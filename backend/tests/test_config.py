"""Tests for the centralized ``Settings`` model and its process-wide cache."""

import pytest

from config import Settings, get_settings


def test_defaults_with_no_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "CORS_ORIGINS",
        "DB_URL",
        "LLM_MODEL",
        "ROLE_DESCRIPTION",
        "SESSION_COOKIE_SECURE",
        "SESSION_IDLE_TIMEOUT_SECONDS",
        "MCP_REGISTRY_URL",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.cors_origins == ["http://localhost:3000"]
    assert settings.db_url == "sqlite:///a2flow.db"
    assert settings.llm_model == "gemini-3.5-flash"
    assert settings.session_cookie_secure is False
    assert settings.session_idle_timeout_seconds == 28800
    assert settings.mcp_registry_url == "https://registry.modelcontextprotocol.io"
    assert settings.reload is False


def test_cors_origins_splits_and_strips_comma_separated_string() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        cors_origins="http://a.example.com, http://b.example.com ,http://c.example.com",  # type: ignore[arg-type]
    )

    assert settings.cors_origins == [
        "http://a.example.com",
        "http://b.example.com",
        "http://c.example.com",
    ]


@pytest.mark.parametrize("raw", [None, "", "not-a-number"])
def test_session_idle_timeout_falls_back_on_missing_or_unparseable(
    raw: str | None,
) -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        session_idle_timeout_seconds=raw,  # type: ignore[arg-type]
    )

    assert settings.session_idle_timeout_seconds == 28800


def test_session_idle_timeout_accepts_valid_numeric_string() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        session_idle_timeout_seconds="60",  # type: ignore[arg-type]
    )

    assert settings.session_idle_timeout_seconds == 60


def test_get_settings_is_cached_until_cleared() -> None:
    first = get_settings()
    second = get_settings()
    assert first is second

    get_settings.cache_clear()

    third = get_settings()
    assert third is not first
