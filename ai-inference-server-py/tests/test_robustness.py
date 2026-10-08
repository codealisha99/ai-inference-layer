import json
import logging
import sqlite3

import pytest
from fastapi.testclient import TestClient

from src.config import Settings
from src.inference import InferenceStore
from src.logging_config import JsonFormatter, configure_logging
from src.server import build_app


def _client(**settings):
    return TestClient(build_app(settings=Settings(**settings)))


class TestBodyLimit:
    def test_declared_oversize_is_413_without_reading(self):
        with _client(max_body_bytes=100) as c:
            r = c.post("/models", content=b"x" * 101, headers={"content-type": "application/json"})
        assert r.status_code == 413
        assert r.json() == {
            "success": False,
            "data": None,
            "error": "request body too large (max 100 bytes)",
        }

    def test_chunked_oversize_without_content_length_is_413(self):
        def chunks():
            for _ in range(10):
                yield b'{"name":' + b"x" * 20

        with _client(max_body_bytes=100) as c:
            r = c.post("/models", content=chunks(), headers={"content-type": "application/json"})
        assert r.status_code == 413

    def test_body_at_the_limit_is_accepted(self):
        body = json.dumps({"name": "a", "type": "embedding"}).encode()
        with _client(max_body_bytes=len(body)) as c:
            r = c.post("/models", content=body, headers={"content-type": "application/json"})
        assert r.status_code == 201

    def test_one_byte_over_is_rejected(self):
        body = json.dumps({"name": "a", "type": "embedding"}).encode()
        with _client(max_body_bytes=len(body) - 1) as c:
            r = c.post("/models", content=body, headers={"content-type": "application/json"})
        assert r.status_code == 413

    @pytest.mark.parametrize("path", ["/infer", "/infer/batch", "/infer/stream"])
    def test_applies_to_inference_routes(self, path):
        with _client(max_body_bytes=200) as c:
            mid = c.post("/models", json={"name": "g", "type": "text-generation"}).json()["data"][
                "id"
            ]
            r = c.post(f"/models/{mid}{path}", json={"input": "x" * 500, "inputs": ["y" * 500]})
        assert r.status_code == 413

    def test_oversize_requests_are_counted_in_metrics(self):
        with _client(max_body_bytes=50) as c:
            c.post("/models", json={"name": "x" * 100, "type": "embedding"})
            assert 'status="413"' in c.get("/metrics").text

    def test_413_still_gets_request_id_and_security_headers(self):
        with _client(max_body_bytes=50) as c:
            r = c.post("/models", json={"name": "x" * 100, "type": "embedding"})
        assert r.headers["x-request-id"]
        assert r.headers["x-content-type-options"] == "nosniff"

    def test_get_requests_are_not_affected(self):
        with _client(max_body_bytes=1) as c:
            assert c.get("/models").status_code == 200

    def test_settings_from_env(self, monkeypatch):
        monkeypatch.setenv("MAX_BODY_BYTES", "2048")
        assert Settings.from_env().max_body_bytes == 2048


class TestRequestId:
    @pytest.mark.parametrize("bad", ["has space", "semi;colon", "x" * 129, "<script>", "a\tb"])
    def test_unsafe_ids_are_replaced(self, bad):
        with _client() as c:
            r = c.get("/health", headers={"x-request-id": bad})
        assert r.headers["x-request-id"] != bad
        assert len(r.headers["x-request-id"]) == 32

    @pytest.mark.parametrize("good", ["abc-123", "a.b_c", "X" * 128, "0123456789"])
    def test_safe_ids_are_kept(self, good):
        with _client() as c:
            assert c.get("/health", headers={"x-request-id": good}).headers["x-request-id"] == good


class TestSecurityHeaders:
    def test_api_responses(self):
        with _client() as c:
            for path in ("/health", "/models", "/nope"):
                r = c.get(path)
                assert r.headers["x-content-type-options"] == "nosniff"
                assert r.headers["x-frame-options"] == "DENY"
                assert r.headers["referrer-policy"] == "no-referrer"
                assert r.headers["cache-control"] == "no-store"

    def test_docs_and_error_responses_have_them_too(self):
        with _client(api_key="k") as c:
            assert c.get("/models").headers["x-content-type-options"] == "nosniff"  # 401
            assert c.get("/docs").headers["x-content-type-options"] == "nosniff"

    def test_docs_are_cacheable(self):
        with _client() as c:
            assert "cache-control" not in c.get("/docs").headers


