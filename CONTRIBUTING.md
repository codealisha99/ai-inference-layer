# Contributing

Thanks for helping. The repository holds four implementations of one wire contract
(see [ARCHITECTURE.md](ARCHITECTURE.md)); the Python port is the most complete.

## Setup and checks

```bash
make build-py && make test-py        # or, inside ai-inference-server-py:
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests                 # lint
ruff format --check src tests        # formatting
mypy                                 # strict type checking
pytest --cov                         # fails below 90% coverage
```

Other ports: `make test-ts`, `make test-go`, `make test-rust`. CI runs all of them.

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
