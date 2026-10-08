import threading

import pytest

from src.inference import InferenceStore, StoreFull


def test_delete_frees_name():
    s = InferenceStore()
    m = s.create_model("a", "embedding", {})
    assert s.create_model("a", "embedding", {}) is None
    assert s.delete_model(m["id"])
    assert s.create_model("a", "embedding", {}) is not None


def test_model_limit():
    s = InferenceStore(max_models=2)
    s.create_model("a", "embedding", {})
    s.create_model("b", "embedding", {})
    with pytest.raises(StoreFull):
        s.create_model("c", "embedding", {})


def test_inference_history_is_bounded_and_evicts_oldest():
    s = InferenceStore(max_inferences_per_model=3)
    m = s.create_model("a", "text-generation", {})
    ids = [s.run_inference(m["id"], f"i{n}")["id"] for n in range(5)]
    items, total = s.list_inferences(m["id"])
    assert [i["id"] for i in items] == ids[2:]
    assert total == 3
    assert s.get_inference(m["id"], ids[0])["inf"] is None


def test_ids_unique_under_threads():
    s = InferenceStore()
    m = s.create_model("a", "embedding", {})
    out: list[str] = []

    def work():
        for _ in range(100):
            out.append(s.run_inference(m["id"], "x")["id"])

    threads = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(set(out)) == 800


def test_stats():
    s = InferenceStore()
    m = s.create_model("a", "embedding", {})
    s.run_inference(m["id"], "x")
    assert s.stats() == {"models": 1, "inferences": 1}


def test_pagination():
    s = InferenceStore()
    for n in range(5):
        s.create_model(f"m{n}", "embedding", {})
    page, total = s.list_models(limit=2, offset=1)
    assert [m["name"] for m in page] == ["m1", "m2"]
    assert total == 5
    assert s.list_models(offset=10)[0] == []


def test_batch_is_ordered_and_unknown_model_is_none():
    s = InferenceStore()
    m = s.create_model("a", "text-generation", {})
    out = s.run_batch(m["id"], ["x", "y", "z"])
    assert [i["input"] for i in out] == ["x", "y", "z"]
    assert s.run_batch("nope", ["x"]) is None
