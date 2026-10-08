import pytest

from src.config import Settings


def test_defaults(monkeypatch):
    for k in ("HOST", "PORT", "LOG_LEVEL", "MAX_INPUT_CHARS", "MAX_MODELS"):
        monkeypatch.delenv(k, raising=False)
    s = Settings.from_env()
    assert s.port == 3000
    assert s.log_level == "info"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("PORT", "8080")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("MAX_MODELS", "5")
    s = Settings.from_env()
    assert (s.port, s.log_level, s.max_models) == (8080, "debug", 5)


@pytest.mark.parametrize("bad", ["abc", "0", "-1"])
def test_invalid_port(monkeypatch, bad):
    monkeypatch.setenv("PORT", bad)
    with pytest.raises(ValueError, match="PORT"):
        Settings.from_env()


def test_database_path(monkeypatch):
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    assert Settings.from_env().database_path is None
    monkeypatch.setenv("DATABASE_PATH", "/tmp/x.db")
    assert Settings.from_env().database_path == "/tmp/x.db"
    monkeypatch.setenv("DATABASE_PATH", "")
    assert Settings.from_env().database_path is None
