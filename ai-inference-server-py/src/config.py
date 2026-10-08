from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value < 1:
        raise ValueError(f"{name} must be >= 1, got {value}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "0.0.0.0"  # noqa: S104 - intended for container use
    port: int = 3000
    log_level: str = "info"
    max_input_chars: int = 100_000
    max_name_chars: int = 128
    max_models: int = 1_000
    max_inferences_per_model: int = 1_000
    max_batch_size: int = 64
    api_key: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        d = cls()
        return cls(
            host=os.getenv("HOST", d.host),
            port=_int_env("PORT", d.port),
            log_level=os.getenv("LOG_LEVEL", d.log_level).lower(),
            max_input_chars=_int_env("MAX_INPUT_CHARS", d.max_input_chars),
            max_name_chars=_int_env("MAX_NAME_CHARS", d.max_name_chars),
            max_models=_int_env("MAX_MODELS", d.max_models),
            max_inferences_per_model=_int_env(
                "MAX_INFERENCES_PER_MODEL", d.max_inferences_per_model
            ),
            max_batch_size=_int_env("MAX_BATCH_SIZE", d.max_batch_size),
            api_key=os.getenv("API_KEY") or None,
        )
