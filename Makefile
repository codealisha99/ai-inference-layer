.PHONY: build test clean demo-py build-ts build-go build-rust build-py test-ts test-go test-rust test-py

build: build-ts build-go build-rust build-py

test: test-ts test-go test-rust test-py

build-ts:
	cd ai-inference-server-ts && npm ci && npm run typecheck

build-go:
	cd ai-inference-server-go && go build ./...

build-rust:
	cd ai-inference-server-rust && cargo build --release

build-py:
	cd ai-inference-server-py && pip install -e ".[dev]"

test-ts:
	cd ai-inference-server-ts && npm test

test-go:
	cd ai-inference-server-go && go test -race ./...

test-rust:
	cd ai-inference-server-rust && cargo test

test-py:
	cd ai-inference-server-py && ruff check src tests && mypy && python -m pytest -v --cov

run-ts:
	cd ai-inference-server-ts && npm start

run-go:
	cd ai-inference-server-go && go run ./cmd/server

run-rust:
	cd ai-inference-server-rust && cargo run

run-py:
	cd ai-inference-server-py && python -m src.server

demo-py:
	cd ai-inference-server-py && python -m src.cli demo

clean:
	cd ai-inference-server-ts && rm -rf dist node_modules 2>/dev/null || true
	cd ai-inference-server-go && go clean 2>/dev/null || true
	cd ai-inference-server-rust && cargo clean 2>/dev/null || true
	cd ai-inference-server-py && rm -rf .pytest_cache __pycache__ src/__pycache__ .ruff_cache .mypy_cache .coverage 2>/dev/null || true
