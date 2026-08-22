"""Centralized application configuration.

Collects every environment variable the running application reads (server
bind settings, CORS, database, agent skill store, LLM selection, admin
bootstrap, demo data, secret encryption, HashiCorp Vault, MCP registry,
platform SMTP bootstrap, and session auth) into a single :class:`Settings`
model instead of scattered ``os.getenv`` calls. Values with side-effecting
fallback behavior (random admin password generation, Fernet key
generation/persistence) are left to the modules that own that behavior; this
model only resolves the plain configuration value.

``scripts/export_openapi.py``'s ``OPENAPI_OUTPUT`` is intentionally excluded:
that script is a standalone dev-time CLI tool outside the running
application, and keeps reading its own environment variable directly.

``infrastructure/password.py``'s ``BCRYPT_ROUNDS`` is also intentionally
excluded and reads ``os.environ`` directly, uncached. ``hash_password`` is
invoked from test-fixture setup code (``tests/_seed.py``'s ``seed_users``,
via ``infrastructure.bootstrap.seed_system_user``) before many tests set
their own env vars in the test body; going through this module's
``lru_cache``d :func:`get_settings` there would build and freeze the whole
``Settings`` singleton at that early point, before those later
``monkeypatch.setenv`` calls (e.g. for ``ADMIN_PASSWORD``) take effect.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

#: Fallback sliding idle timeout (8 hours) used when
#: ``SESSION_IDLE_TIMEOUT_SECONDS`` is unset or not a valid integer.
_DEFAULT_IDLE_TIMEOUT_SECONDS = 28800

#: How long (1 hour) a published skill revision directory is kept from pruning
#: regardless of whether anything references it. A workflow run reads the
#: skill's current ``commit_sha`` and inserts its WorkflowExecution row a moment
#: later; the grace window covers that gap, so a concurrent pull cannot delete
#: the revision the run just picked before the row naming it exists.
_DEFAULT_PRUNE_GRACE_SECONDS = 3600

#: Default per-request (connect/read) timeout, in seconds, for a skill clone's
#: HTTP requests. Bounds how long a slow or hanging remote can keep the sync
#: job stuck: the job holds the skill's advisory lock for the duration of the
#: clone, so an unbounded clone leaves the skill ``pending`` forever and, on
#: another replica, makes a pull of the same skill silently no-op (it skips
#: rather than waits when the lock is held, see ``_LOCK_WAIT_SECONDS`` in
#: ``services/agent_skill_sync.py``).
_DEFAULT_CLONE_TIMEOUT_SECONDS = 120

#: Timezone the operations metrics use to decide where a calendar day starts,
#: used when reporting "today" counts and when bucketing the lead-time trend.
#: UTC is the safe default; an operations team reading these numbers against
#: their own working day will want their local zone instead.
_DEFAULT_METRICS_TIMEZONE = "UTC"

#: How long (1 hour) an MCP approval certificate stays valid after the approval
#: is granted. It bounds the window in which an approved task may call its bound
#: MCP tools: long enough for a task that waits on a slow upstream, short enough
#: that a leaked certificate stops being useful the same working hour.
_DEFAULT_APPROVAL_CERT_TTL_SECONDS = 3600

#: Clock-skew tolerance (60 seconds) for the proof-of-possession signature that
#: accompanies each proxied tool call. The signature covers a timestamp; a
#: signature older or newer than this is rejected.
_DEFAULT_POP_SIGNATURE_WINDOW_SECONDS = 60

#: Validity of the self-signed root CA that signs approval certificates. Ten
#: years, because rotation is not implemented yet and an expired root would
#: silently stop every approved task from calling its tools.
_DEFAULT_MCP_CA_VALIDITY_DAYS = 3650

#: Subject/issuer common name of the generated root CA.
_DEFAULT_MCP_CA_COMMON_NAME = "A2Flow MCP Approval CA"

#: Defaults keyed by field name for :meth:`Settings._fallback_positive_int`.
#: A validator shared across fields cannot read each field's own default, so
#: the mapping supplies it.
_POSITIVE_INT_DEFAULTS = {
    "mcp_approval_cert_ttl_seconds": _DEFAULT_APPROVAL_CERT_TTL_SECONDS,
    "mcp_approval_cert_signature_window_seconds": _DEFAULT_POP_SIGNATURE_WINDOW_SECONDS,
    "mcp_ca_validity_days": _DEFAULT_MCP_CA_VALIDITY_DAYS,
}


class Settings(BaseSettings):
    """Typed, environment-driven application configuration.

    Fields are populated from process environment variables (matched
    case-insensitively by name) or, when unset, from ``backend/.env``.

    Attributes:
        host: Uvicorn bind host, used only by ``main.py``'s ``__main__`` block.
        port: Uvicorn bind port, used only by ``main.py``'s ``__main__`` block.
        reload: Whether that same ``__main__`` block enables uvicorn autoreload.
        cors_origins: Allowed CORS origins for the API.
        db_url: Database URL selecting SQLite (default) or PostgreSQL.
        skills_dir: Root of the Agent Skill store, laid out as
            ``<skill_id>/<commit_sha>/``. This is durable state, not a cache:
            a WorkflowExecution pins the revision it started with, so wiping the
            directory leaves existing sessions unable to load their skill until
            an admin pulls again. In a horizontally scaled deployment it must
            be a volume shared by every replica.
        skills_prune_grace_seconds: How long an unreferenced skill revision
            directory is kept before a pull may prune it.
        skills_clone_timeout_seconds: Per-request timeout, in seconds, for a
            skill clone's HTTP requests against its repository.
        llm_model: LLM selection, either a bare Gemini model name or a
            ``litellm:<provider>/<model>`` string.
        role_description: Base role text fed into the system prompt builder.
        admin_password: Password for the seeded ``admin`` user inside the
            seeded ``Default`` tenant; a random password is generated by
            ``bootstrap.py`` when unset.
        root_password: Password for the seeded platform-wide ``root`` user
            (holds ``super_admin``, no tenant); a random password is
            generated by ``bootstrap.py`` when unset.
        demo_data: Whether the demo dataset (sample Agent Skill, AWS MCP
            server, AWS secrets, and approver/requester users) is registered
            in the seeded ``Default`` tenant on startup. When false, any
            previously registered demo record is removed again — see
            ``infrastructure/demo_data.py``.
        demo_password: Shared password for the seeded demo users; a random
            password is generated by ``demo_data.py`` when unset.
        demo_aws_access_key_id: Value stored in the demo
            ``demo-aws-access-key-id`` secret; a placeholder is stored when
            unset.
        demo_aws_secret_access_key: Value stored in the demo
            ``demo-aws-secret-access-key`` secret; a placeholder is stored
            when unset.
        demo_aws_region: AWS region the demo MCP server's tools act on, passed
            to it as ``--metadata AWS_REGION=...``.
        secret_encryption_key: Fernet key for encrypting local secrets
            (first in the resolution precedence handled by ``secret_cipher.py``).
        secret_key_file: Path to the on-disk Fernet key file (second in that
            precedence).
        vault_addr: HashiCorp Vault server address; Vault is disabled when unset.
        vault_role_id: AppRole authentication role id.
        vault_secret_id: AppRole authentication secret id.
        vault_approle_mount: AppRole login mount path.
        vault_token: Static Vault token, used when AppRole credentials are absent.
        mcp_registry_url: Base URL of the official MCP registry.
        session_cookie_secure: Whether auth/CSRF cookies carry the ``Secure``
            attribute.
        session_idle_timeout_seconds: Sliding idle timeout, in seconds, for a
            login session.
        metrics_timezone: IANA timezone name deciding where a calendar day
            starts for the operations metrics.
        app_base_url: Base URL at which users reach this deployment in a
            browser, used to build the deep links embedded in outgoing
            notification email. Applied to the ``system_settings`` row on
            every startup by
            ``infrastructure.bootstrap.apply_system_settings_env_overrides``;
            left unset, the stored value is untouched. See that function's
            docstring for the full env-loading contract covering this and the
            ``smtp_*`` fields below.
        smtp_enabled: Whether outbound notification email is enabled. Applied
            to the ``system_settings`` row the same way as ``app_base_url``
            above; left unset, the stored value is untouched.
        smtp_host: SMTP relay hostname or IP.
        smtp_port: SMTP relay submission port.
        smtp_security: How the connection to the relay is secured (``none``,
            ``starttls``, or ``ssl``).
        smtp_username: SMTP relay username, if the relay requires authentication.
        smtp_password: SMTP relay password.
        smtp_from_email: "From" address on outgoing notification email.
        smtp_from_name: "From" display name on outgoing notification email.
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    db_url: str = "sqlite:///a2flow.db"

    skills_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent / ".skills"
    )
    skills_prune_grace_seconds: int = _DEFAULT_PRUNE_GRACE_SECONDS
    skills_clone_timeout_seconds: int = _DEFAULT_CLONE_TIMEOUT_SECONDS

    llm_model: str = "gemini-3.5-flash"
    role_description: str = "You are a helpful assistant."

    admin_password: str | None = None
    root_password: str | None = None

    demo_data: bool = False
    demo_password: str | None = None
    demo_aws_access_key_id: str | None = None
    demo_aws_secret_access_key: str | None = None
    demo_aws_region: str = "us-east-1"

    secret_encryption_key: str | None = None
    secret_key_file: Path | None = None

    vault_addr: str | None = None
    vault_role_id: str | None = None
    vault_secret_id: str | None = None
    vault_approle_mount: str = "approle"
    vault_token: str | None = None

    mcp_registry_url: str = "https://registry.modelcontextprotocol.io"

    mcp_approval_cert_ttl_seconds: int = _DEFAULT_APPROVAL_CERT_TTL_SECONDS
    mcp_approval_cert_signature_window_seconds: int = (
        _DEFAULT_POP_SIGNATURE_WINDOW_SECONDS
    )
    mcp_ca_common_name: str = _DEFAULT_MCP_CA_COMMON_NAME
    mcp_ca_validity_days: int = _DEFAULT_MCP_CA_VALIDITY_DAYS

    session_cookie_secure: bool = False
    session_idle_timeout_seconds: int = _DEFAULT_IDLE_TIMEOUT_SECONDS

    metrics_timezone: str = _DEFAULT_METRICS_TIMEZONE

    app_base_url: str | None = None

    smtp_enabled: bool | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_security: str | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: Any) -> Any:
        """Split a comma-separated ``CORS_ORIGINS`` string into a stripped list."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",")]
        return value

    @field_validator("session_idle_timeout_seconds", mode="before")
    @classmethod
    def _fallback_idle_timeout(cls, value: Any) -> Any:
        """Fall back to the default timeout on an unset or unparseable value.

        Mirrors the previous ``os.getenv`` + ``try/except ValueError`` behavior:
        a missing, empty, or non-integer value silently falls back rather than
        failing validation.
        """
        if value is None or value == "":
            return _DEFAULT_IDLE_TIMEOUT_SECONDS
        try:
            return int(value)
        except (TypeError, ValueError):
            return _DEFAULT_IDLE_TIMEOUT_SECONDS

    @field_validator("metrics_timezone", mode="before")
    @classmethod
    def _fallback_metrics_timezone(cls, value: Any) -> Any:
        """Fall back to UTC on an unset or unrecognized IANA timezone name.

        Follows :meth:`_fallback_idle_timeout` in preferring a working default
        over a hard validation failure: a typo in this setting should skew the
        day boundary of a dashboard, not stop the whole application from
        starting.
        """
        if not isinstance(value, str) or not value:
            return _DEFAULT_METRICS_TIMEZONE
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            return _DEFAULT_METRICS_TIMEZONE
        return value

    @field_validator(
        "mcp_approval_cert_ttl_seconds",
        "mcp_approval_cert_signature_window_seconds",
        "mcp_ca_validity_days",
        mode="before",
    )
    @classmethod
    def _fallback_positive_int(cls, value: Any, info: ValidationInfo) -> Any:
        """Fall back to the field's default on an unset or unusable value.

        Follows :meth:`_fallback_idle_timeout`: an empty value from a compose or
        ConfigMap template, a typo, or a non-positive number falls back to the
        default rather than stopping the application from starting. A zero or
        negative certificate lifetime would make every approved task unable to
        call its tools, which is a worse failure than ignoring the setting.
        """
        default = _POSITIVE_INT_DEFAULTS[info.field_name or ""]
        if value is None or value == "":
            return default
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    @field_validator(
        "app_base_url",
        "smtp_enabled",
        "smtp_host",
        "smtp_port",
        "smtp_security",
        "smtp_username",
        "smtp_password",
        "smtp_from_email",
        "smtp_from_name",
        mode="before",
    )
    @classmethod
    def _blank_system_settings_env_is_unset(cls, value: Any) -> Any:
        """Treat an empty ``APP_BASE_URL``/``SMTP_*`` value as unset, not a parse/shape error.

        A deploy template (docker-compose, a Kubernetes ConfigMap) commonly
        emits every declared env var, blank, when a feature exists but isn't
        configured yet. Without this, an empty ``SMTP_PORT`` or
        ``SMTP_ENABLED`` would fail int/bool coercion right here and crash the
        whole application at startup — before
        ``infrastructure.bootstrap.apply_system_settings_env_overrides`` ever
        gets a chance to log a warning and skip just the offending env load —
        and a blank ``SMTP_HOST`` or ``APP_BASE_URL`` would be treated as
        "explicitly set to an invalid empty value" instead of "not
        configured". Mirrors :meth:`_fallback_idle_timeout`'s reasoning for
        the same class of problem.
        """
        if value == "":
            return None
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached :class:`Settings` singleton."""
    return Settings()
