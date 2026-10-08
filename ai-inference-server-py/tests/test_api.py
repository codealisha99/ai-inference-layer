import pytest
from fastapi.testclient import TestClient

from src.server import build_app


@pytest.fixture
def app():
    return build_app()


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def _create_model(client, body=None):
    if body is None:
        body = {"name": "gpt-test", "type": "text-generation"}
    return client.post("/models", json=body)


def _model_id(resp):
    return resp.json()["data"]["id"]


class TestHealth:
    def test_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["success"] is True


class TestCreateModel:
    def test_returns_201(self, client):
        r = _create_model(client)
        assert r.status_code == 201
        assert r.json()["data"]["name"] == "gpt-test"

    def test_missing_name(self, client):
        r = client.post("/models", json={"type": "embedding"})
        assert r.status_code == 400

    def test_invalid_type(self, client):
        r = client.post("/models", json={"name": "x", "type": "badtype"})
        assert r.status_code == 400

    def test_missing_type(self, client):
        r = client.post("/models", json={"name": "x"})
        assert r.status_code == 400

    def test_duplicate_name(self, client):
        _create_model(client)
        r = _create_model(client)
        assert r.status_code == 409

    def test_all_valid_types(self, client):
        for t in ["text-generation", "text-classification", "embedding"]:
            r = client.post("/models", json={"name": t, "type": t})
            assert r.status_code == 201


class TestListModels:
    def test_empty(self, client):
        r = client.get("/models")
        assert r.status_code == 200
        assert r.json()["data"] == []

    def test_returns_all(self, client):
        client.post("/models", json={"name": "m1", "type": "embedding"})
        client.post("/models", json={"name": "m2", "type": "text-classification"})
        r = client.get("/models")
        assert len(r.json()["data"]) == 2


class TestGetModel:
    def test_returns_200(self, client):
        mid = _model_id(_create_model(client))
        r = client.get(f"/models/{mid}")
        assert r.status_code == 200

    def test_404(self, client):
        r = client.get("/models/nope")
        assert r.status_code == 404


class TestDeleteModel:
    def test_removes(self, client):
        mid = _model_id(_create_model(client))
        r = client.delete(f"/models/{mid}")
        assert r.status_code == 200
        assert client.get(f"/models/{mid}").status_code == 404

    def test_404(self, client):
        assert client.delete("/models/nope").status_code == 404


class TestInfer:
    def test_completed_output(self, client):
        mid = _model_id(_create_model(client))
        r = client.post(f"/models/{mid}/infer", json={"input": "hello"})
        assert r.status_code == 201
        assert r.json()["data"]["status"] == "completed"
        assert r.json()["data"]["output"] is not None

    def test_text_generation(self, client):
        mid = _model_id(client.post("/models", json={"name": "gen", "type": "text-generation"}))
        r = client.post(f"/models/{mid}/infer", json={"input": "hi"})
        assert r.json()["data"]["output"]["text"]

    def test_classification(self, client):
        mid = _model_id(client.post("/models", json={"name": "cls", "type": "text-classification"}))
        r = client.post(f"/models/{mid}/infer", json={"input": "hi"})
        assert r.json()["data"]["output"]["label"]
        assert isinstance(r.json()["data"]["output"]["score"], float)

    def test_embedding(self, client):
        mid = _model_id(client.post("/models", json={"name": "emb", "type": "embedding"}))
        r = client.post(f"/models/{mid}/infer", json={"input": "hi"})
        assert isinstance(r.json()["data"]["output"]["embedding"], list)

    def test_missing_input(self, client):
        mid = _model_id(_create_model(client))
        r = client.post(f"/models/{mid}/infer", json={})
        assert r.status_code == 400

    def test_unknown_model(self, client):
        r = client.post("/models/nope/infer", json={"input": "hi"})
        assert r.status_code == 404


class TestListInferences:
    def test_returns_list(self, client):
        mid = _model_id(_create_model(client))
        client.post(f"/models/{mid}/infer", json={"input": "a"})
        client.post(f"/models/{mid}/infer", json={"input": "b"})
        r = client.get(f"/models/{mid}/inferences")
        assert r.status_code == 200
        assert len(r.json()["data"]) == 2

    def test_404(self, client):
        assert client.get("/models/nope/inferences").status_code == 404


class TestGetInference:
    def test_returns_by_id(self, client):
        mid = _model_id(_create_model(client))
        ir = client.post(f"/models/{mid}/infer", json={"input": "x"})
        inf_id = ir.json()["data"]["id"]
        r = client.get(f"/models/{mid}/inferences/{inf_id}")
        assert r.status_code == 200

    def test_unknown_inference(self, client):
        mid = _model_id(_create_model(client))
        assert client.get(f"/models/{mid}/inferences/nope").status_code == 404

    def test_unknown_model(self, client):
        assert client.get("/models/nope/inferences/x").status_code == 404
