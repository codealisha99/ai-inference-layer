"""Deterministic, dependency-free inference engines.

Each engine is a pure function ``(input, config) -> output``. They stand in for real
model backends while keeping the API contract (and every response shape) identical to
the reference TypeScript implementation. Because they are deterministic, identical
requests always produce identical results, which makes the server easy to test.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Callable
from typing import Any

MODEL_TYPES: tuple[str, ...] = ("text-generation", "text-classification", "embedding")

DEFAULT_EMBEDDING_DIMENSIONS = 5
MAX_EMBEDDING_DIMENSIONS = 1024

_WORD_RE = re.compile(r"[a-z']+")

_POSITIVE = frozenset(
    "good great excellent amazing awesome love loved lovely happy wonderful fantastic "
    "best nice brilliant perfect enjoy enjoyed fun superb delightful positive".split()
)
_NEGATIVE = frozenset(
    "bad terrible awful horrible hate hated sad worst poor ugly boring disappointing "
    "broken slow annoying angry useless negative painful nasty".split()
)
_NEGATIONS = frozenset({"not", "no", "never", "isn't", "wasn't", "don't", "didn't", "can't"})


class ConfigError(ValueError):
    """Raised when a model ``config`` is invalid for its type."""


def validate_config(model_type: str, config: dict[str, Any]) -> None:
    """Validate type-specific config. Unknown keys are allowed (forward compatible)."""
    if model_type == "embedding" and "dimensions" in config:
        dims = config["dimensions"]
        if isinstance(dims, bool) or not isinstance(dims, int):
            raise ConfigError("config.dimensions must be an integer")
        if not 1 <= dims <= MAX_EMBEDDING_DIMENSIONS:
            raise ConfigError(f"config.dimensions must be between 1 and {MAX_EMBEDDING_DIMENSIONS}")
    if model_type == "text-generation" and "maxChars" in config:
        limit = config["maxChars"]
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ConfigError("config.maxChars must be a positive integer")


def _generate(inp: str, config: dict[str, Any]) -> dict[str, Any]:
    text = f"Generated response for: {inp}"
    limit = config.get("maxChars")
    if isinstance(limit, int) and not isinstance(limit, bool) and limit >= 1:
        text = text[:limit]
    return {"text": text}


def _classify(inp: str, _config: dict[str, Any]) -> dict[str, Any]:
    """Tiny lexicon sentiment classifier with simple negation handling."""
    score = 0
    negate = False
    for word in _WORD_RE.findall(inp.lower()):
        if word in _NEGATIONS:
            negate = True
            continue
        polarity = (word in _POSITIVE) - (word in _NEGATIVE)
        if polarity:
            score += -polarity if negate else polarity
        negate = False
    if score == 0:
        return {"label": "neutral", "score": 0.5}
    confidence = 0.5 + 0.5 * math.tanh(abs(score) / 2)
    return {
        "label": "positive" if score > 0 else "negative",
        "score": round(confidence, 4),
    }


def _embed(inp: str, config: dict[str, Any]) -> dict[str, Any]:
    """Hash-based embedding: stable, L2-normalised, any dimensionality."""
    dims = config.get("dimensions", DEFAULT_EMBEDDING_DIMENSIONS)
    values: list[float] = []
    counter = 0
    while len(values) < dims:
        digest = hashlib.sha256(f"{counter}:{inp}".encode()).digest()
        for i in range(0, len(digest), 4):
            raw = int.from_bytes(digest[i : i + 4], "big")
            values.append(raw / 0xFFFFFFFF * 2 - 1)
            if len(values) == dims:
                break
        counter += 1
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return {"embedding": [round(v / norm, 6) for v in values]}


_ENGINES: dict[str, Callable[[str, dict[str, Any]], dict[str, Any]]] = {
    "text-generation": _generate,
    "text-classification": _classify,
    "embedding": _embed,
}


def run_engine(model_type: str, inp: str, config: dict[str, Any]) -> dict[str, Any]:
    engine = _ENGINES.get(model_type)
    return engine(inp, config) if engine else {}
