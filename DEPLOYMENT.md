# Production deployment

GitHub repository: https://github.com/codealisha99/ai-inference-layer

| Service | Deployment |
| --- | --- |
| Vercel | https://ai-inference-layer.vercel.app |
| Railway API | https://api-production-c6510.up.railway.app |
| API documentation | https://ai-inference-layer.vercel.app/docs |
| Neon | Project `ai-inference-layer` (`dawn-cloud-06427061`), Singapore |

The Python reference implementation runs in Railway using the root Dockerfile.
`.railway/railway.ts` declares the GitHub source, Singapore replica, build and
readiness settings. Run `npm ci`, `railway config plan`, and
`railway config apply --yes` when changing infrastructure. Secrets remain
unmanaged by this configuration.
Vercel builds the shared static interface with `scripts/build_frontend.py` and
builds the playground, Swagger, and ReDoc with one shared shell. API requests and
the OAuth redirect route are forwarded to Railway. The app runs deterministic
local engines; it does not call a hosted LLM provider.

## Configuration

Railway holds `DATABASE_URL` (pooled), `DATABASE_URL_UNPOOLED` (direct, used for
schema initialization), `PORT=3000`, `LOG_FORMAT=json`,
`RATE_LIMIT_PER_MINUTE=60`, and `RATE_LIMIT_BURST=20`.
Database credentials stay in Railway variables and ignored local env files.
`DATABASE_URL` takes precedence over `DATABASE_PATH`; SQLite and memory remain
available for local development.

The playground is a public demo with rate limiting. Set Railway's `API_KEY` to
require credentials for model and inference operations; the interface will
prompt visitors for that key. Probes and documentation stay public.

The PostgreSQL store reconnects before the next operation when its connection is
closed. It does not replay failed queries or writes. An operation interrupted by
a disconnect may return 503; a subsequent readiness check can establish a fresh
connection. Explicit shutdown does not reopen the store.

## Releases and checks

Both hosts connect to the GitHub repository's `main` branch. CI checks all four
language implementations; Python CI also tests PostgreSQL against an isolated
Postgres service. Never point `TEST_DATABASE_URL` at production: integration
tests clear that test database between cases.

```sh
cd ai-inference-server-py
uv sync --extra dev
uv run python -m ruff check src tests
uv run python -m ruff format --check src tests
uv run python -m mypy
# Supply a dedicated test database to include PostgreSQL integration checks.
uv run python -m pytest --cov
```

For a manual release from the repository root:

```sh
railway status
railway up --service api --detach
vercel project inspect --non-interactive
vercel deploy --prod --yes
```

Check `/livez`, `/readyz`, and `/health` through either host. `/health` reports
`storage: postgres`; model records and inference history persist across Railway
restarts. `/metrics` exposes Prometheus counters.
