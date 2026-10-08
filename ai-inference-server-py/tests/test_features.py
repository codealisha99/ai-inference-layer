import json

import pytest
from fastapi.testclient import TestClient

from src.config import Settings
from src.server import build_app


@pytest.fixture
def client():
    with TestClient(build_app(settings=Settings(max_batch_size=3))) as c:
        yield c


def _mk(client, name="m", typ="text-generation", **extra):
    return client.post("/models", json={"name": name, "type": typ, **extra}).json()["data"]["id"]


def _events(text):
    out = []
    for block in text.strip().split("\n\n"):
        event, data = "message", None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        out.append((event, data))
    return out


class TestPagination:
    def test_models_limit_offset_and_total_header(self, client):
        for n in range(5):
            _mk(client, f"m{n}")
        r = client.get("/models?limit=2&offset=1")
        assert [m["name"] for m in r.json()["data"]] == ["m1", "m2"]
        assert r.headers["x-total-count"] == "5"

    def test_no_params_returns_everything(self, client):
        for n in range(5):
            _mk(client, f"m{n}")
        assert len(client.get("/models").json()["data"]) == 5

    @pytest.mark.parametrize("qs", ["limit=0", "limit=abc", "limit=1001", "offset=-1", "offset=x"])
    def test_bad_params(self, client, qs):
        assert client.get(f"/models?{qs}").status_code == 400

    def test_inferences_paginate(self, client):
        mid = _mk(client)
        for n in range(4):
            client.post(f"/models/{mid}/infer", json={"input": str(n)})
        r = client.get(f"/models/{mid}/inferences?limit=2&offset=2")
        assert [i["input"] for i in r.json()["data"]] == ["2", "3"]
        assert r.headers["x-total-count"] == "4"

    def test_inference_pagination_404(self, client):
        assert client.get("/models/nope/inferences?limit=1").status_code == 404


class TestBatch:
    def test_runs_all_inputs(self, client):
        mid = _mk(client)
        r = client.post(f"/models/{mid}/infer/batch", json={"inputs": ["a", "b"]})
        assert r.status_code == 201
        assert [i["input"] for i in r.json()["data"]] == ["a", "b"]
        assert len(client.get(f"/models/{mid}/inferences").json()["data"]) == 2

    @pytest.mark.parametrize(
        "body", [{}, {"inputs": []}, {"inputs": "x"}, {"inputs": ["a", ""]}, {"inputs": ["a", 1]}]
    )
    def test_invalid(self, client, body):
        mid = _mk(client)
        assert client.post(f"/models/{mid}/infer/batch", json=body).status_code == 400

    def test_invalid_batch_stores_nothing(self, client):
        mid = _mk(client)
        client.post(f"/models/{mid}/infer/batch", json={"inputs": ["ok", ""]})
        assert client.get(f"/models/{mid}/inferences").json()["data"] == []

    def test_size_limit(self, client):
        mid = _mk(client)
        r = client.post(f"/models/{mid}/infer/batch", json={"inputs": ["a"] * 4})
        assert r.status_code == 400

    def test_unknown_model(self, client):
        assert client.post("/models/nope/infer/batch", json={"inputs": ["a"]}).status_code == 404


class TestStreaming:
    def test_token_events_then_done(self, client):
        mid = _mk(client)
        r = client.post(f"/models/{mid}/infer/stream", json={"input": "hello world"})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events = _events(r.text)
        tokens = [d["token"] for e, d in events if e == "token"]
        assert "".join(tokens) == "Generated response for: hello world"
        assert events[-1][0] == "done"
        assert events[-1][1]["status"] == "completed"

    def test_stream_is_recorded(self, client):
        mid = _mk(client)
        client.post(f"/models/{mid}/infer/stream", json={"input": "x"})
        assert len(client.get(f"/models/{mid}/inferences").json()["data"]) == 1

    def test_only_text_generation(self, client):
        mid = _mk(client, "e", "embedding")
        r = client.post(f"/models/{mid}/infer/stream", json={"input": "x"})
        assert r.status_code == 400

    def test_unknown_model_and_missing_input(self, client):
        assert client.post("/models/nope/infer/stream", json={"input": "x"}).status_code == 404
        mid = _mk(client)
        assert client.post(f"/models/{mid}/infer/stream", json={}).status_code == 400


class TestMetrics:
    def test_prometheus_output(self, client):
        mid = _mk(client)
        client.post(f"/models/{mid}/infer", json={"input": "x"})
        client.get("/models/nope")
        r = client.get("/metrics")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")
        body = r.text
        assert (
            'http_requests_total{method="POST",route="/models/{model_id}/infer",status="201"} 1'
            in body
        )
        assert 'status="404"' in body
        assert 'inferences_total{model_type="text-generation"} 1' in body
        assert "models 1" in body
        assert 'http_request_duration_seconds_bucket{le="+Inf"}' in body

    def test_unmatched_routes_do_not_explode_cardinality(self, client):
        client.get("/a/b/c")
        client.get("/d/e/f")
        assert 'route="unmatched"' in client.get("/metrics").text
        assert "/a/b/c" not in client.get("/metrics").text


class TestAuth:
    @pytest.fixture
    def secured(self):
        with TestClient(build_app(settings=Settings(api_key="s3cret"))) as c:
            yield c

    def test_rejects_missing_key(self, secured):
        r = secured.get("/models")
        assert r.status_code == 401
        assert r.headers["www-authenticate"] == "Bearer"
        assert r.json()["error"] == "unauthorized"

    def test_rejects_wrong_key(self, secured):
        assert secured.get("/models", headers={"x-api-key": "nope"}).status_code == 401

    def test_accepts_x_api_key(self, secured):
        assert secured.get("/models", headers={"x-api-key": "s3cret"}).status_code == 200

    def test_accepts_bearer(self, secured):
        r = secured.get("/models", headers={"authorization": "Bearer s3cret"})
        assert r.status_code == 200

    def test_health_and_docs_stay_public(self, secured):
        assert secured.get("/health").status_code == 200
        assert secured.get("/openapi.json").status_code == 200

    def test_metrics_protected(self, secured):
        assert secured.get("/metrics").status_code == 401
        assert secured.get("/metrics", headers={"x-api-key": "s3cret"}).status_code == 200

    def test_no_key_configured_means_open(self, client):
        assert client.get("/models").status_code == 200