class TestCors:
    def test_disabled_by_default(self):
        with _client() as c:
            r = c.get("/health", headers={"origin": "https://app.example"})
        assert "access-control-allow-origin" not in r.headers

    def test_allowed_origin(self):
        with _client(cors_origins=("https://app.example",)) as c:
            r = c.get("/health", headers={"origin": "https://app.example"})
        assert r.headers["access-control-allow-origin"] == "https://app.example"
        assert "x-total-count" in r.headers["access-control-expose-headers"]

    def test_other_origin_is_not_allowed(self):
        with _client(cors_origins=("https://app.example",)) as c:
            r = c.get("/health", headers={"origin": "https://evil.example"})
        assert "access-control-allow-origin" not in r.headers

    def test_preflight(self):
        with _client(cors_origins=("https://app.example",), api_key="k") as c:
            r = c.options(
                "/models",
                headers={
                    "origin": "https://app.example",
                    "access-control-request-method": "POST",
                    "access-control-request-headers": "x-api-key,content-type",
                },
            )
        assert r.status_code == 200  # answered before auth, as browsers require
        assert "x-api-key" in r.headers["access-control-allow-headers"]
        assert "POST" in r.headers["access-control-allow-methods"]

    def test_env_parsing(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", " https://a.example , https://b.example ,, ")
        assert Settings.from_env().cors_origins == ("https://a.example", "https://b.example")
        monkeypatch.setenv("CORS_ORIGINS", "")
        assert Settings.from_env().cors_origins == ()


class _FailingStore(InferenceStore):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error
        self.healthy = True

    def list_models(self, limit=None, offset=0):
        raise self.error

    def ping(self) -> bool:
        return self.healthy


class TestProbes:
    def test_livez_never_touches_storage(self):
        store = _FailingStore(sqlite3.OperationalError("disk I/O error"))
        store.healthy = False
        with TestClient(build_app(store=store)) as c:
            r = c.get("/livez")
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "alive"

    def test_readyz_ok(self):
        with _client() as c:
            r = c.get("/readyz")
        assert r.status_code == 200
        assert r.json()["data"] == {"status": "ready", "storage": "memory"}

    def test_readyz_503_when_storage_is_down(self):
        store = _FailingStore(sqlite3.OperationalError("x"))
        store.healthy = False
        with TestClient(build_app(store=store)) as c:
            r = c.get("/readyz")
        assert r.status_code == 503
        assert r.headers["retry-after"] == "1"
        assert r.json()["error"] == "storage unavailable"

    def test_probes_are_public_when_an_api_key_is_set(self):
        with _client(api_key="k") as c:
            assert c.get("/livez").status_code == 200
            assert c.get("/readyz").status_code == 200
            assert c.get("/models").status_code == 401

    def test_sqlite_store_ping(self, tmp_path):
        from src.sqlite_store import SqliteStore

        s = SqliteStore(str(tmp_path / "p.db"))
        assert s.ping() is True
        s.close()
        assert s.ping() is False  # closed connection -> not ready


class TestStorageFailure:
    def test_database_errors_become_503_not_500(self):
        store = _FailingStore(sqlite3.OperationalError("database is locked"))
        with TestClient(build_app(store=store), raise_server_exceptions=False) as c:
            r = c.get("/models")
        assert r.status_code == 503
        assert r.headers["retry-after"] == "1"
        assert r.json() == {
            "success": False,
            "data": None,
            "error": "storage temporarily unavailable",
        }
        assert "locked" not in r.text  # internals are not leaked

    def test_other_errors_are_still_500(self):
        store = _FailingStore(RuntimeError("boom"))
        with TestClient(build_app(store=store), raise_server_exceptions=False) as c:
            assert c.get("/models").status_code == 500


class TestJsonLogging:
    def test_formatter_emits_one_json_object(self):
        rec = logging.LogRecord("x", logging.INFO, "f", 1, "hello %s", ("world",), None)
        rec.request_id = "abc"
        out = json.loads(JsonFormatter().format(rec))
        assert out["message"] == "hello world"
        assert out["level"] == "info"
        assert out["request_id"] == "abc"
        assert out["ts"].endswith("+00:00")

    def test_formatter_includes_exceptions(self):
        try:
            raise ValueError("bad")
        except ValueError:
            import sys

            rec = logging.LogRecord("x", logging.ERROR, "f", 1, "oops", (), sys.exc_info())
        assert "ValueError: bad" in json.loads(JsonFormatter().format(rec))["exception"]

    def test_access_log_carries_structured_fields(self, capsys):
        configure_logging("info", "json")
        try:
            with _client() as c:
                c.get("/health", headers={"x-request-id": "req-1"})
            lines = [
                json.loads(ln)
                for ln in capsys.readouterr().err.splitlines()
                if ln.startswith("{") and '"path"' in ln
            ]
        finally:
            configure_logging("warning", "text")
        entry = lines[-1]
        assert entry["request_id"] == "req-1"
        assert entry["method"] == "GET"
        assert entry["path"] == "/health"
        assert entry["status"] == 200
        assert entry["duration_ms"] >= 0

    def test_text_format_is_default(self, monkeypatch):
        monkeypatch.delenv("LOG_FORMAT", raising=False)
        assert Settings.from_env().log_format == "text"

    def test_invalid_log_format_fails_fast(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "xml")
        with pytest.raises(ValueError, match="LOG_FORMAT"):
            Settings.from_env()
