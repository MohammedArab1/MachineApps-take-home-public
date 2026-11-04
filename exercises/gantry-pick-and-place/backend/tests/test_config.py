"""Settings and environment parsing tests."""

from __future__ import annotations

from app.config import Settings, _as_bool


def test_as_bool() -> None:
    assert _as_bool(None, True) is True
    assert _as_bool(None, False) is False
    assert _as_bool("true", False) is True
    assert _as_bool("YES", False) is True
    assert _as_bool("0", True) is False
    assert _as_bool("off", True) is False


def test_settings_from_env(monkeypatch) -> None:
    monkeypatch.setenv("GANTRY_DB_URL", "sqlite:////tmp/test.db")
    monkeypatch.setenv("GANTRY_CORS_ORIGINS", "http://one, http://two")
    monkeypatch.setenv("GANTRY_ENABLE_DEV_TOOLS", "false")
    settings = Settings.from_env()
    assert settings.db_url == "sqlite:////tmp/test.db"
    assert settings.cors_origins == ("http://one", "http://two")
    assert settings.enable_dev_tools is False
