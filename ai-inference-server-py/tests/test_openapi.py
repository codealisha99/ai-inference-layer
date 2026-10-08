import json

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from openapi_spec_validator import validate

from src.config import Settings
from src.schemas import (
    DeletedResponse,
    ErrorResponse,
    HealthResponse,
    Inference,
    InferenceListResponse,
    InferenceResponse,
    ModelListResponse,
    ModelResponse,
    ProbeResponse,
)
from src.server import build_app


@pytest.fixture(scope="module")
def app():
    return build_app()


@pytest.fixture(scope="module")
def spec(app):
    return TestClient(app).get("/openapi.json").json()


@pytest.fixture
def client():
    with TestClient(build_app()) as c:
        yield c


class TestDocumentIsValid:
    def test_conforms_to_the_openapi_spec(self, spec):
        validate(spec)

    def test_metadata(self, spec):
        assert spec["info"]["title"] == "AI Inference Server"
        assert '{"success": bool' in spec["info"]["description"]
        assert {t["name"] for t in spec["tags"]} == {"models", "inference", "operations"}

    def test_every_ref_resolves(self, spec):
        def refs(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k == "$ref":
                        yield v
                    else:
                        yield from refs(v)
            elif isinstance(node, list):
                for item in node:
                    yield from refs(item)

        for ref in set(refs(spec)):
            assert ref.startswith("#/components/schemas/"), ref
            assert ref.rsplit("/", 1)[1] in spec["components"]["schemas"], ref

    def test_every_operation_is_tagged_summarised_and_has_a_success_response(self, spec):
        for path, item in spec["paths"].items():
            for method, op in item.items():
                where = f"{method.upper()} {path}"
                assert op.get("tags"), where
                assert op.get("summary"), where
                assert any(code.startswith("2") for code in op["responses"]), where

    def test_all_routes_are_documented(self, app, spec):
        documented = {(m.lower(), p) for p, item in spec["paths"].items() for m in item}
        expected = {
            (m.lower(), r.path)
            for r in app.routes
            if isinstance(r, APIRoute) and r.include_in_schema
            for m in r.methods
        }
        assert documented == expected
        assert len(documented) == 13

    def test_path_parameters_are_readable(self, spec):
        params = spec["paths"]["/models/{model_id}/inferences/{inference_id}"]["get"]["parameters"]
        assert {p["name"] for p in params} == {"model_id", "inference_id"}


class TestRequestsAreDocumented:
    @pytest.mark.parametrize(
        ("path", "schema"),
        [
            ("/models", "ModelCreate"),
            ("/models/{model_id}/infer", "InferRequest"),
            ("/models/{model_id}/infer/batch", "BatchRequest"),
            ("/models/{model_id}/infer/stream", "InferRequest"),
        ],
    )
    def test_post_bodies(self, spec, path, schema):
        body = spec["paths"][path]["post"]["requestBody"]
        assert body["required"] is True
        ref = body["content"]["application/json"]["schema"]["$ref"]
        assert ref == f"#/components/schemas/{schema}"

    @pytest.mark.parametrize("path", ["/models", "/models/{model_id}/inferences"])
    def test_list_endpoints_document_paging(self, spec, path):
        op = spec["paths"][path]["get"]
        assert {"limit", "offset"} <= {p["name"] for p in op["parameters"]}
        assert "X-Total-Count" in op["responses"]["200"]["headers"]

    def test_request_schemas_carry_constraints_and_examples(self, spec):
        schemas = spec["components"]["schemas"]
        assert schemas["BatchRequest"]["properties"]["inputs"]["minItems"] == 1
        assert schemas["InferRequest"]["properties"]["input"]["minLength"] == 1
        assert schemas["ModelCreate"]["properties"]["type"]["enum"] == [
            "text-generation",
            "text-classification",
            "embedding",
        ]
        assert schemas["ModelCreate"]["properties"]["name"]["examples"] == ["sentiment"]

    def test_stream_documents_event_stream(self, spec):
        ok = spec["paths"]["/models/{model_id}/infer/stream"]["post"]["responses"]["200"]
        assert "text/event-stream" in ok["content"]
        assert "event: token" in ok["content"]["text/event-stream"]["example"]

    def test_errors_use_the_envelope(self, spec):
        responses = spec["paths"]["/models"]["post"]["responses"]
        for code in ("400", "401", "409", "413", "429", "503"):
            ref = responses[code]["content"]["application/json"]["schema"]["$ref"]
            assert ref == "#/components/schemas/ErrorResponse"

    def test_document_is_cached_and_stable(self, app):
        assert app.openapi() is app.openapi()
        assert json.dumps(app.openapi(), sort_keys=True)


class TestRealResponsesMatchTheDocs:
    """The published models are the contract: every real response must validate against them."""

    def test_models_lifecycle(self, client):
        r = client.post(
            "/models", json={"name": "e", "type": "embedding", "config": {"dimensions": 3}}
        )
        assert r.status_code == 201
        model = ModelResponse.model_validate(r.json()).data
        assert model.config == {"dimensions": 3}
        ModelResponse.model_validate(client.get(f"/models/{model.id}").json())
        assert len(ModelListResponse.model_validate(client.get("/models").json()).data) == 1
        DeletedResponse.model_validate(client.delete(f"/models/{model.id}").json())

    @pytest.mark.parametrize(
        ("model_type", "input_text"),
        [
            ("text-generation", "hello"),
            ("text-classification", "not bad at all"),
            ("embedding", "vectors"),
        ],
    )
    def test_inference_of_each_type(self, client, model_type, input_text):
        mid = client.post("/models", json={"name": "m", "type": model_type}).json()["data"]["id"]
        r = client.post(f"/models/{mid}/infer", json={"input": input_text})
        inf = InferenceResponse.model_validate(r.json()).data
        assert inf.status == "completed"
        assert (
            type(inf.output).__name__
            == {
                "text-generation": "TextOutput",
                "text-classification": "ClassificationOutput",
                "embedding": "EmbeddingOutput",
            }[model_type]
        )
        InferenceResponse.model_validate(client.get(f"/models/{mid}/inferences/{inf.id}").json())

    def test_batch_history_and_stream(self, client):
        mid = client.post("/models", json={"name": "g", "type": "text-generation"}).json()["data"][
            "id"
        ]
        batch = client.post(f"/models/{mid}/infer/batch", json={"inputs": ["a", "b"]})
        assert len(InferenceListResponse.model_validate(batch.json()).data) == 2
        history = client.get(f"/models/{mid}/inferences?limit=1")
        assert len(InferenceListResponse.model_validate(history.json()).data) == 1
        stream = client.post(f"/models/{mid}/infer/stream", json={"input": "hi there"})
        done = [b for b in stream.text.split("\n\n") if b.startswith("event: done")][0]
        Inference.model_validate_json(done.split("data: ", 1)[1])

    def test_operations_endpoints(self, client):
        health = HealthResponse.model_validate(client.get("/health").json()).data
        assert health.storage == "memory"
        assert ProbeResponse.model_validate(client.get("/livez").json()).data.status == "alive"
        ready = ProbeResponse.model_validate(client.get("/readyz").json()).data
        assert (ready.status, ready.storage) == ("ready", "memory")

    @pytest.mark.parametrize(
        ("method", "path", "body", "status"),
        [
            ("get", "/models/nope", None, 404),
            ("get", "/nope", None, 404),
            ("put", "/models", None, 405),
            ("post", "/models", {"type": "embedding"}, 400),
            ("post", "/models/nope/infer", {"input": "x"}, 404),
            ("post", "/models/nope/infer/batch", {"inputs": ["x"]}, 404),
            ("get", "/models?limit=0", None, 400),
        ],
    )
    def test_errors_validate_as_the_error_envelope(self, client, method, path, body, status):
        r = getattr(client, method)(path, **({"json": body} if body is not None else {}))
        assert r.status_code == status
        parsed = ErrorResponse.model_validate(r.json())
        assert parsed.error

    def test_conflict_and_auth_errors_validate(self, client):
        client.post("/models", json={"name": "d", "type": "embedding"})
        dup = client.post("/models", json={"name": "d", "type": "embedding"})
        assert dup.status_code == 409
        ErrorResponse.model_validate(dup.json())
        with TestClient(build_app(settings=Settings(api_key="k"))) as c:
            r = c.get("/models")
        assert r.status_code == 401
        ErrorResponse.model_validate(r.json())


def test_docs_pages_render(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
