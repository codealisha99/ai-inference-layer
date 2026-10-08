# AI Inference Server — Architecture

## Overview

A small model registry plus an inference API. Clients register named models of a given type
(`text-generation`, `text-classification`, `embedding`), run inputs against them, and read the
inference history back. The same HTTP contract is implemented four times (TypeScript, Go, Rust,
Python) so the ports can be compared and swapped behind one client.

Inference is done by deterministic in-process engines rather than real model weights. That keeps
the server dependency-free and its output reproducible, and the engine boundary is the single
place a real backend would plug in.

The Python port (`ai-inference-server-py`) is the most complete: on top of the shared contract it
adds batch inference, SSE streaming, pagination, Prometheus metrics, optional API-key auth and
configurable limits. See its [README](./ai-inference-server-py/README.md).

## Component Diagram

```mermaid
graph TD
    Client -->|HTTP + JSON| Middleware
    subgraph Server
        Middleware[Middleware: auth, request id, access log, metrics]
        Middleware --> Routes[Routes + validation]
        Routes --> Store[InferenceStore]
        Store --> Engines[Engines]
        Routes --> Metrics[Metrics]
    end
    Prometheus -->|GET /metrics| Middleware
```

## Sequence Diagram

```mermaid
sequenceDiagram
    participant Client
    participant Middleware
    participant Routes
    participant Store
    participant Engine
    Client->>Middleware: POST /models/{id}/infer
    Middleware->>Middleware: check API key, assign request id
    Middleware->>Routes: forward
    Routes->>Routes: validate body (input is a non-empty string, within limit)
    Routes->>Store: run_inference(id, input)
    Store->>Engine: run_engine(type, input, config)
    Engine-->>Store: output
    Store->>Store: record inference, evict oldest past the cap
    Store-->>Routes: inference
    Routes-->>Middleware: 201 {success, data, error}
    Middleware-->>Client: response + X-Request-ID
```

## Data Flow

1. A model is created with a unique (trimmed) name, a type and an optional `config`. The config is
   validated against the type before the model is stored.
2. An inference is created synchronously: the engine runs, and the result is stored with status
   `completed`, timestamps and measured `latencyMs`.
3. Each model owns a bounded, insertion-ordered history. When it exceeds
   `MAX_INFERENCES_PER_MODEL` the oldest entries are evicted.
4. Deleting a model removes its history and frees its name.
5. Batch requests are validated up front and executed under one lock, so they either run entirely
   or not at all. Streaming creates and stores the inference first, then emits its text as
   `token` events followed by a final `done` event carrying the full record.

## Wire Contract (shared by all ports)

Every response is `{"success": bool, "data": ..., "error": string | null}`.

| Route | Success | Errors |
|-------|---------|--------|
| `GET /health` | 200 | |
| `POST /models` | 201 | 400 invalid, 409 duplicate name |
| `GET /models`, `GET /models/{id}` | 200 | 404 unknown model |
| `DELETE /models/{id}` | 200 | 404 |
| `POST /models/{id}/infer` | 201 | 400 missing input, 404 |
| `GET /models/{id}/inferences[/{inferenceId}]` | 200 | 404 model or inference |

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Deterministic engines instead of real models | No heavy dependencies, reproducible tests, and a clear seam (`run_engine`) for a real backend |
| One response envelope everywhere, including 404/405/500 | Clients parse a single shape; no framework default error bodies leak through |
| In-memory store behind a lock | Simple and fast for a reference server; the store API is the boundary for swapping in persistence |
| Bounded memory (model cap, per-model history cap) | An unauthenticated or runaway client cannot grow the process without limit |
| Python extras are additive | New fields (`latencyMs`) and endpoints do not change existing responses, so other ports stay compatible |
| Metrics label by route template, not raw path | Unknown paths collapse to `unmatched`, keeping Prometheus cardinality bounded |
| Config validated at startup | A bad `PORT` or limit fails immediately instead of at first request |
| Secrets compared in constant time | `API_KEY` checks use `hmac.compare_digest` |

## Known Limitations

- State is not persisted; a restart clears everything.
- The server is single-process; with several workers each would hold its own store.
- Auth is a single shared key, with no per-client keys or rate limiting.
