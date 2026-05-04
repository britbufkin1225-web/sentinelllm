import json
import os
import time
import logging
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

# =========================
# Configuration
# =========================

HOST = "localhost"
PORT = 8000

LOG_DIR = "logs"
REQUEST_LOG_FILE = os.path.join(LOG_DIR, "requests.log")

RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 10

API_KEY = os.getenv("API_KEY", "dev-key-change-me")

CHEATSHEET_DIR = "cheatsheets"
CACHE_TTL_SECONDS = 300


# =========================
# Setup
# =========================

os.makedirs(LOG_DIR, exist_ok=True)

request_logger = logging.getLogger("request_logger")
request_logger.setLevel(logging.INFO)

if not request_logger.handlers:
    file_handler = logging.FileHandler(REQUEST_LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    request_logger.addHandler(file_handler)


rate_limit_store = {}
cheatsheet_cache = {}


# =========================
# Helpers
# =========================

def now_iso():
    return datetime.now().isoformat()


def log_event(ctx, status, message, model=None, prompt=None, response_text=None, error=None):
    log_entry = {
        "timestamp": now_iso(),
        "request_id": ctx.request_id,
        "ip": ctx.ip,
        "method": ctx.method,
        "endpoint": ctx.endpoint,
        "status": status,
        "latency_ms": ctx.latency_ms(),
        "model": model,
        "prompt_length": len(prompt) if prompt else 0,
        "response_length": len(response_text) if response_text else 0,
        "error": str(error) if error else None,
        "message": message
    }

    request_logger.info(json.dumps(log_entry))


def is_rate_limited(ip):
    current_time = time.time()

    if ip not in rate_limit_store:
        rate_limit_store[ip] = []

    rate_limit_store[ip] = [
        timestamp for timestamp in rate_limit_store[ip]
        if current_time - timestamp < RATE_LIMIT_WINDOW_SECONDS
    ]

    if len(rate_limit_store[ip]) >= RATE_LIMIT_MAX_REQUESTS:
        return True

    rate_limit_store[ip].append(current_time)
    return False


def fake_ai_response(prompt):
    return f"Received your prompt: {prompt}"


class RequestContext:
    def __init__(self, request_id, ip, endpoint, method):
        self.request_id = request_id
        self.ip = ip
        self.endpoint = endpoint
        self.method = method
        self.start_time = time.time()

    def latency_ms(self):
        return round((time.time() - self.start_time) * 1000, 2)


def cache_get(key):
    cached_item = cheatsheet_cache.get(key)

    if not cached_item:
        return None, False

    age = time.time() - cached_item["created_at"]

    if age > CACHE_TTL_SECONDS:
        del cheatsheet_cache[key]
        return None, False

    return cached_item["data"], True


def cache_set(key, data):
    cheatsheet_cache[key] = {
        "created_at": time.time(),
        "data": data
    }

def get_cheatsheet(query):
    query = query.strip().lower()

    if not query:
        return None, False

    cache_key = f"cheatsheet:{query}"
    cached_result, cache_hit = cache_get(cache_key)

    if cache_hit:
        return cached_result, True

    filename = f"{query}.txt"
    filepath = os.path.join(CHEATSHEET_DIR, filename)

    if not os.path.exists(filepath):
        return None, False

    with open(filepath, "r", encoding="utf-8") as file:
        result = file.read()

    cache_set(cache_key, result)

    return result, False


def search_cheatsheets(query):
    query = query.strip().lower()

    cache_key = f"cheatsheet_search:{query}"
    cached_result, cache_hit = cache_get(cache_key)

    if cache_hit:
        return cached_result, True

    results = []

    if not os.path.exists(CHEATSHEET_DIR):
        return results, False

    for filename in os.listdir(CHEATSHEET_DIR):
        if not filename.endswith(".txt"):
            continue

        filepath = os.path.join(CHEATSHEET_DIR, filename)

        with open(filepath, "r", encoding="utf-8") as file:
            content = file.read()

        name = filename.replace(".txt", "")

        if query in name.lower() or query in content.lower():
            results.append({
                "name": name,
                "filename": filename,
                "preview": content[:200]
            })

    cache_set(cache_key, results)

    return results, False


def autocomplete_cheatsheets(query):
    query = query.strip().lower()

    cache_key = f"cheatsheet_autocomplete:{query}"
    cached_result, cache_hit = cache_get(cache_key)

    if cache_hit:
        return cached_result, True

    suggestions = []

    if not os.path.exists(CHEATSHEET_DIR):
        return suggestions, False

    for filename in os.listdir(CHEATSHEET_DIR):
        if not filename.endswith(".txt"):
            continue

        name = filename.replace(".txt", "")

        if name.lower().startswith(query):
            suggestions.append(name)

    cache_set(cache_key, suggestions)

    return suggestions, False

# =========================
# Request Handler
# =========================

class ChatHandler(BaseHTTPRequestHandler):

    def set_headers(self, status_code=200, request_id=None):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")

        if request_id:
            self.send_header("X-Request-ID", request_id)

        self.end_headers()

    def send_json(self, status_code, data, request_id):
        data["request_id"] = request_id

        self.set_headers(status_code, request_id)

        response_body = json.dumps(data).encode("utf-8")
        self.wfile.write(response_body)

    def do_OPTIONS(self):
        request_id = str(uuid.uuid4())
        self.set_headers(200, request_id)

    def do_GET(self):
        request_id = str(uuid.uuid4())

        parsed_path = urlparse(self.path)
        endpoint = parsed_path.path
        query_params = parse_qs(parsed_path.query)
        ip = self.client_address[0]

        ctx = RequestContext(request_id, ip, endpoint, "GET")

        if endpoint == "/health":
            log_event(ctx, 200, "Health check")

            self.send_json(200, {
               "status": "ok",
               "service": "SentinelLLM backend"
            }, request_id)
            return

        if endpoint == "/cheatsheet":
            search_query = query_params.get("q", [""])[0]
            result, cache_hit = get_cheatsheet(search_query)

            if result is None:
                log_event(ctx, 404, f"Cheatsheet not found: {search_query}")

                self.send_json(404, {
                    "query": search_query,
                    "error": "Cheatsheet not found"
                }, request_id)
                return

            log_event(ctx, 200, f"Cheatsheet served: {search_query}")

            self.send_json(200, {
                "query": search_query,
                "result": result,
                "source": "local_file",
                "cache_hit": cache_hit
            }, request_id)
            return

        if endpoint == "/cheatsheet/search":
            search_query = query_params.get("q", [""])[0]
            results, cache_hit = search_cheatsheets(search_query)

            log_event(ctx, 200, f"Cheatsheet search: {search_query}")

            self.send_json(200, {
                "query": search_query,
                "count": len(results),
                "results": results,
                "cache_hit": cache_hit
            }, request_id)
            return

        if endpoint == "/cheatsheet/autocomplete":
            q = query_params.get("q", [""])[0]
            suggestions, cache_hit = autocomplete_cheatsheets(q)

            log_event(ctx, 200, "Cheatsheet autocomplete")

            self.send_json(200, {
                "query": q,
                "suggestions": suggestions,
                "cache_hit": cache_hit
            }, request_id)
            return

        log_event(ctx, 404, "Endpoint not found")

        self.send_json(404, {
            "error": "Endpoint not found"
        }, request_id)

    def do_POST(self):
        request_id = str(uuid.uuid4())

        parsed_path = urlparse(self.path)
        endpoint = parsed_path.path
        ip = self.client_address[0]

        ctx = RequestContext(request_id, ip, endpoint, "POST")

        try:
            if endpoint != "/chat":
                log_event(ctx, 404, "Endpoint not found")

                self.send_json(404, {
                    "error": "Endpoint not found"
                }, request_id)
                return

            if is_rate_limited(ip):
                log_event(ctx, 429, "Rate limit exceeded")

                self.send_json(429, {
                    "error": "Rate limit exceeded"
                }, request_id)
                return

            incoming_api_key = self.headers.get("X-API-Key")

            if incoming_api_key != API_KEY:
                log_event(ctx, 401, "Invalid or missing API key")

                self.send_json(401, {
                    "error": "Invalid or missing API key"
                }, request_id)
                return

            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                log_event(ctx, 400, "Invalid JSON")

                self.send_json(400, {
                    "error": "Invalid JSON"
                }, request_id)
                return

            prompt = data.get("prompt", "").strip()

            if not prompt:
                log_event(ctx, 400, "Missing prompt")

                self.send_json(400, {
                    "error": "Missing prompt"
                }, request_id)
                return

            response_text = fake_ai_response(prompt)

            log_event(
                ctx,
                200,
                "Chat request successful",
                prompt=prompt,
                response_text=response_text
            )

            self.send_json(200, {
                "response": response_text
            }, request_id)

        except Exception as error:
            log_event(
                ctx,
                500,
                "Internal server error",
                error=error
            )

            self.send_json(500, {
                "error": "Internal server error"
            }, request_id)


# =========================
# Run Server
# =========================

def run_server():
    print("RUNNING FILE:", os.path.abspath(__file__))

    server = HTTPServer((HOST, PORT), ChatHandler)

    print(f"SentinelLLM backend running at http://{HOST}:{PORT}")

    server.serve_forever()


if __name__ == "__main__":
    run_server()