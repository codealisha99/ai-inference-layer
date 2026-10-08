# ai-inference-server-py

Python port of the AI Inference Server: a model registry plus an inference API, built on
FastAPI. It is wire-compatible with the TypeScript, Go and Rust ports (same routes, same
`{success, data, error}` envelope, same status codes) and adds a few production features on top.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m src.server            # http://localhost:3000  (landing page at /, API docs at /docs)
```

State is in memory by default. Set `DATABASE_PATH=./data/ai.db` to persist everything to SQLite.

Or with Docker:

```bash
docker build -t ai-inference-server-py .
docker run --rm -p 3000:3000 -v ais-data:/data ai-inference-server-py   # persists to /data
```

## API

All responses use the envelope `{"success": bool, "data": ..., "error": string | null}`.

| Method | Path | Description | Success |
|--------|------|-------------|---------|
| GET | `/` | Landing page | 200 |
| GET | `/health` | Status, version, storage backend, uptime, counts | 200 |
| GET | `/metrics` | Prometheus metrics | 200 |
| POST | `/models` | Register a model | 201 |
| GET | `/models` | List models (`?limit=&offset=`) | 200 |
| GET | `/models/{id}` | Get a model | 200 |
| DELETE | `/models/{id}` | Delete a model and its history | 200 |
| POST | `/models/{id}/infer` | Run one inference | 201 |
| POST | `/models/{id}/infer/batch` | Run up to `MAX_BATCH_SIZE` inputs | 201 |
| POST | `/models/{id}/infer/stream` | Stream a text-generation result (SSE) | 200 |
| GET | `/models/{id}/inferences` | Inference history (`?limit=&offset=`) | 200 |
| GET | `/models/{id}/inferences/{inferenceId}` | Get one inference | 200 |

Paginated endpoints return the full total in the `X-Total-Count` header. Without `limit`
every item is returned, as in the other ports.

### Model types

| Type | Output | Config |
|------|--------|--------|
| `text-generation` | `{"text": "..."}` | `maxChars` (positive int) truncates the output |
| `text-classification` | `{"label": "positive" \| "negative" \| "neutral", "score": float}` | none |
| `embedding` | `{"embedding": [float, ...]}` (unit length) | `dimensions` (1-1024, default 5) |

The engines are deterministic and dependency-free: the same input always gives the same
output. The classifier is a small lexicon model with negation handling ("not bad" is positive)
and the embedding is a stable hash projection. They are stand-ins for real model backends; add
one by registering a function in `src/engines.py`.

### Examples

```bash
curl -s -XPOST localhost:3000/models -H 'content-type: application/json' \
  -d '{"name":"sentiment","type":"text-classification"}'

curl -s -XPOST localhost:3000/models/$ID/infer -H 'content-type: application/json' \
  -d '{"input":"this is not bad at all"}'

curl -s -XPOST localhost:3000/models/$ID/infer/batch -H 'content-type: application/json' \
  -d '{"inputs":["great","terrible","table"]}'

curl -sN -XPOST localhost:3000/models/$GEN/infer/stream -H 'content-type: application/json' \
  -d '{"input":"hello world"}'
# event: token / data: {"index":0,"token":"Generated "} ... event: done / data: {<inference>}
```

### Errors

| Status | When |
|--------|------|
| 400 | Missing or invalid field, bad query parameter, invalid config |
| 401 | `API_KEY` is set and the request has no valid key |
| 404 | Unknown route, model or inference |
| 405 | Method not allowed |
| 409 | Model name already exists (names are trimmed) |
| 413 | Input longer than `MAX_INPUT_CHARS` |
| 429 | `MAX_MODELS` reached |
| 500 | Unexpected error (details are logged, never returned) |

Every response carries `X-Request-ID` (echoed from the request or generated) and
`X-Response-Time-Ms`.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `3000` | Listen port |
| `LOG_LEVEL` | `info` | `debug`, `info`, `warning`, `error` |
| `DATABASE_PATH` | unset | SQLite file to persist to (parent directories are created). Unset keeps everything in memory; `:memory:` gives a throwaway SQLite database |
| `API_KEY` | unset | If set, require `Authorization: Bearer <key>` or `X-API-Key` (except `/`, `/assets/*`, `/health`, `/docs`, `/redoc`, `/openapi.json`) |
| `MAX_INPUT_CHARS` | `100000` | Max characters per input |
| `MAX_NAME_CHARS` | `128` | Max model name length |
| `MAX_MODELS` | `1000` | Max registered models |
| `MAX_INFERENCES_PER_MODEL` | `1000` | History kept per model (oldest evicted first) |
| `MAX_BATCH_SIZE` | `64` | Max inputs per batch request |

Invalid values fail fast at startup.

## Development

```bash
ruff check src tests     # lint
mypy                     # strict type check
pytest --cov             # tests; fails below 90% coverage
```

Layout:

```
src/
  server.py     FastAPI app, routes, middleware, error handling
  inference.py  Store protocol and the thread-safe, bounded in-memory store
  sqlite_store.py  Durable SQLite store with the same semantics
  engines.py    Deterministic inference engines + config validation
  metrics.py    Prometheus text exposition
  config.py     Environment-driven settings
  static/       Landing page (served at / and /assets)
tests/          Unit and API tests (HTTP contract, both stores, engines, auth, SSE, metrics)
```

### Persistence

With `DATABASE_PATH` set the server uses SQLite (WAL mode, foreign keys on). It behaves exactly
like the in-memory store, including the model cap, the per-model history cap (oldest inferences
are deleted first) and cascade-delete of a model's history. A batch is a single transaction, so
it is applied completely or not at all. The schema version is stored in `PRAGMA user_version`;
a database written by a newer server is refused rather than misread. One process should own a
database file: run a single worker.

Without `DATABASE_PATH`, a restart clears all models and history.
