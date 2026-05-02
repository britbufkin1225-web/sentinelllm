from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import time
import logging
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


def log_chat_request(ip, endpoint, model, prompt, response_text, status, latency):
    log_entry = {
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


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        start_time = time.time()
        client_ip = self.client_address[0]

        try:
            if self.path == "/chat":
                content_length = int(self.headers["Content-Length"])
                body = self.rfile.read(content_length)
                data = json.loads(body)

                user_input = data.get("message", "")

                model = "local-echo-model"

                response = {
                    "reply": f"Echo: {user_input}"
                }

                response_text = response["reply"]

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())

                latency = time.time() - start_time

                log_chat_request(
                    ip=client_ip,
                    endpoint="/chat",
                    model=model,
                    prompt=user_input,
                    response_text=response_text,
                    status="success",
                    latency=latency
                )

        except Exception as e:
            latency = time.time() - start_time

            log_chat_request(
                ip=client_ip,
                endpoint=self.path,
                model="unknown",
                prompt="",
                response_text=str(e),
                status="error",
                latency=latency
            )

            self.send_response(500)
            self.end_headers()


def run():
    server = HTTPServer(("localhost", 8000), Handler)
    print("Server running on http://localhost:8000")
    server.serve_forever()


if __name__ == "__main__":
    run()