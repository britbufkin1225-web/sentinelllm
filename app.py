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
START_TIME = time.time()

def load_env_file(filepath=".env"):
    if not os.path.exists(filepath):
        return

    with open(filepath, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip()

load_env_file()

API_KEY = os.getenv("SENTINEL_API_KEY", "dev-key-change-me")

CHEATSHEET_DIR = "cheatsheets"
CACHE_TTL_SECONDS = 300
FRONTEND_DIR = "frontend"


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


def build_success_response(data):
    return {
        "success": True,
        "data": data,
        "error": None
    }


def build_error_response(code, message, data=None):
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message
        },
        "data": data
    }


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

    if not query:
        return [], False

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

    if not query:
        return [], False

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


def read_request_logs():
    if not os.path.exists(REQUEST_LOG_FILE):
        return []

    logs = []

    with open(REQUEST_LOG_FILE, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line:
                continue

            try:
                logs.append(json.loads(line))
            except json.JSONDecodeError:
                logs.append({"raw": line})

    return logs


def summarize_request_logs(logs):
    status_counts = {}
    method_counts = {}

    for entry in logs:
        status = str(entry.get("status", entry.get("status_code", "unknown")))
        method = entry.get("method") or "UNKNOWN"

        status_counts[status] = status_counts.get(status, 0) + 1
        method_counts[method] = method_counts.get(method, 0) + 1

    return {
        "total_requests": len(logs),
        "status_counts": status_counts,
        "method_counts": method_counts
    }


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

    def send_static_file(self, filename, content_type):
        filepath = os.path.join(FRONTEND_DIR, filename)

        try:
            with open(filepath, "rb") as file:
                content = file.read()
        except OSError:
            self.send_error(404, "Dashboard asset not found")
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        request_id = str(uuid.uuid4())
        self.set_headers(200, request_id)

    def do_GET(self):
        request_id = str(uuid.uuid4())

        parsed_path = urlparse(self.path)
        endpoint = parsed_path.path.rstrip("/") or "/"
        query_params = parse_qs(parsed_path.query)
        ip = self.client_address[0]

        ctx = RequestContext(request_id, ip, endpoint, "GET")

        dashboard_routes = {
            "/dashboard": ("dashboard.html", "text/html; charset=utf-8"),
            "/dashboard.css": ("dashboard.css", "text/css; charset=utf-8"),
            "/dashboard.js": ("dashboard.js", "application/javascript; charset=utf-8"),
        }

        if endpoint in dashboard_routes:
            filename, content_type = dashboard_routes[endpoint]
            self.send_static_file(filename, content_type)
            return

        protected_get_routes = {
            "/api/v1/system",
            "/api/v1/logs",
            "/api/v1/logs/recent",
            "/api/v1/logs/summary",
            "/api/v1/events",
            "/api/v1/events/summary",
            "/api/v1/devices",
            "/api/v1/network/scan",
            "/api/v1/metrics",
        }

        if endpoint in protected_get_routes:
            incoming_api_key = self.headers.get("X-API-Key")

            if incoming_api_key != API_KEY:
                log_event(ctx, 401, "Invalid or missing API key")

                self.send_json(
                    401,
                    build_error_response(
                        "UNAUTHORIZED",
                        "Invalid or missing API key"
                    ),
                    request_id
                )
                return

            if is_rate_limited(ip):
                log_event(ctx, 429, "Rate limit exceeded")

                self.send_json(
                    429,
                    build_error_response(
                        "RATE_LIMITED",
                        "Rate limit exceeded"
                    ),
                    request_id
                )
                return

        if endpoint in {"/health", "/api/v1/health"}:
            log_event(ctx, 200, "Health check")

            self.send_json(
                200,
                build_success_response({
                    "status": "ok",
                    "service": "SentinelLLM backend"
                }),
                request_id
            )
            return

        if endpoint == "/api/v1/system":
            log_event(ctx, 200, "System status served")

            self.send_json(
                200,
                build_success_response({
                    "service": "SentinelLLM backend",
                    "status": "running"
                }),
                request_id
            )
            return

        if endpoint == "/api/v1/logs":
            logs = read_request_logs()
            log_event(ctx, 200, "Logs endpoint served")

            data = {
                "logs": logs
            }

            if not logs:
                data["message"] = "No request logs found"

            self.send_json(
                200,
                build_success_response(data),
                request_id
            )
            return

        if endpoint == "/api/v1/logs/recent":
            limit_value = query_params.get("limit", ["10"])[0]

            try:
                limit = int(limit_value)
            except (TypeError, ValueError):
                limit = 0

            if limit < 1 or limit > 100:
                log_event(ctx, 400, "Invalid recent logs limit")

                self.send_json(
                    400,
                    build_error_response(
                        "INVALID_LIMIT",
                        "Limit must be an integer between 1 and 100"
                    ),
                    request_id
                )
                return

            logs = read_request_logs()
            recent_logs = logs[-limit:]
            log_event(ctx, 200, "Recent logs endpoint served")

            self.send_json(
                200,
                build_success_response({
                    "logs": recent_logs,
                    "count": len(recent_logs),
                    "limit": limit
                }),
                request_id
            )
            return
        
        if endpoint == "/api/v1/logs/summary":
            logs = read_request_logs()

            status_counts = {}
            method_counts = {}
            endpoint_counts = {}
            error_count = 0
            latest_request_timestamp = None

            for entry in logs:
                status = entry.get("status", entry.get("status_code", "unknown"))
                status_key = str(status)

                method = entry.get("method") or "UNKNOWN"
                logged_endpoint = entry.get("endpoint") or "unknown"
                timestamp = entry.get("timestamp")

                status_counts[status_key] = status_counts.get(status_key, 0) + 1
                method_counts[method] = method_counts.get(method, 0) + 1
                endpoint_counts[logged_endpoint] = endpoint_counts.get(logged_endpoint, 0) + 1

                try:
                    if int(status) >= 400:
                        error_count += 1
                except (TypeError, ValueError):
                    pass

                if timestamp:
                    latest_request_timestamp = timestamp

            top_endpoints = [
                {"endpoint": endpoint_name, "count": count}
                for endpoint_name, count in sorted(
                    endpoint_counts.items(),
                    key=lambda item: item[1],
                    reverse=True
                )[:10]
            ]

            log_event(ctx, 200, "Logs summary endpoint served")

            self.send_json(
                200,
                build_success_response({
                    "total_requests": len(logs),
                    "status_counts": status_counts,
                    "method_counts": method_counts,
                    "endpoint_counts": endpoint_counts,
                    "top_endpoints": top_endpoints,
                    "error_count": error_count,
                    "latest_request_timestamp": latest_request_timestamp,
                }),
                request_id
            )
            return

        if endpoint == "/api/v1/events":
            log_event(ctx, 200, "Events endpoint served")

            self.send_json(
                200,
                build_success_response({
                    "events": [],
                    "count": 0,
                    "message": "Events endpoint ready"
                }),
                request_id
            )
            return

        if endpoint == "/api/v1/events/summary":
            log_event(ctx, 200, "Events summary endpoint served")

            self.send_json(
                200,
                build_success_response({
                    "total_events": 0,
                    "by_severity": {},
                    "by_type": {},
                    "by_source": {}
                }),
                request_id
            )
            return

        if endpoint == "/api/v1/devices":
            log_event(ctx, 200, "Devices endpoint served")

            self.send_json(
                200,
                build_success_response({
                    "devices": [],
                    "count": 0,
                    "message": "Devices endpoint ready"
                }),
                request_id
            )
            return

        if endpoint == "/api/v1/network/scan":
            log_event(ctx, 200, "Network scan endpoint served")

            self.send_json(
                200,
                build_success_response({
                    "scan_status": "not_implemented",
                    "message": "Network scan endpoint is wired but scanning is not implemented yet",
                    "devices": []
                }),
                request_id
            )
            return

        if endpoint == "/api/v1/metrics":
            logs = read_request_logs()
            request_summary = summarize_request_logs(logs)
            log_event(ctx, 200, "Metrics endpoint served")

            self.send_json(
                200,
                build_success_response({
                    "service": "SentinelLLM backend",
                    "status": "running",
                    "uptime_seconds": round(time.time() - START_TIME, 2),
                    "requests": request_summary,
                    "rate_limit": {
                        "window_seconds": RATE_LIMIT_WINDOW_SECONDS,
                        "max_requests": RATE_LIMIT_MAX_REQUESTS
                    },
                    "cache": {
                        "enabled": True,
                        "ttl_seconds": CACHE_TTL_SECONDS,
                        "items": len(cheatsheet_cache)
                    }
                }),
                request_id
            )
            return

        if endpoint == "/cheatsheet":
            search_query = query_params.get("q", [""])[0].strip()

            if not search_query:
                log_event(ctx, 400, "Missing cheatsheet query")

                self.send_json(
                    400,
                    build_error_response(
                        "EMPTY_QUERY",
                        "Query parameter 'q' is required and cannot be empty"
                    ),
                    request_id
                )
                return

            result, cache_hit = get_cheatsheet(search_query)

            if result is None:
                log_event(ctx, 404, f"Cheatsheet not found: {search_query}")

                self.send_json(
                    404,
                    build_error_response(
                        "CHEATSHEET_NOT_FOUND",
                        "Cheatsheet not found",
                        {
                            "query": search_query
                        }
                    ),
                    request_id
                )
                return

            log_event(ctx, 200, f"Cheatsheet served: {search_query}")

            self.send_json(
                200,
                build_success_response({
                    "query": search_query,
                    "result": result,
                    "source": "local_file",
                    "cache_hit": cache_hit
                }),
                request_id
            )
            return

        if endpoint == "/cheatsheet/search":
            search_query = query_params.get("q", [""])[0].strip()

            if not search_query:
                log_event(ctx, 400, "Missing cheatsheet search query")

                self.send_json(
                    400,
                    build_error_response(
                        "EMPTY_QUERY",
                        "Query parameter 'q' is required and cannot be empty"
                    ),
                    request_id
                )
                return

            results, cache_hit = search_cheatsheets(search_query)

            log_event(ctx, 200, f"Cheatsheet search: {search_query}")

            self.send_json(
                200,
                build_success_response({
                    "query": search_query,
                    "count": len(results),
                    "results": results,
                    "cache_hit": cache_hit
                }),
                request_id
            )
            return

        if endpoint == "/cheatsheet/autocomplete":
            q = query_params.get("q", [""])[0].strip()

            if not q:
                log_event(ctx, 400, "Missing autocomplete query")

                self.send_json(
                    400,
                    build_error_response(
                        "EMPTY_QUERY",
                        "Query parameter 'q' is required and cannot be empty"
                    ),
                    request_id
                )
                return

            suggestions, cache_hit = autocomplete_cheatsheets(q)

            log_event(ctx, 200, "Cheatsheet autocomplete")

            self.send_json(
                200,
                build_success_response({
                    "query": q,
                    "suggestions": suggestions,
                    "cache_hit": cache_hit
                }),
                request_id
            )
            return

        log_event(ctx, 404, "Endpoint not found")

        self.send_json(
            404,
            build_error_response(
                "NOT_FOUND",
                "Endpoint not found"
            ),
            request_id
        )

    def do_POST(self):
        request_id = str(uuid.uuid4())

        parsed_path = urlparse(self.path)
        endpoint = parsed_path.path.rstrip("/") or "/"
        ip = self.client_address[0]

        ctx = RequestContext(request_id, ip, endpoint, "POST")

        try:
            if endpoint != "/chat":
                log_event(ctx, 404, "Endpoint not found")

                self.send_json(
                    404,
                    build_error_response(
                        "NOT_FOUND",
                        "Endpoint not found"
                    ),
                    request_id
                )
                return

            if is_rate_limited(ip):
                log_event(ctx, 429, "Rate limit exceeded")

                self.send_json(
                    429,
                    build_error_response(
                        "RATE_LIMITED",
                        "Rate limit exceeded"
                    ),
                    request_id
                )
                return

            incoming_api_key = self.headers.get("X-API-Key")

            if incoming_api_key != API_KEY:
                log_event(ctx, 401, "Invalid or missing API key")

                self.send_json(
                    401,
                    build_error_response(
                        "UNAUTHORIZED",
                        "Invalid or missing API key"
                    ),
                    request_id
                )
                return

            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                log_event(ctx, 400, "Invalid JSON")

                self.send_json(
                    400,
                    build_error_response(
                        "INVALID_JSON",
                        "Invalid JSON"
                    ),
                    request_id
                )
                return

            prompt = data.get("prompt", "").strip()

            if not prompt:
                log_event(ctx, 400, "Missing prompt")

                self.send_json(
                    400,
                    build_error_response(
                        "MISSING_PROMPT",
                        "Missing prompt"
                    ),
                    request_id
                )
                return

            response_text = fake_ai_response(prompt)

            log_event(
                ctx,
                200,
                "Chat request successful",
                prompt=prompt,
                response_text=response_text
            )

            self.send_json(
                200,
                build_success_response({
                    "response": response_text
                }),
                request_id
            )

        except Exception as error:
            log_event(
                ctx,
                500,
                "Internal server error",
                error=error
            )

            self.send_json(
                500,
                build_error_response(
                    "INTERNAL_SERVER_ERROR",
                    "Internal server error"
                ),
                request_id
            )


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
