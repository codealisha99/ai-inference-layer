import math

import pytest

from src.engines import ConfigError, run_engine, validate_config


class TestTextGeneration:
    def test_echoes_input(self):
        assert run_engine("text-generation", "hi", {}) == {"text": "Generated response for: hi"}

    def test_max_chars_truncates(self):
        out = run_engine("text-generation", "hello world", {"maxChars": 5})
        assert out["text"] == "Gener"


class TestClassification:
    @pytest.mark.parametrize(
        ("text", "label"),
        [
            ("I love this, it is great", "positive"),
            ("this is terrible and awful", "negative"),
            ("the table is made of wood", "neutral"),
            ("not good at all", "negative"),
            ("not bad", "positive"),
        ],
    )
    def test_labels(self, text, label):
        assert run_engine("text-classification", text, {})["label"] == label

    def test_score_is_float_in_range(self):
        out = run_engine("text-classification", "great great great", {})
        assert isinstance(out["score"], float)
        assert 0.5 < out["score"] < 1.0

    def test_more_evidence_means_higher_confidence(self):
        one = run_engine("text-classification", "good", {})["score"]
        three = run_engine("text-classification", "good great awesome", {})["score"]
        assert three > one


class TestEmbedding:
    def test_default_dimensions(self):
        assert len(run_engine("embedding", "x", {})["embedding"]) == 5

    @pytest.mark.parametrize("dims", [1, 8, 64, 1024])
    def test_custom_dimensions(self, dims):
        assert len(run_engine("embedding", "x", {"dimensions": dims})["embedding"]) == dims

    def test_deterministic(self):
        a = run_engine("embedding", "same", {"dimensions": 16})
        b = run_engine("embedding", "same", {"dimensions": 16})
        assert a == b

    def test_different_inputs_differ(self):
        a = run_engine("embedding", "one", {})["embedding"]
        b = run_engine("embedding", "two", {})["embedding"]
        assert a != b

    def test_unit_norm(self):
        vec = run_engine("embedding", "norm", {"dimensions": 32})["embedding"]
        assert math.isclose(math.sqrt(sum(v * v for v in vec)), 1.0, abs_tol=1e-3)


class TestValidateConfig:
    @pytest.mark.parametrize("bad", [0, -1, 1025, "8", 1.5, True])
    def test_bad_dimensions(self, bad):
        with pytest.raises(ConfigError):
            validate_config("embedding", {"dimensions": bad})

    @pytest.mark.parametrize("bad", [0, -3, "x", True])
    def test_bad_max_chars(self, bad):
        with pytest.raises(ConfigError):
            validate_config("text-generation", {"maxChars": bad})

    def test_unknown_keys_allowed(self):
        validate_config("embedding", {"whatever": 1})

    def test_type_specific(self):
        validate_config("text-classification", {"dimensions": -5})
