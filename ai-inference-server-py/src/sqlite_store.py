"""SQLite-backed store: same behaviour as ``InferenceStore`` but durable across restarts."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .engines import run_engine
from .inference import Inference, Model, StoreFull, new_id, now_ms

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS models (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    id         TEXT    NOT NULL UNIQUE,
    name       TEXT    NOT NULL UNIQUE,
    type       TEXT    NOT NULL,
    config     TEXT    NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS inferences (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    id           TEXT    NOT NULL UNIQUE,
    model_id     TEXT    NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    input        TEXT    NOT NULL,
    status       TEXT    NOT NULL,
    output       TEXT    NOT NULL,
    created_at   INTEGER NOT NULL,
    completed_at INTEGER NOT NULL,
    latency_ms   REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_inferences_model ON inferences(model_id, seq);
"""


def _model(row: sqlite3.Row) -> Model:
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "config": json.loads(row["config"]),
        "createdAt": row["created_at"],
    }


def _inference(row: sqlite3.Row) -> Inference:
    return {
        "id": row["id"],
        "modelId": row["model_id"],
        "input": row["input"],
        "status": row["status"],
        "output": json.loads(row["output"]),
        "createdAt": row["created_at"],
        "completedAt": row["completed_at"],
        "latencyMs": row["latency_ms"],
    }


class SqliteStore:
    """Durable store with the same limits as the in-memory one.

    * Writes happen in short transactions; a batch is a single transaction, so it is
      all-or-nothing even across a crash.
    * ``max_models`` caps registered models; each model keeps its newest
      ``max_inferences_per_model`` inferences (older rows are deleted).
    * Deleting a model cascades to its inferences.

    A single connection is shared behind a lock, which is plenty for this workload and
    keeps ``:memory:`` databases working.
    """

    kind = "sqlite"

    def __init__(
        self,
        path: str,
        *,
        max_models: int = 1_000,
        max_inferences_per_model: int = 1_000,
    ) -> None:
        self._max_models = max_models
        self._max_inferences = max_inferences_per_model
        self._lock = threading.RLock()
        self.path = path
        if path != ":memory:":
            Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None -> autocommit; transactions are explicit in ``_tx``.
        self._conn = sqlite3.connect(
            path, check_same_thread=False, isolation_level=None, timeout=10.0
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
        self._migrate()

    # ---- plumbing --------------------------------------------------------------------

    def _migrate(self) -> None:
        with self._lock:
            version = self._conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"database schema v{version} is newer than this server (v{SCHEMA_VERSION})"
                )
            if version < SCHEMA_VERSION:
                self._conn.executescript(_SCHEMA)
                self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---- models ----------------------------------------------------------------------

    def create_model(self, name: str, type: str, config: dict[str, Any]) -> Model | None:
        with self._tx() as db:
            if db.execute("SELECT 1 FROM models WHERE name = ?", (name,)).fetchone():
                return None
            count = db.execute("SELECT COUNT(*) FROM models").fetchone()[0]
            if count >= self._max_models:
                raise StoreFull("model limit reached")
            mid = new_id()
            created = now_ms()
            db.execute(
                "INSERT INTO models (id, name, type, config, created_at) VALUES (?, ?, ?, ?, ?)",
                (mid, name, type, json.dumps(config), created),
            )
        return {"id": mid, "name": name, "type": type, "config": config, "createdAt": created}

    def get_model(self, mid: str) -> Model | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM models WHERE id = ?", (mid,)).fetchone()
        return _model(row) if row else None

    def list_models(self, limit: int | None = None, offset: int = 0) -> tuple[list[Model], int]:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) FROM models").fetchone()[0]
            rows = self._conn.execute(
                "SELECT * FROM models ORDER BY seq LIMIT ? OFFSET ?",
                (-1 if limit is None else limit, offset),
            ).fetchall()
        return [_model(r) for r in rows], total

    def delete_model(self, mid: str) -> bool:
        with self._tx() as db:
            return db.execute("DELETE FROM models WHERE id = ?", (mid,)).rowcount > 0

    # ---- inferences ------------------------------------------------------------------

    def run_inference(self, model_id: str, inp: str) -> Inference | None:
        batch = self.run_batch(model_id, [inp])
        return None if batch is None else batch[0]

    def run_batch(self, model_id: str, inputs: list[str]) -> list[Inference] | None:
        with self._tx() as db:
            row = db.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
            if row is None:
                return None
            model = _model(row)
            results: list[Inference] = []
            for inp in inputs:
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
                db.execute(
                    "INSERT INTO inferences (id, model_id, input, status, output, created_at,"
                    " completed_at, latency_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        inf["id"],
                        model_id,
                        inp,
                        inf["status"],
                        json.dumps(output),
                        inf["createdAt"],
                        inf["completedAt"],
                        latency_ms,
                    ),
                )
                results.append(inf)
            # Keep only the newest N rows for this model: delete everything at or before
            # the (N+1)-th newest. The subquery is NULL (deletes nothing) under the cap.
            db.execute(
                "DELETE FROM inferences WHERE model_id = ? AND seq <= ("
                " SELECT seq FROM inferences WHERE model_id = ?"
                " ORDER BY seq DESC LIMIT 1 OFFSET ?)",
                (model_id, model_id, self._max_inferences),
            )
            return results

    def list_inferences(
        self, model_id: str, limit: int | None = None, offset: int = 0
    ) -> tuple[list[Inference], int] | None:
        with self._lock:
            if not self._conn.execute("SELECT 1 FROM models WHERE id = ?", (model_id,)).fetchone():
                return None
            total = self._conn.execute(
                "SELECT COUNT(*) FROM inferences WHERE model_id = ?", (model_id,)
            ).fetchone()[0]
            rows = self._conn.execute(
                "SELECT * FROM inferences WHERE model_id = ? ORDER BY seq LIMIT ? OFFSET ?",
                (model_id, -1 if limit is None else limit, offset),
            ).fetchall()
        return [_inference(r) for r in rows], total

    def get_inference(self, model_id: str, inference_id: str) -> dict[str, Any]:
        with self._lock:
            if not self._conn.execute("SELECT 1 FROM models WHERE id = ?", (model_id,)).fetchone():
                return {"modelFound": False}
            row = self._conn.execute(
                "SELECT * FROM inferences WHERE model_id = ? AND id = ?",
                (model_id, inference_id),
            ).fetchone()
        return {"modelFound": True, "inf": _inference(row) if row else None}

    def stats(self) -> dict[str, int]:
        with self._lock:
            models = self._conn.execute("SELECT COUNT(*) FROM models").fetchone()[0]
            inferences = self._conn.execute("SELECT COUNT(*) FROM inferences").fetchone()[0]
        return {"models": models, "inferences": inferences}
