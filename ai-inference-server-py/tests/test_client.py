import pytest

from src.client import ApiError, Client, Page, ServerUnreachable


@pytest.fixture
def ais(live_server):
    return Client(live_server.url)


def test_health(ais):
    h = ais.health()
    assert h["status"] == "ok"
    assert h["storage"] == "sqlite"


def test_model_lifecycle(ais):
    m = ais.create_model("sent", "text-classification")
    assert ais.get_model(m["id"]) == m
    assert [x["name"] for x in ais.list_models()] == ["sent"]
    assert ais.delete_model(m["id"]) == {"id": m["id"], "removed": True}
    with pytest.raises(ApiError) as err:
        ais.get_model(m["id"])
    assert err.value.status == 404
    assert err.value.message == "model not found"


def test_create_with_config(ais):
    m = ais.create_model("emb", "embedding", {"dimensions": 12})
    assert len(ais.infer(m["id"], "x")["output"]["embedding"]) == 12


def test_validation_errors_surface_as_api_error(ais):
    with pytest.raises(ApiError) as err:
        ais.create_model("bad", "nope")
    assert err.value.status == 400
    ais.create_model("dup", "embedding")
    with pytest.raises(ApiError) as err:
        ais.create_model("dup", "embedding")
    assert err.value.status == 409


def test_find_model_by_id_and_name(ais):
    m = ais.create_model("findme", "embedding")
    assert ais.find_model(m["id"]) == m
    assert ais.find_model("findme") == m
    with pytest.raises(ApiError) as err:
        ais.find_model("ghost")
    assert err.value.status == 404
    assert "ghost" in err.value.message


def test_find_model_pages_through_many_models(ais):
    for n in range(5):
        ais.create_model(f"m{n}", "embedding")
    assert ais.find_model("m4")["name"] == "m4"


def test_infer_and_history(ais):
    m = ais.create_model("g", "text-generation")
    inf = ais.infer(m["id"], "hello")
    assert inf["output"]["text"] == "Generated response for: hello"
    assert ais.get_inference(m["id"], inf["id"]) == inf
    assert ais.list_inferences(m["id"]) == [inf]


def test_batch(ais):
    m = ais.create_model("b", "text-generation")
    out = ais.batch(m["id"], ["a", "b", "c"])
    assert [i["input"] for i in out] == ["a", "b", "c"]
    with pytest.raises(ApiError) as err:
        ais.batch(m["id"], [])
    assert err.value.status == 400


def test_pagination_total(ais):
    m = ais.create_model("p", "text-generation")
    ais.batch(m["id"], [str(n) for n in range(5)])
    page = ais.list_inferences(m["id"], limit=2, offset=1)
    assert isinstance(page, Page)
    assert [i["input"] for i in page] == ["1", "2"]
    assert page.total == 5


def test_stream_events_and_text(ais):
    m = ais.create_model("s", "text-generation")
    events = list(ais.stream(m["id"], "hello big world"))
    assert events[-1][0] == "done"
    assert events[-1][1]["output"]["text"] == "Generated response for: hello big world"
    assert [e for e, _ in events[:-1]] == ["token"] * (len(events) - 1)
    assert "".join(ais.stream_text(m["id"], "hello big world")) == events[-1][1]["output"]["text"]
    assert len(ais.list_inferences(m["id"])) == 2  # both streams were recorded


def test_stream_wrong_type_is_api_error(ais):
    m = ais.create_model("e", "embedding")
    with pytest.raises(ApiError) as err:
        list(ais.stream(m["id"], "x"))
    assert err.value.status == 400


def test_ids_with_odd_characters_are_escaped(ais):
    with pytest.raises(ApiError) as err:
        ais.get_model("a/b?c")
    assert err.value.status == 404


def test_metrics(ais):
    ais.health()
    assert "http_requests_total" in ais.metrics()


def test_unreachable(dead_url):
    with pytest.raises(ServerUnreachable, match="cannot reach"):
        Client(dead_url, timeout=2).health()


def test_api_key(secured_server):
    with pytest.raises(ApiError) as err:
        Client(secured_server.url).list_models()
    assert err.value.status == 401
    assert Client(secured_server.url, api_key="s3cret").list_models() == []
    assert Client(secured_server.url).health()["status"] == "ok"  # health is public


def test_base_url_trailing_slash(live_server):
    assert Client(live_server.url + "/").health()["status"] == "ok"
