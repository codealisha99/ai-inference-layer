import pytest
from fastapi.testclient import TestClient

from src.config import Settings
from src.server import build_app


@pytest.fixture
def client():
    settings = Settings(max_input_chars=10, max_name_chars=8, max_models=2)
    with TestClient(build_app(settings=settings)) as c:
        yield c


def _mk(client, name="m", typ="embedding", **extra):
    return client.post("/models", json={"name": name, "type": typ, **extra})


class TestEnvelope:
    def test_unknown_route_uses_envelope(self, client):
        r = client.get("/nope")
        assert r.status_code == 404
        assert r.json() == {"success": False, "data": None, "error": "not found"}

    def test_wrong_method_uses_envelope(self, client):
        r = client.put("/models")
        assert r.status_code == 405
        assert r.json()["success"] is False

    def test_malformed_json_is_400(self, client):
        r = client.post(
            "/models", content=b"{not json", headers={"content-type": "application/json"}
        )
        assert r.status_code == 400
        assert r.json()["error"] == "name is required"

    def test_non_object_body_is_400(self, client):
        assert client.post("/models", json=[1, 2]).status_code == 400


class TestRequestContext:
    def test_generates_request_id(self, client):
        r = client.get("/health")
        assert len(r.headers["x-request-id"]) == 32
        assert float(r.headers["x-response-time-ms"]) >= 0

    def test_echoes_request_id(self, client):
        r = client.get("/health", headers={"x-request-id": "abc-123"})
        assert r.headers["x-request-id"] == "abc-123"

    def test_unhandled_error_becomes_500_envelope(self):
        app = build_app()

        @app.get("/boom")
        async def boom():
            raise RuntimeError("kaboom")

        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get("/boom")
        assert r.status_code == 500
        assert r.json()["error"] == "internal server error"
        assert "kaboom" not in r.text


class TestValidation:
    def test_name_must_be_string(self, client):
        assert _mk(client, name=123).json()["error"] == "name must be a string"

    def test_name_whitespace_only(self, client):
        assert _mk(client, name="   ").json()["error"] == "name is required"

    def test_name_is_trimmed(self, client):
        assert _mk(client, name="  ok  ").json()["data"]["name"] == "ok"

    def test_trimmed_duplicate_conflicts(self, client):
        _mk(client, name="ok")
        assert _mk(client, name=" ok ").status_code == 409

    def test_name_too_long(self, client):
        assert _mk(client, name="x" * 9).status_code == 400

    def test_type_must_be_string(self, client):
        assert _mk(client, typ=["embedding"]).status_code == 400

    def test_config_must_be_object(self, client):
        r = _mk(client, config="nope")
        assert r.status_code == 400
        assert r.json()["error"] == "config must be an object"

    def test_null_config_defaults_to_empty(self, client):
        assert _mk(client, config=None).json()["data"]["config"] == {}

    def test_bad_dimensions_rejected(self, client):
        r = _mk(client, config={"dimensions": 0})
        assert r.status_code == 400

    def test_model_limit_returns_429(self, client):
        _mk(client, "a")
        _mk(client, "b")
        assert _mk(client, "c").status_code == 429

    def test_input_must_be_string(self, client):
        mid = _mk(client).json()["data"]["id"]
        r = client.post(f"/models/{mid}/infer", json={"input": 5})
        assert r.status_code == 400
        assert r.json()["error"] == "input must be a string"

    def test_input_too_long_is_413(self, client):
        mid = _mk(client).json()["data"]["id"]
        r = client.post(f"/models/{mid}/infer", json={"input": "x" * 11})
        assert r.status_code == 413


class TestBehaviour:
    def test_embedding_uses_configured_dimensions(self, client):
        mid = _mk(client, config={"dimensions": 16}).json()["data"]["id"]
        out = client.post(f"/models/{mid}/infer", json={"input": "hi"}).json()["data"]["output"]
        assert len(out["embedding"]) == 16

    def test_classifier_detects_sentiment(self, client):
        mid = _mk(client, typ="text-classification").json()["data"]["id"]
        out = client.post(f"/models/{mid}/infer", json={"input": "so bad"}).json()["data"]["output"]
        assert out["label"] == "negative"

    def test_inference_records_latency(self, client):
        mid = _mk(client).json()["data"]["id"]
        inf = client.post(f"/models/{mid}/infer", json={"input": "hi"}).json()["data"]
        assert inf["latencyMs"] >= 0
        assert inf["completedAt"] >= inf["createdAt"]

    def test_deleting_model_removes_inferences(self, client):
        mid = _mk(client).json()["data"]["id"]
        iid = client.post(f"/models/{mid}/infer", json={"input": "hi"}).json()["data"]["id"]
        client.delete(f"/models/{mid}")
        assert client.get(f"/models/{mid}/inferences/{iid}").status_code == 404

    def test_health_reports_counts(self, client):
        mid = _mk(client).json()["data"]["id"]
        client.post(f"/models/{mid}/infer", json={"input": "hi"})
        data = client.get("/health").json()["data"]
        assert data["status"] == "ok"
        assert data["models"] == 1
        assert data["inferences"] == 1
        assert data["version"]

    def test_openapi_docs_available(self, client):
        assert client.get("/openapi.json").status_code == 200
