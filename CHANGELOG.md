# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the Python port uses
[semantic versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - Python port

### Added
- **Persistence.** Opt-in SQLite store (`DATABASE_PATH`): WAL, foreign keys, atomic batches,
  versioned schema, per-model history cap, cascade delete.
- **Batch inference** (`POST /models/{id}/infer/batch`) and **SSE streaming**
  (`POST /models/{id}/infer/stream`).
- **Pagination** on model and history lists (`limit`, `offset`, `X-Total-Count`).
- **Observability.** Prometheus `/metrics` (route-template labels), `/livez` and `/readyz`
  probes, JSON structured logs (`LOG_FORMAT=json`), request ids and `X-Response-Time-Ms`.
- **Protection.** Optional API key, per-client token-bucket rate limiting
  (`RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_BURST`, `TRUST_PROXY`), request body limit
  (`MAX_BODY_BYTES`), opt-in CORS, security headers, and 503 + `Retry-After` when the database
  is unavailable.
- **Typed OpenAPI** document, validated in tests against real responses.
- **`ais` CLI and Python client** (`models`, `infer`, `batch`, `history`, `health`, `metrics`,
  `demo`, `bench`).
- **`ais bench`** load tester with percentile latencies and JSON output.
- Landing page, Dockerfile (non-root, `/data` volume), `docker-compose.yml`, and CI for all four
  ports.

### Changed
- The request pipeline is pure ASGI instead of `BaseHTTPMiddleware`; with uvloop and httptools
  (`uvicorn[standard]`) throughput on health and inference routes roughly doubled.
- Routes use `{model_id}` as the path parameter name (visible in metrics labels and OpenAPI).

## [0.1.0]

- Initial TypeScript, Go, Rust and Python ports sharing one wire contract: models, inference,
  history, health, and the uniform `{success, data, error}` envelope.
