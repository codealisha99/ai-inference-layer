"""A small load tester for a running server: throughput and latency percentiles per scenario.

    ais bench --duration 5 --concurrency 16

It creates temporary ``bench-*`` models, drives each scenario from ``concurrency`` threads over
keep-alive connections, then deletes the models. The load generator is Python, so on a single
machine it can become the bottleneck before the server does; treat results as a floor and
compare scenarios and runs against each other rather than against other languages' tools.
"""

from __future__ import annotations

import http.client
import json
import threading
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .client import Client


@dataclass
class Scenario:
    name: str
    method: str
    path: Callable[[dict[str, str]], str]
    body: Callable[[], Any] | None = None
    expect: tuple[int, ...] = (200, 201)


@dataclass
class Result:
    name: str
    requests: int = 0
    errors: int = 0
    seconds: float = 0.0
    latencies_ms: list[float] = field(default_factory=list)

    @property
    def rps(self) -> float:
        return self.requests / self.seconds if self.seconds else 0.0

    def percentile(self, p: float) -> float:
        if not self.latencies_ms:
            return 0.0
        data = sorted(self.latencies_ms)
        return data[min(len(data) - 1, int(len(data) * p / 100))]

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.name,
            "requests": self.requests,
            "errors": self.errors,
            "rps": round(self.rps, 1),
            "p50_ms": round(self.percentile(50), 2),
            "p95_ms": round(self.percentile(95), 2),
            "p99_ms": round(self.percentile(99), 2),
        }


SCENARIOS: list[Scenario] = [
    Scenario("GET /health", "GET", lambda m: "/health"),
    Scenario("GET /models/{id}", "GET", lambda m: f"/models/{m['gen']}"),
    Scenario(
        "infer: text-generation",
        "POST",
        lambda m: f"/models/{m['gen']}/infer",
        lambda: {"input": "the quick brown fox jumps over the lazy dog"},
    ),
    Scenario(
        "infer: text-classification",
        "POST",
        lambda m: f"/models/{m['cls']}/infer",
        lambda: {"input": "this is not a bad product, quite good in fact"},
    ),
    Scenario(
        "infer: embedding (64 dims)",
        "POST",
        lambda m: f"/models/{m['emb']}/infer",
        lambda: {"input": "a short sentence to embed"},
    ),
    Scenario(
        "batch x16: embedding (64 dims)",
        "POST",
        lambda m: f"/models/{m['emb']}/infer/batch",
        lambda: {"inputs": [f"sentence number {i}" for i in range(16)]},
    ),
    Scenario("GET history (limit 20)", "GET", lambda m: f"/models/{m['gen']}/inferences?limit=20"),
    Scenario("GET /models (list)", "GET", lambda m: "/models?limit=20"),
]

_MODELS = {
    "gen": ("bench-generation", "text-generation", None),
    "cls": ("bench-classifier", "text-classification", None),
    "emb": ("bench-embedder", "embedding", {"dimensions": 64}),
}


def _connect(url: urllib.parse.ParseResult, timeout: float) -> http.client.HTTPConnection:
    cls = http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
    return cls(url.hostname or "localhost", url.port, timeout=timeout)


def _drive(
    url: urllib.parse.ParseResult,
    headers: dict[str, str],
    scenario: Scenario,
    models: dict[str, str],
    stop_at: float,
    out: Result,
    lock: threading.Lock,
) -> None:
    conn = _connect(url, 30.0)
    path = scenario.path(models)
    payload = json.dumps(scenario.body()).encode() if scenario.body else None
    hdrs = dict(headers)
    if payload:
        hdrs["content-type"] = "application/json"
    latencies: list[float] = []
    errors = 0
    while time.perf_counter() < stop_at:
        started = time.perf_counter()
        try:
            conn.request(scenario.method, path, body=payload, headers=hdrs)
            resp = conn.getresponse()
            resp.read()
            ok = resp.status in scenario.expect
        except (OSError, http.client.HTTPException):
            ok = False
            conn.close()
            conn = _connect(url, 30.0)
        latencies.append((time.perf_counter() - started) * 1000)
        errors += 0 if ok else 1
    conn.close()
    with lock:
        out.latencies_ms.extend(latencies)
        out.requests += len(latencies)
        out.errors += errors


def run_scenario(
    base_url: str,
    api_key: str | None,
    scenario: Scenario,
    models: dict[str, str],
    duration: float,
    concurrency: int,
) -> Result:
    url = urllib.parse.urlparse(base_url)
    headers = {"x-api-key": api_key} if api_key else {}
    result = Result(scenario.name)
    lock = threading.Lock()
    started = time.perf_counter()
    stop_at = started + duration
    threads = [
        threading.Thread(
            target=_drive, args=(url, headers, scenario, models, stop_at, result, lock), daemon=True
        )
        for _ in range(concurrency)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    result.seconds = time.perf_counter() - started
    return result


def run_benchmark(
    client: Client,
    *,
    duration: float = 3.0,
    concurrency: int = 16,
    scenarios: list[Scenario] | None = None,
    progress: Callable[[str], None] | None = None,
) -> list[Result]:
    """Run every scenario against ``client``'s server; returns one ``Result`` each."""
    created: list[str] = []
    models: dict[str, str] = {}
    try:
        for key, (name, typ, cfg) in _MODELS.items():
            try:
                existing = client.find_model(name)
                client.delete_model(existing["id"])
            except Exception:  # noqa: S110 - absent on a fresh server
                pass
            model = client.create_model(name, typ, cfg)
            models[key] = model["id"]
            created.append(model["id"])
        results = []
        for scenario in scenarios or SCENARIOS:
            if progress:
                progress(scenario.name)
            results.append(
                run_scenario(
                    client.base_url, client.api_key, scenario, models, duration, concurrency
                )
            )
        return results
    finally:
        for mid in created:
            try:
                client.delete_model(mid)
            except Exception:  # noqa: S110, PERF203 - best-effort cleanup
                pass
