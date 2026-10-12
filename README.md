# AI Inference Layer

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="ai-inference-server-py/src/static/logo-inverse.svg">
  <img src="ai-inference-server-py/src/static/logo.svg" alt="Inference logo" width="288" height="64">
</picture>

Maintained by [Alisha Karma](https://alishakarma.com) ([codealisha99](https://github.com/codealisha99)). Historical contributors remain credited in Git history.

A model registry and inference API implemented four times (TypeScript, Go, Rust, Python) behind one HTTP contract. Register a model, run inputs against it, read the history back. The Python port is the reference implementation and the most complete.

The web workbench is named **Inference**. Its classification, generation, and embedding engines are deterministic reference implementations for integration testing; they do not call a hosted language model.

## Deployment endpoints

- Website and playground: https://ai-inference-layer.vercel.app
- API and Swagger: https://api-production-c6510.up.railway.app/docs
- Storage: dedicated Neon PostgreSQL project in Singapore.

Read-only audit on 2026-10-11: the website responded, but its `/health` and the
Railway `/readyz` endpoint returned HTTP 503. The PostgreSQL connection-recovery fix
was verified locally; live recovery must be checked after release. See [DESIGN_AUDIT.md](./DESIGN_AUDIT.md).

The Vercel site proxies API requests to Railway, so the playground uses the same
persistent database as direct API clients. Pushes to `main` deploy through the
connected GitHub repository. See [DEPLOYMENT.md](./DEPLOYMENT.md) for configuration.

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
cd ai-inference-server-py
uv sync --extra dev --locked
uv run ais serve --db ./data/ai.db
```

Open `http://localhost:3000/` for the playground and `/docs` for the interactive
API reference. In another terminal, run `uv run ais demo` from the same directory
to register sample models and create inference history. Python 3.12+ and
[uv](https://docs.astral.sh/uv/) are required for these commands.

The existing `make run-py`, `make run-ts`, `make run-go`, and `make run-rust`
targets remain available after installing the corresponding implementation's dependencies.

## Build and test everything

```bash
make build
make test
```

## Project docs

- [ARCHITECTURE.md](./ARCHITECTURE.md): design, wire contract, decisions and limitations
- [CHANGELOG.md](./CHANGELOG.md): what changed and when
- [CONTRIBUTING.md](./CONTRIBUTING.md): setup, checks and guidelines
- [SECURITY.md](./SECURITY.md): reporting vulnerabilities and deployment guidance
- [OWNERSHIP.md](./OWNERSHIP.md): primary author, maintainer contact, and attribution policy
- [brand.md](./brand.md): logo assets, palette, typography, and brand usage
