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
* Admin dashboard
* Cybersecurity threat-intel endpoints
* Frontend demo dashboard
* API documentation
* Security documentation
* Portfolio screenshots and demo GIF
