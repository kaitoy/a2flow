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


@pytest.mark.parametrize(
    "field",
    ["app_base_url", "smtp_enabled", "smtp_port", "smtp_host", "smtp_from_email"],
)
def test_blank_system_settings_env_var_is_treated_as_unset(field: str) -> None:
    settings = Settings(_env_file=None, **{field: ""})  # type: ignore[call-arg,arg-type]

    assert getattr(settings, field) is None


def test_app_base_url_and_smtp_env_vars_default_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # config.Settings always reads real os.environ regardless of _env_file:
    # main.py's module-level load_dotenv() writes backend/.env's contents
    # straight into os.environ the first time anything in the same
    # pytest-xdist worker imports main, which then persists for the rest of
    # that worker's test run. Without clearing these explicitly, a developer
    # with real SMTP credentials configured in their local backend/.env would
    # see this test fail depending on test order.
    for var in (
        "APP_BASE_URL",
        "SMTP_ENABLED",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_SECURITY",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM_EMAIL",
        "SMTP_FROM_NAME",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.app_base_url is None
    assert settings.smtp_enabled is None
    assert settings.smtp_host is None
    assert settings.smtp_port is None
    assert settings.smtp_security is None
    assert settings.smtp_username is None
    assert settings.smtp_password is None
    assert settings.smtp_from_email is None
    assert settings.smtp_from_name is None
