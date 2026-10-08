# AI Inference Layer

Created by [Alisha Karma](https://alishakarma.com).

A model registry and inference API implemented four times (TypeScript, Go, Rust, Python) behind one HTTP contract. Register a model, run inputs against it, read the history back. The Python port is the reference implementation and the most complete.

## Implementations

| Language | Directory | Stack | Notes |
|----------|-----------|-------|-------|
| Python | [ai-inference-server-py](./ai-inference-server-py/) | Python 3.12, FastAPI + Uvicorn | Reference port: batch, SSE streaming, pagination, Prometheus metrics, API-key auth, SQLite persistence, Docker |
| TypeScript | [ai-inference-server-ts](./ai-inference-server-ts/) | Node.js 22, Fastify 5 | Core contract |
| Go | [ai-inference-server-go](./ai-inference-server-go/) | Standard library + chi | Core contract |
| Rust | [ai-inference-server-rust](./ai-inference-server-rust/) | tokio + axum | Core contract |

All four expose the same core routes and the same `{success, data, error}` response envelope:

```
GET    /health
POST   /models                          GET /models
GET    /models/{id}                     DELETE /models/{id}
POST   /models/{id}/infer
GET    /models/{id}/inferences          GET /models/{id}/inferences/{inferenceId}
```

Model types: `text-generation`, `text-classification`, `embedding`. See [ARCHITECTURE.md](./ARCHITECTURE.md) for the design and the full contract, and the [Python README](./ai-inference-server-py/README.md) for the extended API.

## Quick start

```bash
cd ai-inference-server-py && pip install -e ".[dev]"
ais serve --db ./data/ai.db   # Python port with persistence; then in another terminal:
ais demo                      # create sample models and run them (see the Python README)

make run-py     # http://localhost:3000, interactive docs at /docs
make run-ts
make run-go
make run-rust
```

## Build and test everything

```bash
make build
make test
```
