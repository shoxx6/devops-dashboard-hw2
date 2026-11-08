"""Small standard-library HTTP app for the SMS spam classifier."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from train_model import predict

ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "public"
MODEL_PATH = Path(os.environ.get("MODEL_PATH", ROOT / "models" / "sms_spam_model.json"))
METRICS_PATH = Path(os.environ.get("METRICS_PATH", ROOT / "models" / "metrics.json"))
MAX_BODY_BYTES = 24_000


def load_json(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


try:
    MODEL = load_json(MODEL_PATH)
    METRICS = load_json(METRICS_PATH)
    MODEL_ERROR = None
except (OSError, ValueError) as error:
    MODEL = None
    METRICS = None
    MODEL_ERROR = str(error)


class Handler(BaseHTTPRequestHandler):
    server_version = "SMSClassifier/1.0"

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            status = 200 if MODEL is not None else 503
            self.send_json(status, {
                "status": "healthy" if MODEL is not None else "model_unavailable",
                "service": "sms-spam-checker",
                "model_loaded": MODEL is not None,
                "metrics": METRICS,
            })
            return

        filenames = {
            "/": "index.html",
            "/style.css": "style.css",
            "/app.js": "app.js",
        }
        filename = filenames.get(path)
        if filename is None:
            self.send_error(404, "Not found")
            return
        content = (PUBLIC_DIR / filename).read_bytes()
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }[Path(filename).suffix]
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        if urlsplit(self.path).path != "/api/predict":
            self.send_json(404, {"error": "Not found."})
            return
        if MODEL is None:
            self.send_json(503, {"error": "The model is not available."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"error": "Invalid request length."})
            return
        if length <= 0 or length > MAX_BODY_BYTES:
            self.send_json(413, {"error": "Message is empty or too long (limit: 5,000 characters)."})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"error": "Send a valid JSON request."})
            return
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            self.send_json(400, {"error": "Enter a message to check."})
            return
        if len(text) > 5000:
            self.send_json(413, {"error": "Message is too long (limit: 5,000 characters)."})
            return
        label, probabilities = predict(MODEL, text.strip())
        self.send_json(200, {
            "label": label,
            "spam_probability": round(probabilities["spam"], 6),
            "ham_probability": round(probabilities["ham"], 6),
            "model": MODEL["model_type"],
        })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    print(f"SMS Spam Checker listening on 0.0.0.0:{port}; model_loaded={MODEL is not None}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
