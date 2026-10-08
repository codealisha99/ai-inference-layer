from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from typing import Any, Protocol

from .engines import MODEL_TYPES, run_engine

VALID_TYPES = frozenset(MODEL_TYPES)

Model = dict[str, Any]
Inference = dict[str, Any]


class StoreFull(Exception):
    """Raised when the configured model capacity is reached."""


class Store(Protocol):
    """What the HTTP layer needs from a backend (in-memory or SQLite)."""

    kind: str

    def create_model(self, name: str, type: str, config: dict[str, Any]) -> Model | None: ...
    def get_model(self, mid: str) -> Model | None: ...
    def list_models(self, limit: int | None = None, offset: int = 0) -> tuple[list[Model], int]: ...
    def delete_model(self, mid: str) -> bool: ...
    def run_inference(self, model_id: str, inp: str) -> Inference | None: ...
    def run_batch(self, model_id: str, inputs: list[str]) -> list[Inference] | None: ...
    def list_inferences(
        self, model_id: str, limit: int | None = None, offset: int = 0
    ) -> tuple[list[Inference], int] | None: ...
    def get_inference(self, model_id: str, inference_id: str) -> dict[str, Any]: ...
    def stats(self) -> dict[str, int]: ...
    def ping(self) -> bool: ...
    def close(self) -> None: ...


def new_id() -> str:
    return uuid.uuid4().hex


def now_ms() -> int:
    return int(time.time() * 1000)


def page(items: list[Any], limit: int | None, offset: int) -> list[Any]:
    end = None if limit is None else offset + limit
    return items[offset:end]


class InferenceStore:
    """In-memory, thread-safe store of models and their inference history.

    Memory is bounded: at most ``max_models`` models, and each model keeps its
    ``max_inferences_per_model`` most recent inferences (oldest are evicted first).
    """

    kind = "memory"

    def __init__(self, *, max_models: int = 1_000, max_inferences_per_model: int = 1_000) -> None:
        self._max_models = max_models
        self._max_inferences = max_inferences_per_model
        self._lock = threading.RLock()
        self._models: dict[str, Model] = {}
        self._names: dict[str, str] = {}  # name -> model id
        self._inferences: dict[str, OrderedDict[str, Inference]] = {}

    def create_model(self, name: str, type: str, config: dict[str, Any]) -> Model | None:
        """Create a model, or return ``None`` if the name is already taken."""
        with self._lock:
            if name in self._names:
                return None
            if len(self._models) >= self._max_models:
                raise StoreFull("model limit reached")
            mid = new_id()
            model: Model = {
                "id": mid,
                "name": name,
                "type": type,
                "config": config,
                "createdAt": now_ms(),
            }
            self._models[mid] = model
            self._names[name] = mid
            self._inferences[mid] = OrderedDict()
            return model

    def get_model(self, mid: str) -> Model | None:
        with self._lock:
            return self._models.get(mid)

    def list_models(self, limit: int | None = None, offset: int = 0) -> tuple[list[Model], int]:
        """Return a page of models plus the total count."""
        with self._lock:
            items = list(self._models.values())
        return page(items, limit, offset), len(items)

    def delete_model(self, mid: str) -> bool:
        with self._lock:
            model = self._models.pop(mid, None)
            if model is None:
                return False
            self._names.pop(model["name"], None)
            self._inferences.pop(mid, None)
            return True

    def run_inference(self, model_id: str, inp: str) -> Inference | None:
        batch = self.run_batch(model_id, [inp])
        return None if batch is None else batch[0]

    def run_batch(self, model_id: str, inputs: list[str]) -> list[Inference] | None:
        """Run several inputs against one model atomically (None if model is unknown)."""
        with self._lock:
            model = self._models.get(model_id)
            if model is None:
                return None
            return [self._run_locked(model, inp) for inp in inputs]

    def _run_locked(self, model: Model, inp: str) -> Inference:
        model_id = model["id"]
        started = time.perf_counter()
        created = now_ms()
        output = run_engine(model["type"], inp, model["config"])
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        inf: Inference = {
            "id": new_id(),
            "modelId": model_id,
            "input": inp,
            "status": "completed",
            "output": output,
            "createdAt": created,
            "completedAt": now_ms(),
            "latencyMs": latency_ms,
        }
        bucket = self._inferences[model_id]
        bucket[inf["id"]] = inf
        while len(bucket) > self._max_inferences:
            bucket.popitem(last=False)
        return inf

    def list_inferences(
        self, model_id: str, limit: int | None = None, offset: int = 0
    ) -> tuple[list[Inference], int] | None:
        with self._lock:
            bucket = self._inferences.get(model_id)
            if bucket is None:
                return None
            items = list(bucket.values())
        return page(items, limit, offset), len(items)

    def get_inference(self, model_id: str, inference_id: str) -> dict[str, Any]:
        with self._lock:
            bucket = self._inferences.get(model_id)
            if bucket is None:
                return {"modelFound": False}
            return {"modelFound": True, "inf": bucket.get(inference_id)}

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        """Nothing to release for the in-memory store."""

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "models": len(self._models),
                "inferences": sum(len(b) for b in self._inferences.values()),
            }
