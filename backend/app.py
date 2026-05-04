import os
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("SENTINEL_API_KEY")

if not API_KEY:
    raise ValueError("Missing SENTINEL_API_KEY in .env file")

from http.server import BaseHTTPRequestHandler, HTTPServer
from collections import defaultdict
import json
import os
import time
import logging
import uuid
from datetime import datetime

# =========================
# Request Logging Setup
# =========================

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

REQUEST_LOG_FILE = os.path.join(LOG_DIR, "requests.log")

request_logger = logging.getLogger("request_logger")
request_logger.setLevel(logging.INFO)

if not request_logger.handlers:
    file_handler = logging.FileHandler(REQUEST_LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    request_logger.addHandler(file_handler)


# =========================
# Rate Limiting Setup
# =========================

RATE_LIMIT = 10
RATE_WINDOW = 60  # seconds

ip_request_times = defaultdict(list)


def is_rate_limited(ip):
    now = time.time()

    ip_request_times[ip] = [
        t for t in ip_request_times[ip]
        if now - t < RATE_WINDOW
    ]

    if len(ip_request_times[ip]) >= RATE_LIMIT:
        return True

    ip_request_times[ip].append(now)
    return False


def log_chat_request(request_id, ip, endpoint, model, prompt, response_text, status, latency):
    log_entry = {
        "request_id": request_id,
        "timestamp": datetime.now().isoformat(),
        "ip": ip,
        "endpoint": endpoint,
        "model": model,
        "prompt_length": len(prompt) if prompt else 0,
        "response_length": len(response_text) if response_text else 0,
        "status": status,
        "latency_ms": round(latency * 1000, 2)
    }

    request_logger.info(json.dumps(log_entry))

def is_authorized(headers):
    provided_key = headers.get("X-API-Key")
    return provided_key == API_KEY

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not is_authorized(self.headers):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "Unauthorized"
            }).encode("utf-8"))
            return
        start_time = time.time()
        request_id = str(uuid.uuid4())
        client_ip = self.client_address[0]

        if is_rate_limited(client_ip):
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Request-ID", request_id)
            self.end_headers()

            response = {
                "error": "Rate limit exceeded",
                "message": "Too many requests. Please wait and try again.",
                "request_id": request_id
            }

            self.wfile.write(json.dumps(response).encode("utf-8"))

            latency = time.time() - start_time

            log_chat_request(
                request_id=request_id,
                ip=client_ip,
                endpoint=self.path,
                model="unknown",
                prompt="",
                response_text="Rate limit exceeded",
                status="rate_limited",
                latency=latency
            )

            return

        try:
            if self.path == "/chat":
                content_length = int(self.headers["Content-Length"])
                body = self.rfile.read(content_length)
                data = json.loads(body)

                user_input = data.get("message", "")

                model = "local-echo-model"

                response = {
                    "reply": f"Echo: {user_input}",
                    "request_id": request_id
                }

                response_text = response["reply"]

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("X-Request-ID", request_id)
                self.end_headers()
                self.wfile.write(json.dumps(response).encode("utf-8"))

                latency = time.time() - start_time

                log_chat_request(
                    request_id=request_id,
                    ip=client_ip,
                    endpoint="/chat",
                    model=model,
                    prompt=user_input,
                    response_text=response_text,
                    status="success",
                    latency=latency
                )

            else:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("X-Request-ID", request_id)
                self.end_headers()

                response = {
                    "error": "Not found",
                    "request_id": request_id
                }

                self.wfile.write(json.dumps(response).encode("utf-8"))

        except Exception as e:
            latency = time.time() - start_time

            log_chat_request(
                request_id=request_id,
                ip=client_ip,
                endpoint=self.path,
                model="unknown",
                prompt="",
                response_text=str(e),
                status="error",
                latency=latency
            )

            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Request-ID", request_id)
            self.end_headers()

            response = {
                "error": "Internal server error",
                "request_id": request_id
            }

            self.wfile.write(json.dumps(response).encode("utf-8"))


def run():
    server = HTTPServer(("localhost", 8000), Handler)
    print("Server running on http://localhost:8000")
    server.serve_forever()


if __name__ == "__main__":
    run()