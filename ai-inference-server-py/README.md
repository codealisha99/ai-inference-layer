# ai-inference-server-py

Created by [Alisha Karma](https://alishakarma.com).

Python port of the AI Inference Server: a model registry plus an inference API, built on
FastAPI. It is wire-compatible with the TypeScript, Go and Rust ports (same routes, same
`{success, data, error}` envelope, same status codes) and adds a few production features on top.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

ais serve --db ./data/ai.db     # http://localhost:3000, data persists in SQLite
ais demo                        # in another terminal: creates sample models and runs them
```

`ais serve` without `--db` keeps everything in memory. Open `http://localhost:3000/` for the
landing page and live playground, or `/docs` for the interactive API reference.

With Docker (data persists in a volume):

```bash
docker compose up --build
# or: docker build -t ai-inference-server-py . && docker run --rm -p 3000:3000 -v ais-data:/data ai-inference-server-py
```

## Using it

### Command line: `ais`

```bash
ais models create sentiment --type text-classification
ais models create vectors   --type embedding --config '{"dimensions": 64}'
ais models create writer    --type text-generation
ais models list

ais infer sentiment "this is not bad at all"          # positive (0.73)
echo "I love it" | ais infer sentiment                # input from stdin
ais infer writer "once upon a time" --stream          # tokens print as they arrive
ais batch sentiment "great" "awful" "a table"         # one request, many inputs
ais batch sentiment -f reviews.txt                    # one input per line
ais history sentiment --limit 10
ais health
ais bench --duration 5 -c 16                          # load-test a running server
```

Models can be referenced by name or id. Add `--json` to any command for raw JSON (handy with
`jq`). Point it at another server with `--url` / `AIS_URL`, and pass a key with `--api-key` /
`AIS_API_KEY`. Exit codes: `0` ok, `1` the server returned an error, `2` the server is
unreachable.

### From Python

The client has no dependencies beyond the standard library.

```python
from src.client import Client

ais = Client("http://localhost:3000")        # api_key="..." if the server requires one
model = ais.create_model("sentiment", "text-classification")

ais.infer(model["id"], "this is not bad at all")["output"]   # {'label': 'positive', 'score': 0.7311}
ais.batch(model["id"], ["great", "awful"])                   # list of inferences

writer = ais.create_model("writer", "text-generation")
for token in ais.stream_text(writer["id"], "hello world"):   # tokens as they arrive
    print(token, end="")
page = ais.list_inferences(model["id"], limit=10)            # page.total is the overall count
```

Errors raise `ApiError` (with `.status` and `.message`) or `ServerUnreachable`.

### From anything else

It is plain HTTP and JSON, so `curl` works too. See the API reference below.

## API

All responses use the envelope `{"success": bool, "data": ..., "error": string | null}`.

| Method | Path | Description | Success |
|--------|------|-------------|---------|
| GET | `/` | Landing page | 200 |
| GET | `/health` | Status, version, storage backend, uptime, counts | 200 |
| GET | `/metrics` | Prometheus metrics | 200 |
| GET | `/livez` | Liveness probe (never touches storage) | 200 |
| GET | `/readyz` | Readiness probe: 200 when storage answers, else 503 | 200 / 503 |
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

The API is fully described at `/openapi.json` (rendered at `/docs` and `/redoc`): request bodies,
response schemas, query parameters and every error status for each route. The tests validate
real responses against those schemas, so the documentation cannot drift from the behaviour.

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

### Rate limiting

Set `RATE_LIMIT_PER_MINUTE` to enable a token bucket per client (default: off). Each request costs
one token, and the bucket holds `RATE_LIMIT_BURST` tokens that refill continuously. Responses carry
`X-RateLimit-Limit`, `X-RateLimit-Remaining` and `X-RateLimit-Reset`; a blocked request gets `429`
with `Retry-After`. The check runs before authentication, so repeated wrong-key guesses are
throttled too. `/health`, `/livez`, `/readyz`, `/metrics`, the docs and the landing page are never
limited.

Clients are identified by their peer address. Behind a reverse proxy, set `TRUST_PROXY=true` so the
address the proxy appended to `X-Forwarded-For` is used instead (never enable it when clients can
reach the server directly, since they could then choose their own identity). Bucket state is per
process and bounded to 10,000 clients.

### Errors

| Status | When |
|--------|------|
| 400 | Missing or invalid field, bad query parameter, invalid config |
| 401 | `API_KEY` is set and the request has no valid key |
| 404 | Unknown route, model or inference |
| 405 | Method not allowed |
| 409 | Model name already exists (names are trimmed) |
| 413 | Input longer than `MAX_INPUT_CHARS`, or request body larger than `MAX_BODY_BYTES` |
| 429 | Rate limit exceeded (sent with `Retry-After`), or `MAX_MODELS` reached |
| 500 | Unexpected error (details are logged, never returned) |
| 503 | Storage is temporarily unavailable (sent with `Retry-After`) |

Every response carries `X-Request-ID` (echoed from the request if it is 1-128 characters of
`A-Za-z0-9._-`, otherwise generated) and `X-Response-Time-Ms`. API responses also send
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` and
`Cache-Control: no-store`.

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
| `MAX_BODY_BYTES` | `4194304` | Max request body size, enforced while reading (covers chunked uploads) |
| `LOG_FORMAT` | `text` | `text`, or `json` for one structured object per line (request id, method, path, status, duration) |
| `RATE_LIMIT_PER_MINUTE` | unset | Enable per-client rate limiting at this sustained rate. Unset disables it |
| `RATE_LIMIT_BURST` | = per-minute rate | Bucket size: how many requests a client may send at once |
| `TRUST_PROXY` | `false` | Key clients by the last `X-Forwarded-For` hop (set only behind a proxy that appends it) |
| `CORS_ORIGINS` | unset | Comma-separated allowed browser origins (`*` for any). Unset disables CORS |

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
  cli.py          `ais` command line
  client.py       Dependency-free Python client
  bench.py        Load generator behind `ais bench`
  server.py       FastAPI app factory, routes, exception handlers
  middleware.py   Pure-ASGI request pipeline (ids, auth, rate limit, metrics, logs) and body limit
  ratelimit.py    Token-bucket limiter
  schemas.py      Pydantic response/request models (the typed OpenAPI contract)
  openapi.py      OpenAPI metadata and schema assembly
  inference.py    Store protocol and the thread-safe, bounded in-memory store
  sqlite_store.py Durable SQLite store with the same semantics
  engines.py      Deterministic inference engines + config validation
  metrics.py      Prometheus text exposition
  logging_config.py  Text and JSON log formats
  config.py       Environment-driven settings
  static/         Landing page (served at / and /assets)
tests/          Unit, API and end-to-end tests (HTTP contract, both stores, engines, auth,
                SSE, metrics, and the client and CLI against a real running server)
```

### Persistence

With `DATABASE_PATH` set the server uses SQLite (WAL mode, foreign keys on). It behaves exactly
like the in-memory store, including the model cap, the per-model history cap (oldest inferences
are deleted first) and cascade-delete of a model's history. A batch is a single transaction, so
it is applied completely or not at all. The schema version is stored in `PRAGMA user_version`;
a database written by a newer server is refused rather than misread. One process should own a
database file: run a single worker.

Without `DATABASE_PATH`, a restart clears all models and history.

## Performance

`ais bench` drives a running server with keep-alive connections and reports throughput and
latency percentiles per scenario. It creates (and removes) its own `bench-*` models, so it is safe
to point at a scratch server:

```bash
ais serve &                          # or: ais serve --db /tmp/bench.db
ais bench --duration 5 -c 16         # add --json for machine-readable output
```

Measured on an Apple M4, Python 3.12, one uvicorn worker, 16 client connections on the same
machine (so the load generator competes for CPU; treat the numbers as a floor, not a ceiling):

| Scenario                       | Memory req/s | SQLite req/s | Memory p50 | SQLite p50 |
|--------------------------------|-------------:|-------------:|-----------:|-----------:|
| `GET /health`                  |       11,821 |       10,803 |    1.26 ms |    1.33 ms |
| `GET /models/{id}`             |        9,878 |       10,026 |    1.36 ms |    1.47 ms |
| `GET /models` (list)           |        9,742 |        9,030 |    1.37 ms |    1.63 ms |
| infer: text-generation         |        8,790 |        4,656 |    1.61 ms |    2.78 ms |
| infer: text-classification     |        8,954 |        4,840 |    1.60 ms |    2.83 ms |
| infer: embedding (64 dims)     |        6,704 |        3,804 |    2.10 ms |    3.58 ms |
| `GET` history (limit 20)       |        6,662 |        5,342 |    2.21 ms |    2.72 ms |
| batch of 16 embeddings         |        1,362 |          792 |   10.77 ms |   18.99 ms |

Where the time goes, and what was done about it:

- **Middleware.** The request pipeline is plain ASGI rather than Starlette's
  `BaseHTTPMiddleware`. The latter wraps every request in extra tasks and streams; on a trivial
  app that alone cut throughput from ~13.8k to ~6.8k req/s. Moving to pure ASGI roughly doubled
  `/health` and inference throughput.
- **Event loop and parser.** `uvicorn[standard]` brings uvloop and httptools.
- **Writes.** Inference on SQLite is bound by a durable write per request (WAL, one lock-protected
  connection); a batch is a single transaction, which is why batching is the fast path for bulk
  work: 16 inputs per request yields ~21.8k embeddings/s on memory (~12.7k on SQLite) versus
  ~6.7k (~3.8k) as single requests.
- **Engines.** A 64-dimension embedding costs ~23 µs of pure compute, so a 16-input batch is
  dominated by hashing plus JSON encoding, not by the server.

Numbers vary with hardware; run `ais bench` against your own deployment.
