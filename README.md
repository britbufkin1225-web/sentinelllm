# SentinelLLM Backend

SentinelLLM is a local-first backend service for experimenting with AI assistant infrastructure, cybersecurity reference tooling, API security, request tracing, caching, and backend observability.

The project is designed as a lightweight portfolio backend that demonstrates practical backend engineering concepts including protected API routes, structured logging, request IDs, latency tracking, rate limiting, local data lookup, and future LLM provider integration.

## Current Features

* Local Python HTTP backend server
* Health check endpoint
* Status endpoint
* Mock chat endpoint
* API key authentication for protected requests
* Per-IP rate limiting
* JSON request logging
* Request ID tracing
* Latency tracking
* Local cybersecurity cheatsheet lookup
* Cheatsheet search
* Cheatsheet autocomplete
* In-memory response caching
* Basic metrics endpoint
* Live browser dashboard for health, metrics, and request logs
* CORS support
* Structured error handling for common request failures

## Planned Features

* API key protection for all non-public endpoints
* Rate limiting for all protected endpoints
* Cache hit/miss metrics
* Expanded metrics endpoint
* Cache stats endpoint
* Cache clearing endpoint
* SQLite-backed cheatsheet storage
* Better structured error responses
* Real LLM provider support
* Ollama local model integration
* Optional OpenAI API integration
* Unit tests
* Docker support
* FastAPI migration
* Cybersecurity threat-intel endpoints
* API documentation
* Security documentation
* Portfolio screenshots and demo GIF

## Dashboard Preview

![SentinelLLM Dashboard](docs/screenshots/dashboard.png)

To create or refresh the dashboard screenshot:

1. Run the backend from the repository root:

   ```powershell
   python app.py
   ```

2. Open `http://localhost:8000/dashboard` in a browser.
3. Enter a valid API key and refresh the dashboard.
4. Take a screenshot and save it as `docs/screenshots/dashboard.png`.
