"""Deploy a new SMS image behind a persistent loopback Docker proxy."""

import json
import os
import subprocess
import threading
import time
from urllib.request import urlopen

from verify_rollout import NEW_SHA, OLD_SHA, SAMPLE, STABLE_PORT, docker, image_for, monitor, predict, summary

NETWORK = "sms-hw3"
EDGE = "sms-hw3-edge"
NGINX_CONFIG = "/etc/nginx/conf.d/default.conf"


def exists(kind, name):
    return subprocess.run(["docker", kind, "inspect", name],
                          capture_output=True).returncode == 0


def active_revision():
    with urlopen(f"http://127.0.0.1:{STABLE_PORT}/health", timeout=3) as response:
        revision = response.headers["X-Image-Revision"]
        if not revision or not json.load(response)["model_loaded"]:
            raise RuntimeError("Proxy is not serving a healthy SMS image")
        return revision


def backend_name(revision):
    return f"sms-hw3-{revision[:12]}"


def ensure_backend(revision):
    name = backend_name(revision)
    if not exists("container", name):
        docker("run", "-d", "--name", name, "--network", NETWORK,
               "--restart", "unless-stopped", "-p", "127.0.0.1::10000", image_for(revision))
    else:
        docker("start", name)
    port = int(docker("port", name, "10000/tcp").splitlines()[0].rsplit(":", 1)[1])
    for _ in range(25):
        try:
            if predict(port)[1].get("label") == "spam":
                return
        except OSError:
            pass
        time.sleep(1)
    raise RuntimeError(f"Container {name} did not become ready")


def route(revision):
    config = f"""server {{
      listen 80;
      location / {{
        proxy_pass http://{backend_name(revision)}:10000;
        add_header X-Image-Revision {revision} always;
      }}
    }}
    """
    subprocess.run(["docker", "exec", "-i", EDGE, "sh", "-c",
                    f"cat > {NGINX_CONFIG}"], input=config.encode("ascii"), check=True)
    docker("exec", EDGE, "nginx", "-t")
    docker("exec", EDGE, "nginx", "-s", "reload")
    for _ in range(20):
        try:
            if active_revision() == revision:
                return
        except (OSError, RuntimeError):
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Proxy did not route to {revision}")


def main():
    if not exists("network", NETWORK):
        docker("network", "create", NETWORK)
    if not exists("container", EDGE):
        ensure_backend(OLD_SHA)
        docker("run", "-d", "--name", EDGE, "--network", NETWORK, "--restart", "unless-stopped",
               "-p", f"127.0.0.1:{STABLE_PORT}:80", "nginx:alpine")
        for _ in range(20):
            if subprocess.run(["docker", "exec", EDGE, "nginx", "-t"],
                              capture_output=True).returncode == 0:
                break
            time.sleep(0.5)
        route(OLD_SHA)

    prior = active_revision()
    if prior == NEW_SHA:
        print(f"Revision {NEW_SHA} is already active")
        return

    done = threading.Event()
    samples, stage = [], ["Before"]
    probe = threading.Thread(target=monitor, args=(done, samples, stage))
    probe.start()
    try:
        time.sleep(5)
        stage[0] = "During"
        ensure_backend(NEW_SHA)
        route(NEW_SHA)
        time.sleep(5)
        stage[0] = "After"
        time.sleep(30)
        done.set()
        probe.join()
        environment = "Self-hosted Windows runner" if os.getenv("GITHUB_ACTIONS") == "true" else "Local Windows Docker"
        healthy = summary(samples, environment)
        after = [row for row in samples if row[0] == "After"]
        if not healthy or any(row[2:] != (NEW_SHA, "spam", len(SAMPLE)) for row in after):
            raise RuntimeError("The local deployment did not pass verification")
    except Exception:
        route(prior)
        raise
    finally:
        done.set()
        probe.join()
    docker("rm", "-f", backend_name(prior))
    print(f"Local service: http://127.0.0.1:{STABLE_PORT}/")


if __name__ == "__main__":
    main()
