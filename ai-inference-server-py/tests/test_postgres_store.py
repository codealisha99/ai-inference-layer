"""Integration checks; TEST_DATABASE_URL must point to a dedicated test database."""

import os
import threading

import psycopg
import pytest
from fastapi.testclient import TestClient

from src.config import Settings
from src.inference import StoreFull
from src.postgres_store import PostgresStore
from src.server import build_app


@pytest.fixture
def database_url():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    store = PostgresStore(url)
    store._conn.execute("TRUNCATE inferences, models RESTART IDENTITY CASCADE")
    store.close()
    yield url
    store = PostgresStore(url)
    store._conn.execute("TRUNCATE inferences, models RESTART IDENTITY CASCADE")
    store.close()


@pytest.fixture
def store(database_url):
    backend = PostgresStore(database_url)
    yield backend
    backend.close()


def test_models_and_history_survive_reconnect(store, database_url):
    model = store.create_model("日本語", "embedding", {"dimensions": 4, "nested": [None]})
    result = store.run_inference(model["id"], "héllo ✓")
    with TestClient(build_app(settings=Settings(database_url=database_url))) as client:
        assert client.get("/readyz").json()["data"]["storage"] == "postgres"
        assert client.get("/health").json()["data"]["storage"] == "postgres"
        assert client.get(f"/models/{model['id']}").json()["data"] == model
        assert (
            client.get(f"/models/{model['id']}/inferences/{result['id']}").json()["data"] == result
        )
    assert store.create_model("日本語", "embedding", {}) is None
    assert store.stats() == {"models": 1, "inferences": 1}
    assert store.ping()


def test_pagination_and_history_eviction(database_url):
    backend = PostgresStore(database_url, max_inferences_per_model=2)
    try:
        models = [backend.create_model(str(n), "text-generation", {}) for n in range(3)]
        assert backend.list_models(1, 1) == ([models[1]], 3)
        assert backend.list_models()[1] == 3
        results = backend.run_batch(models[0]["id"], ["a", "b", "c"])
        assert backend.list_inferences(models[0]["id"]) == (results[1:], 2)
        assert backend.list_inferences(models[0]["id"], 1, 1) == ([results[2]], 2)
        assert backend.get_inference(models[0]["id"], results[0]["id"])["inf"] is None
        assert backend.delete_model(models[0]["id"])
        assert not backend.delete_model(models[0]["id"])
        assert backend.stats() == {"models": 2, "inferences": 0}
    finally:
        backend.close()


def test_unknown_ids(store):
    assert store.get_model("unknown") is None
    assert store.run_inference("unknown", "hello") is None
    assert store.run_batch("unknown", ["hello"]) is None
    assert store.list_inferences("unknown") is None
    assert store.get_inference("unknown", "unknown") == {"modelFound": False}


def test_capacity_is_shared_across_connections(database_url):
    first = PostgresStore(database_url, max_models=1)
    second = PostgresStore(database_url, max_models=1)
    try:
        first.create_model("first", "embedding", {})
        with pytest.raises(StoreFull):
            second.create_model("second", "embedding", {})
    finally:
        first.close()
        second.close()


def test_batch_failure_rolls_back(store, monkeypatch):
    model = store.create_model("rollback", "embedding", {})
    calls = 0

    def fail_on_second(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("engine failed")
        return {"embedding": [1.0]}

    monkeypatch.setattr("src.postgres_store.run_engine", fail_on_second)
    with pytest.raises(RuntimeError):
        store.run_batch(model["id"], ["a", "b"])
    assert store.list_inferences(model["id"]) == ([], 0)
    assert store.run_inference(model["id"], "retry") is not None


def test_concurrent_duplicate_names(database_url):
    stores = [PostgresStore(database_url) for _ in range(2)]
    results = []
    try:
        threads = [
            threading.Thread(
                target=lambda s=s: results.append(s.create_model("concurrent", "embedding", {}))
            )
            for s in stores
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len(results) == 2
        assert sum(result is not None for result in results) == 1
    finally:
        for backend in stores:
            backend.close()


def test_storage_errors_return_503(store, monkeypatch):
    with TestClient(build_app(store=store)) as client:

        def fail():
            raise psycopg.OperationalError("database unavailable")

        monkeypatch.setattr(store, "stats", fail)
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json()["error"] == "storage temporarily unavailable"
    store.close()
    assert not store.ping()


def test_database_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://pooled")
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", "postgresql://direct")
    settings = Settings.from_env()
    assert settings.database_url == "postgresql://pooled"
    assert settings.database_url_unpooled == "postgresql://direct"


def test_closed_connection_recovers_without_losing_history(store):
    model = store.create_model("recovery", "embedding", {})
    inference = store.run_inference(model["id"], "before disconnect")
    store._conn.close()
    assert store.ping()
    assert store.get_model(model["id"]) == model
    assert store.get_inference(model["id"], inference["id"])["inf"] == inference
    store._conn.close()
    assert store.run_inference(model["id"], "after disconnect") is not None
    assert store.stats() == {"models": 1, "inferences": 2}


def test_server_disconnection_recovers_on_next_request(store, database_url):
    model = store.create_model("terminated-session", "embedding", {})
    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute("SELECT pg_terminate_backend(%s)", (store._conn.info.backend_pid,))
    with TestClient(build_app(store=store)) as client:
        assert client.get("/health").status_code == 503
        assert client.get("/readyz").status_code == 200
        assert client.get(f"/models/{model['id']}").json()["data"] == model


def test_explicit_shutdown_does_not_reconnect(store):
    store.close()
    assert not store.ping()
    with pytest.raises(psycopg.OperationalError, match="store is closed"):
        store.stats()
