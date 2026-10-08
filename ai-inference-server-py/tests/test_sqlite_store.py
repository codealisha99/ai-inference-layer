import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

from src.config import Settings
from src.inference import InferenceStore, StoreFull
from src.server import build_app, open_store
from src.sqlite_store import SCHEMA_VERSION, SqliteStore


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "data" / "ai.db")  # parent directory does not exist yet


@pytest.fixture
def store(db_path):
    s = SqliteStore(db_path)
    yield s
    s.close()


class TestStoreContract:
    """Behaviour must match the in-memory store."""

    def test_model_roundtrip(self, store):
        m = store.create_model("a", "embedding", {"dimensions": 8})
        assert store.get_model(m["id"]) == m
        assert store.get_model("nope") is None

    def test_duplicate_name(self, store):
        store.create_model("a", "embedding", {})
        assert store.create_model("a", "embedding", {}) is None

    def test_delete_frees_name_and_cascades(self, store):
        m = store.create_model("a", "text-generation", {})
        inf = store.run_inference(m["id"], "hi")
        assert store.delete_model(m["id"]) is True
        assert store.delete_model(m["id"]) is False
        assert store.get_inference(m["id"], inf["id"]) == {"modelFound": False}
        assert store.stats() == {"models": 0, "inferences": 0}
        assert store.create_model("a", "embedding", {}) is not None

    def test_model_limit(self, db_path):
        s = SqliteStore(db_path, max_models=1)
        s.create_model("a", "embedding", {})
        with pytest.raises(StoreFull):
            s.create_model("b", "embedding", {})
        s.close()

    def test_models_keep_insertion_order_and_paginate(self, store):
        for n in range(5):
            store.create_model(f"m{n}", "embedding", {})
        page, total = store.list_models(limit=2, offset=1)
        assert [m["name"] for m in page] == ["m1", "m2"]
        assert total == 5
        assert [m["name"] for m in store.list_models()[0]] == [f"m{n}" for n in range(5)]

    def test_inference_roundtrip_matches_memory_store(self, store):
        mem = InferenceStore()
        for s in (store, mem):
            s.create_model("e", "embedding", {"dimensions": 4})
        sm = store.list_models()[0][0]
        mm = mem.list_models()[0][0]
        a = store.run_inference(sm["id"], "hello")
        b = mem.run_inference(mm["id"], "hello")
        assert a["output"] == b["output"]
        assert set(a) == set(b)
        assert store.get_inference(sm["id"], a["id"])["inf"] == a

    def test_unknown_model(self, store):
        assert store.run_inference("nope", "x") is None
        assert store.run_batch("nope", ["x"]) is None
        assert store.list_inferences("nope") is None
        assert store.get_inference("nope", "x") == {"modelFound": False}

    def test_unknown_inference(self, store):
        m = store.create_model("a", "embedding", {})
        assert store.get_inference(m["id"], "nope") == {"modelFound": True, "inf": None}

    def test_history_cap_evicts_oldest_per_model(self, db_path):
        s = SqliteStore(db_path, max_inferences_per_model=3)
        a = s.create_model("a", "text-generation", {})
        b = s.create_model("b", "text-generation", {})
        ids = [s.run_inference(a["id"], f"i{n}")["id"] for n in range(5)]
        s.run_inference(b["id"], "other")
        items, total = s.list_inferences(a["id"])
        assert [i["id"] for i in items] == ids[2:]
        assert total == 3
        assert s.list_inferences(b["id"])[1] == 1  # other models are untouched
        s.close()

    def test_batch_over_cap_keeps_newest(self, db_path):
        s = SqliteStore(db_path, max_inferences_per_model=2)
        m = s.create_model("a", "text-generation", {})
        s.run_batch(m["id"], ["1", "2", "3", "4"])
        assert [i["input"] for i in s.list_inferences(m["id"])[0]] == ["3", "4"]
        s.close()

    def test_batch_is_ordered(self, store):
        m = store.create_model("a", "text-generation", {})
        out = store.run_batch(m["id"], ["x", "y", "z"])
        assert [i["input"] for i in out] == ["x", "y", "z"]
        assert [i["input"] for i in store.list_inferences(m["id"])[0]] == ["x", "y", "z"]

    def test_batch_rolls_back_on_failure(self, store, monkeypatch):
        m = store.create_model("a", "text-generation", {})
        calls = {"n": 0}

        def flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("engine blew up")
            return {"text": "ok"}

        monkeypatch.setattr("src.sqlite_store.run_engine", flaky)
        with pytest.raises(RuntimeError):
            store.run_batch(m["id"], ["a", "b", "c"])
        assert store.list_inferences(m["id"]) == ([], 0)
        # the store is still usable after the rollback
        assert store.run_inference(m["id"], "again") is not None

    def test_unicode_and_nested_config_roundtrip(self, store):
        cfg = {"note": "héllo ✓", "nested": {"a": [1, 2, {"b": None}]}}
        m = store.create_model("ü", "embedding", cfg)
        assert store.get_model(m["id"])["config"] == cfg
        inf = store.run_inference(m["id"], "日本語")
        assert store.get_inference(m["id"], inf["id"])["inf"]["input"] == "日本語"

    def test_threads_do_not_corrupt(self, store):
        m = store.create_model("a", "embedding", {})
        out: list[str] = []

        def work():
            for _ in range(25):
                out.append(store.run_inference(m["id"], "x")["id"])

        threads = [threading.Thread(target=work) for _ in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert len(set(out)) == 200
        assert store.stats()["inferences"] == 200


class TestDurability:
    def test_data_survives_reopen(self, db_path):
        first = SqliteStore(db_path)
        m = first.create_model("persist", "text-classification", {"k": 1})
        inf = first.run_inference(m["id"], "this is great")
        first.close()

        second = SqliteStore(db_path)
        assert second.get_model(m["id"]) == m
        assert second.get_inference(m["id"], inf["id"])["inf"] == inf
        assert second.create_model("persist", "embedding", {}) is None  # name still taken
        second.close()

    def test_insertion_order_survives_reopen(self, db_path):
        s = SqliteStore(db_path)
        for n in range(3):
            s.create_model(f"m{n}", "embedding", {})
        s.close()
        s = SqliteStore(db_path)
        assert [m["name"] for m in s.list_models()[0]] == ["m0", "m1", "m2"]
        s.close()

    def test_wal_mode_and_foreign_keys(self, db_path):
        s = SqliteStore(db_path)
        assert s._conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert s._conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        s.close()

    def test_schema_version_recorded(self, db_path):
        SqliteStore(db_path).close()
        raw = sqlite3.connect(db_path)
        assert raw.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        raw.close()

    def test_refuses_newer_schema(self, db_path):
        SqliteStore(db_path).close()
        raw = sqlite3.connect(db_path)
        raw.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        raw.commit()
        raw.close()
        with pytest.raises(RuntimeError, match="newer"):
            SqliteStore(db_path)

    def test_memory_database(self):
        s = SqliteStore(":memory:")
        m = s.create_model("a", "embedding", {})
        assert s.run_inference(m["id"], "x") is not None
        s.close()


class TestServerIntegration:
    def test_open_store_selects_backend(self, db_path):
        mem = open_store(Settings())
        assert mem.kind == "memory"
        db = open_store(Settings(database_path=db_path))
        assert db.kind == "sqlite"
        db.close()

    def test_api_persists_across_app_restarts(self, db_path):
        settings = Settings(database_path=db_path)
        with TestClient(build_app(settings=settings)) as c:
            mid = c.post("/models", json={"name": "keep", "type": "text-generation"}).json()[
                "data"
            ]["id"]
            iid = c.post(f"/models/{mid}/infer", json={"input": "hello"}).json()["data"]["id"]
            assert c.get("/health").json()["data"]["storage"] == "sqlite"

        with TestClient(build_app(settings=settings)) as c:  # a "restart"
            assert c.get(f"/models/{mid}").json()["data"]["name"] == "keep"
            got = c.get(f"/models/{mid}/inferences/{iid}").json()["data"]
            assert got["output"]["text"] == "Generated response for: hello"
            assert c.get("/health").json()["data"]["inferences"] == 1
            assert c.post("/models", json={"name": "keep", "type": "embedding"}).status_code == 409

    def test_full_api_on_sqlite(self, db_path):
        with TestClient(build_app(settings=Settings(database_path=db_path))) as c:
            mid = c.post("/models", json={"name": "g", "type": "text-generation"}).json()[
                "data"
            ]["id"]
            batch = c.post(f"/models/{mid}/infer/batch", json={"inputs": ["a", "b", "c"]})
            assert batch.status_code == 201
            page = c.get(f"/models/{mid}/inferences?limit=2&offset=1")
            assert [i["input"] for i in page.json()["data"]] == ["b", "c"]
            assert page.headers["x-total-count"] == "3"
            stream = c.post(f"/models/{mid}/infer/stream", json={"input": "x y"})
            assert "event: done" in stream.text
            assert c.delete(f"/models/{mid}").status_code == 200
            assert c.get(f"/models/{mid}/inferences").status_code == 404
            assert "stored_inferences 0" in c.get("/metrics").text

    def test_app_closes_store_it_opened(self, db_path):
        app = build_app(settings=Settings(database_path=db_path))
        with TestClient(app):
            pass
        raw = sqlite3.connect(db_path)  # file is released and readable
        assert raw.execute("SELECT COUNT(*) FROM models").fetchone()[0] == 0
        raw.close()

    def test_app_does_not_close_a_store_it_was_given(self, store):
        with TestClient(build_app(store=store)):
            pass
        assert store.create_model("still-open", "embedding", {}) is not None
