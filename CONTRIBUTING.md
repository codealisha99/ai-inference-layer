# Contributing

Primary maintainer: [Alisha Karma](https://github.com/codealisha99). Contact:
[lishykarma99@gmail.com](mailto:lishykarma99@gmail.com). Contributions remain
attributed to their authors; do not rewrite history to change ownership.
See [OWNERSHIP.md](./OWNERSHIP.md) for the identity and attribution policy.

Thanks for helping. The repository holds four implementations of one wire contract
(see [ARCHITECTURE.md](ARCHITECTURE.md)); the Python port is the most complete.

## Setup and checks

```bash
cd ai-inference-server-py
uv sync --extra dev --locked
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
uv run python -m pytest --cov         # fails below 90% coverage
```

The pip-based `make build-py` and `make test-py` targets remain supported.

Other ports: `make test-ts`, `make test-go`, `make test-rust`. CI runs all of them.

For the website, run `npm ci`, `npm run build`, and `npm run test:ui` from the
repository root. The browser suite uses installed Google Chrome and two isolated,
in-memory Python servers; it never needs production database credentials. Run
`uv run python -m pytest ../tests/test_frontend_build.py -q` from the Python
directory to check the static documentation output and local deployment rewrites.

## Guidelines

- **Tests come with the change.** Behaviour changes need a test that fails without them; HTTP
  behaviour is tested against the real app, and `tests/conftest.py` can start a live server.
- **Keep the contract stable.** Every response keeps the `{success, data, error}` envelope.
  Python-only extras must be additive so the other ports stay compatible.
- **Keep OpenAPI honest.** Response models live in `src/schemas.py`; `tests/test_openapi.py`
  checks the published document against real responses, so update both together.
- **Measure performance claims.** Use `ais bench` before and after, and put the numbers in the
  pull request.
- **Small, focused commits** with a message that explains why, not only what.

## Pull requests

Describe the change, how you tested it, and anything reviewers should look at closely. Link the
issue if there is one. CI must pass.
