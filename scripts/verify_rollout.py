"""Exercise an image rollout on the Actions runner through one local URL."""

import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

SAMPLE = "URGENT! You have won a free prize. Call now to claim your reward!"
PAYLOAD = json.dumps({"text": SAMPLE}).encode()
OLD_SHA = os.environ["BASELINE_REVISION"]
NEW_SHA = os.environ["GITHUB_SHA"]
REPOSITORY = os.environ["IMAGE_REPOSITORY"]
STABLE_PORT = 18080


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def image_for(sha):
    image = f"{REPOSITORY}:sha-{sha[:7]}"
    docker("pull", image)
    revision = docker("image", "inspect", "--format",
                      '{{index .Config.Labels "org.opencontainers.image.revision"}}', image)
    if revision != sha:
        raise RuntimeError(f"Unexpected revision for {image}: {revision}")
    return image


def predict(port):
    request = Request(f"http://127.0.0.1:{port}/api/predict", data=PAYLOAD,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=3) as response:
        return response.status, json.load(response)


def start(name, image, port):
    docker("run", "-d", "--name", name, "-p", f"127.0.0.1:{port}:10000", image)
    for _ in range(30):
        try:
            status, result = predict(port)
            if status == 200 and result["label"] == "spam":
                return
        except OSError:
            pass
        time.sleep(1)
    raise RuntimeError(f"{name} did not become ready")


class Proxy(BaseHTTPRequestHandler):
    # One immutable target snapshot per request. Keep the old process alive
    # until the cutover has been observed at the public-facing test port.
    target = (18081, OLD_SHA)

    def do_POST(self):
        port, revision = self.target
        with urlopen(Request(f"http://127.0.0.1:{port}{self.path}",
                             data=self.rfile.read(int(self.headers["Content-Length"])),
                             headers={"Content-Type": "application/json"}), timeout=2) as upstream:
            body = upstream.read()
            self.send_response(upstream.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Image-Revision", revision)
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, *_args):
        pass


def monitor(done, samples, stage):
    while not done.is_set():
        request = Request(f"http://127.0.0.1:{STABLE_PORT}/api/predict",
                          data=PAYLOAD, headers={"Content-Type": "application/json"})
        phase = stage[0]
        started = time.monotonic()
        try:
            with urlopen(request, timeout=3) as response:
                result = json.load(response)
                row = (phase, response.status, response.headers["X-Image-Revision"],
                       result["label"], result.get("message_length"))
        except (OSError, ValueError, KeyError) as error:
            print(f"Request failed: {error}", flush=True)
            row = (phase, 0, "", "", None)
        samples.append(row)
        print(f"{phase} HTTP {row[1]} {row[2][:7]} {row[3]} length={row[4]} "
              f"({(time.monotonic() - started)*1000:.0f} ms)", flush=True)
        done.wait(1)


def summary(samples):
    lines = ["## SMS Spam Checker rollout", "",
             "GitHub-hosted Ubuntu runner · POST `http://127.0.0.1:18080/api/predict`", "",
             "| Phase | Successful / sent | Image revision | Label | Message length |",
             "| --- | ---: | --- | --- | --- |"]
    counts = {}
    for phase in ("Before", "During", "After"):
        rows = [row for row in samples if row[0] == phase]
        good = [row for row in rows if row[1] == 200 and row[3] == "spam"]
        counts[phase] = (len(good), len(rows))
        versions = ", ".join(dict.fromkeys(row[2][:7] for row in good)) or "—"
        lengths = ", ".join(dict.fromkeys(str(row[4] or "—") for row in good)) or "—"
        lines.append(f"| {phase} | {len(good)}/{len(rows)} | {versions} | "
                     f"{'spam' if good else '—'} | {lengths} |")
    failures = sum(sent - good for good, sent in counts.values())
    lines += ["", f"**{len(samples)} requests · {failures} failed**", "",
              f"Image change: `{OLD_SHA[:7]}` → `{NEW_SHA[:7]}`."]
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as output:
        output.write("\n".join(lines) + "\n")
    return all(good > 0 and good == sent for good, sent in counts.values())


def main():
    done = threading.Event()
    stage = ["Before"]
    samples = []
    server = ThreadingHTTPServer(("127.0.0.1", STABLE_PORT), Proxy)
    probe = threading.Thread(target=monitor, args=(done, samples, stage))
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    try:
        start("sms-old", image_for(OLD_SHA), 18081)
        serving.start()
        probe.start()
        time.sleep(5)
        stage[0] = "During"
        start("sms-new", image_for(NEW_SHA), 18082)
        Proxy.target = (18082, NEW_SHA)
        time.sleep(5)
        docker("rm", "-f", "sms-old")
        stage[0] = "After"
        time.sleep(30)
    finally:
        done.set()
        if probe.ident is not None:
            probe.join()
        if serving.ident is not None:
            server.shutdown()
        server.server_close()
        healthy = summary(samples)
        subprocess.run(["docker", "rm", "-f", "sms-old", "sms-new"],
                       capture_output=True, check=False)

    before = [row for row in samples if row[0] == "Before"]
    after = [row for row in samples if row[0] == "After"]
    if (not healthy or any(row[2:] != (OLD_SHA, "spam", None) for row in before)
            or any(row[2:] != (NEW_SHA, "spam", len(SAMPLE)) for row in after)):
        raise RuntimeError("Rollout verification failed")


if __name__ == "__main__":
    main()
