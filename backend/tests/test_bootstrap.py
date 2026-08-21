"""Tests for the startup bootstrap helpers in ``infrastructure.bootstrap``.

Covers :func:`seed_root_user` (the platform-wide super_admin, ``username="root"``)
and :func:`seed_default_tenant_and_admin_user` (the seeded ``Default`` tenant
plus its tenant-scoped ``admin`` user): each honours its own environment
variable (``ROOT_PASSWORD`` / ``ADMIN_PASSWORD``) or generates and logs a
random password exactly once when unset, and each is independently
idempotent. Also covers the ordering contract between the two — ``root`` must
be seeded first, or its "any real user exists" skip check would wrongly fire
once the Default-tenant admin exists.

Also covers :func:`apply_system_settings_env_overrides`: applying whichever
``APP_BASE_URL``/``SMTP_*`` environment variables are set onto the singleton
system-settings row on every startup, leaving unset fields (and, on any
validation failure, the whole row) untouched.
"""

import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, get_args

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.bootstrap import (
    apply_system_settings_env_overrides,
    seed_default_tenant_and_admin_user,
    seed_root_user,
    seed_system_settings,
    seed_system_user,
)
from infrastructure.password import verify_password
from infrastructure.secret_cipher import get_secret_cipher
from models.constraints import Password
from models.system_settings import SYSTEM_SETTINGS_ID, SystemSettings
from models.tenant import Tenant
from models.user import SYSTEM_USER_ID, Role, User
from repositories.exceptions import NotFoundError

_PASSWORD_CONSTRAINTS = get_args(Password)[1]

_BOOTSTRAP_LOGGER = "infrastructure.bootstrap"


async def _fresh_seeded_engine() -> AsyncEngine:
    """Create an in-memory SQLite engine with the schema and system user seeded."""
    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(mem_engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(mem_engine) as session:
        await seed_system_user(session)
    return mem_engine


@pytest_asyncio.fixture()
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Provide an in-memory SQLite engine with the schema and system user seeded."""
    mem_engine = await _fresh_seeded_engine()
    try:
        yield mem_engine
    finally:
        await mem_engine.dispose()


@pytest_asyncio.fixture()
async def settings_engine(engine: AsyncEngine) -> AsyncEngine:
    """The shared ``engine`` fixture, with the system_settings row also seeded."""
    async with AsyncSession(engine) as session:
        await seed_system_settings(session)
    return engine


async def _real_users(session: AsyncSession) -> list[User]:
    """Return all non-system users currently persisted."""
    stmt = select(User).where(col(User.id) != SYSTEM_USER_ID)
    return list((await session.exec(stmt)).all())


async def _seed_with_generated_password(
    engine: AsyncEngine,
    caplog: pytest.LogCaptureFixture,
    seed: Callable[[AsyncSession], Awaitable[None]],
) -> str:
    """Run ``seed`` and return the password generated for the log."""
    with caplog.at_level(logging.WARNING, logger=_BOOTSTRAP_LOGGER):
        async with AsyncSession(engine) as session:
            await seed(session)
    record = caplog.records[-1]
    assert isinstance(record.args, tuple)
    password = record.args[0]
    assert isinstance(password, str)
    return password


# ---------- seed_root_user ----------


async def test_seed_root_user_creates_root(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        await seed_root_user(session)
    async with AsyncSession(engine) as session:
        users = await _real_users(session)
    assert len(users) == 1
    assert users[0].username == "root"
    assert users[0].enabled is True
    assert users[0].created_by == SYSTEM_USER_ID


async def test_seed_root_user_grants_super_admin_role(engine: AsyncEngine) -> None:
    """The seeded root user holds super_admin so it can manage users and roles."""
    async with AsyncSession(engine) as session:
        await seed_root_user(session)
    async with AsyncSession(engine) as session:
        root = (await _real_users(session))[0]
    assert root.roles == [Role.super_admin.value]
    assert root.tenant_id is None


async def test_seed_root_user_honours_env_password(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("ROOT_PASSWORD", "super-secret-pw")
    with caplog.at_level(logging.WARNING, logger=_BOOTSTRAP_LOGGER):
        async with AsyncSession(engine) as session:
            await seed_root_user(session)
    async with AsyncSession(engine) as session:
        root = (await _real_users(session))[0]
    assert verify_password("super-secret-pw", root.password)
    assert caplog.records == []


async def test_seed_root_user_generates_random_password_when_unset(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("ROOT_PASSWORD", raising=False)
    password = await _seed_with_generated_password(engine, caplog, seed_root_user)
    async with AsyncSession(engine) as session:
        root = (await _real_users(session))[0]
    assert verify_password(password, root.password)
    assert "ROOT_PASSWORD not set" in caplog.records[-1].getMessage()


async def test_seed_root_user_generated_password_meets_length_bounds(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("ROOT_PASSWORD", raising=False)
    password = await _seed_with_generated_password(engine, caplog, seed_root_user)
    assert _PASSWORD_CONSTRAINTS.min_length <= len(password)
    assert len(password) <= _PASSWORD_CONSTRAINTS.max_length


async def test_seed_root_user_two_fresh_databases_get_different_passwords(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("ROOT_PASSWORD", raising=False)
    engine_a = await _fresh_seeded_engine()
    engine_b = await _fresh_seeded_engine()
    try:
        password_a = await _seed_with_generated_password(
            engine_a, caplog, seed_root_user
        )
        caplog.clear()
        password_b = await _seed_with_generated_password(
            engine_b, caplog, seed_root_user
        )
    finally:
        await engine_a.dispose()
        await engine_b.dispose()
    assert password_a != password_b


async def test_seed_root_user_logs_generated_password_only_once(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("ROOT_PASSWORD", raising=False)
    with caplog.at_level(logging.WARNING, logger=_BOOTSTRAP_LOGGER):
        async with AsyncSession(engine) as session:
            await seed_root_user(session)
            await seed_root_user(session)
    assert len(caplog.records) == 1


async def test_seed_root_user_is_idempotent(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        await seed_root_user(session)
        await seed_root_user(session)
    async with AsyncSession(engine) as session:
        users = await _real_users(session)
    assert len(users) == 1


async def test_seed_root_user_skips_when_real_user_exists(
    engine: AsyncEngine,
) -> None:
    async with AsyncSession(engine) as session:
        session.add(
            User(
                id="alice",
                username="alice",
                first_name="Alice",
                last_name="Smith",
                password="hash",
                email="alice@example.com",
                roles=[Role.super_admin.value],
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await session.commit()
        await seed_root_user(session)
    async with AsyncSession(engine) as session:
        users = await _real_users(session)
    assert len(users) == 1
    assert users[0].username == "alice"


# ---------- seed_default_tenant_and_admin_user ----------


async def _default_tenant(session: AsyncSession) -> Tenant | None:
    stmt = select(Tenant).where(col(Tenant.name) == "default")
    return (await session.exec(stmt)).first()


async def test_seed_default_tenant_and_admin_user_creates_tenant(
    engine: AsyncEngine,
) -> None:
    async with AsyncSession(engine) as session:
        await seed_default_tenant_and_admin_user(session)
    async with AsyncSession(engine) as session:
        tenant = await _default_tenant(session)
    assert tenant is not None
    assert tenant.display_name == "Default"
    assert tenant.enabled is True
    assert tenant.created_by == SYSTEM_USER_ID


async def test_seed_default_tenant_and_admin_user_creates_admin(
    engine: AsyncEngine,
) -> None:
    async with AsyncSession(engine) as session:
        await seed_default_tenant_and_admin_user(session)
    async with AsyncSession(engine) as session:
        users = await _real_users(session)
        tenant = await _default_tenant(session)
    assert tenant is not None
    assert len(users) == 1
    assert users[0].username == "admin"
    assert users[0].roles == [Role.admin.value]
    assert users[0].tenant_id == tenant.id


async def test_seed_default_tenant_and_admin_user_honours_env_password(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("ADMIN_PASSWORD", "super-secret-pw")
    with caplog.at_level(logging.WARNING, logger=_BOOTSTRAP_LOGGER):
        async with AsyncSession(engine) as session:
            await seed_default_tenant_and_admin_user(session)
    async with AsyncSession(engine) as session:
        admin = (await _real_users(session))[0]
    assert verify_password("super-secret-pw", admin.password)
    assert caplog.records == []


async def test_seed_default_tenant_and_admin_user_generates_random_password_when_unset(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    password = await _seed_with_generated_password(
        engine, caplog, seed_default_tenant_and_admin_user
    )
    async with AsyncSession(engine) as session:
        admin = (await _real_users(session))[0]
    assert verify_password(password, admin.password)
    assert "ADMIN_PASSWORD not set" in caplog.records[-1].getMessage()


async def test_seed_default_tenant_and_admin_user_logs_generated_password_only_once(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    with caplog.at_level(logging.WARNING, logger=_BOOTSTRAP_LOGGER):
        async with AsyncSession(engine) as session:
            await seed_default_tenant_and_admin_user(session)
            await seed_default_tenant_and_admin_user(session)
    assert len(caplog.records) == 1


async def test_seed_default_tenant_and_admin_user_is_idempotent(
    engine: AsyncEngine,
) -> None:
    async with AsyncSession(engine) as session:
        await seed_default_tenant_and_admin_user(session)
        await seed_default_tenant_and_admin_user(session)
    async with AsyncSession(engine) as session:
        users = await _real_users(session)
        stmt = select(Tenant).where(col(Tenant.name) == "default")
        tenants = list((await session.exec(stmt)).all())
    assert len(users) == 1
    assert len(tenants) == 1


async def test_seed_default_tenant_and_admin_user_reuses_preexisting_tenant(
    engine: AsyncEngine,
) -> None:
    async with AsyncSession(engine) as session:
        session.add(
            Tenant(
                id="preexisting-default",
                display_name="Default",
                name="default",
                enabled=True,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await session.commit()
        await seed_default_tenant_and_admin_user(session)
    async with AsyncSession(engine) as session:
        stmt = select(Tenant).where(col(Tenant.name) == "default")
        tenants = list((await session.exec(stmt)).all())
        users = await _real_users(session)
    assert len(tenants) == 1
    assert tenants[0].id == "preexisting-default"
    assert users[0].tenant_id == "preexisting-default"


async def test_seed_default_tenant_and_admin_user_creates_new_admin_alongside_legacy_platform_admin(
    engine: AsyncEngine,
) -> None:
    """A pre-existing platform-scoped 'admin' does not block the tenant-scoped one.

    Simulates upgrading a deployment that ran the old single-seed bootstrap
    (a platform-scoped, ``tenant_id IS NULL`` legacy super_admin 'admin'):
    the admin-seed check is scoped to the Default tenant's id, so the legacy
    user is left completely untouched and a *new*, Default-tenant-scoped
    'admin' is created alongside it.
    """
    async with AsyncSession(engine) as session:
        session.add(
            User(
                id="legacy-admin",
                username="admin",
                first_name="Admin",
                last_name="User",
                password="hash",
                email="admin@localhost",
                roles=[Role.super_admin.value],
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await session.commit()
        await seed_default_tenant_and_admin_user(session)
    async with AsyncSession(engine) as session:
        tenant = await _default_tenant(session)
        users = await _real_users(session)
    assert tenant is not None
    assert len(users) == 2
    legacy = next(u for u in users if u.id == "legacy-admin")
    assert legacy.roles == [Role.super_admin.value]
    assert legacy.tenant_id is None
    new_admin = next(u for u in users if u.id != "legacy-admin")
    assert new_admin.username == "admin"
    assert new_admin.roles == [Role.admin.value]
    assert new_admin.tenant_id == tenant.id


async def test_seed_default_tenant_and_admin_user_skips_when_admin_already_in_default_tenant(
    engine: AsyncEngine,
) -> None:
    """The admin-seed skip check is scoped to the Default tenant, not global."""
    async with AsyncSession(engine) as session:
        tenant = Tenant(
            display_name="Default",
            name="default",
            enabled=True,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        tenant_id = tenant.id
        session.add(tenant)
        await session.commit()
        session.add(
            User(
                id="existing-tenant-admin",
                username="admin",
                first_name="Admin",
                last_name="User",
                password="hash",
                email="admin@localhost",
                roles=[Role.admin.value],
                tenant_id=tenant_id,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await session.commit()
        await seed_default_tenant_and_admin_user(session)
    async with AsyncSession(engine) as session:
        users = await _real_users(session)
    assert len(users) == 1
    assert users[0].id == "existing-tenant-admin"


# ---------- ordering contract between seed_root_user and seed_default_tenant_and_admin_user ----------


async def test_seed_root_user_then_default_tenant_admin_user_together(
    engine: AsyncEngine,
) -> None:
    async with AsyncSession(engine) as session:
        await seed_root_user(session)
        await seed_default_tenant_and_admin_user(session)
    async with AsyncSession(engine) as session:
        users = await _real_users(session)
        tenant = await _default_tenant(session)
    assert tenant is not None
    usernames = {user.username for user in users}
    assert usernames == {"root", "admin"}
    root = next(user for user in users if user.username == "root")
    admin = next(user for user in users if user.username == "admin")
    assert root.roles == [Role.super_admin.value]
    assert root.tenant_id is None
    assert admin.roles == [Role.admin.value]
    assert admin.tenant_id == tenant.id


async def test_seed_default_tenant_admin_user_before_root_user_prevents_root(
    engine: AsyncEngine,
) -> None:
    """Regression guard for the ordering contract: root must be seeded first.

    If the Default-tenant admin were seeded before root, it would count as
    the "real user" that makes ``seed_root_user``'s skip check fire, and
    root would never be created.
    """
    async with AsyncSession(engine) as session:
        await seed_default_tenant_and_admin_user(session)
        await seed_root_user(session)
    async with AsyncSession(engine) as session:
        users = await _real_users(session)
    usernames = {user.username for user in users}
    assert usernames == {"admin"}
    assert "root" not in usernames


# ---------- apply_system_settings_env_overrides ----------


async def _settings_row(engine: AsyncEngine) -> SystemSettings:
    async with AsyncSession(engine) as session:
        row = await session.get(SystemSettings, SYSTEM_SETTINGS_ID)
    assert row is not None
    return row


@pytest.fixture(autouse=True)
def _blank_system_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force every ``APP_BASE_URL``/``SMTP_*`` env var blank before each test below.

    ``config.get_settings`` always reads real ``os.environ`` regardless of
    the conftest-level ``_reset_settings_cache`` fixture blocking
    ``Settings``'s ``env_file`` — and ``main.py``'s module-level
    ``load_dotenv()`` call writes ``backend/.env``'s contents straight into
    ``os.environ`` the first time anything in the same pytest-xdist worker
    imports ``main`` (e.g. a router test's ``TestClient`` fixture), which
    then persists for the rest of that worker's test run. Without this, a
    developer with real SMTP credentials configured in their local
    ``backend/.env`` would see these tests fail depending on test order.
    A blank value is treated as unset by :class:`config.Settings`'s own
    validator, so this only establishes a clean baseline; each test below
    still layers its own ``monkeypatch.setenv(...)`` calls on top for the
    fields it cares about.
    """
    for name in (
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
        monkeypatch.setenv(name, "")


async def test_apply_system_settings_env_overrides_does_nothing_when_unset(
    settings_engine: AsyncEngine,
) -> None:
    async with AsyncSession(settings_engine) as session:
        await apply_system_settings_env_overrides(session)
    row = await _settings_row(settings_engine)
    assert row.app_base_url is None
    assert row.smtp_enabled is False
    assert row.smtp_host is None
    assert row.smtp_port == 587


async def test_apply_system_settings_env_overrides_applies_app_base_url(
    settings_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_BASE_URL", "https://a2flow.example.com")

    async with AsyncSession(settings_engine) as session:
        await apply_system_settings_env_overrides(session)

    row = await _settings_row(settings_engine)
    assert row.app_base_url == "https://a2flow.example.com"
    # Applied independently of SMTP — no enable flag gates it.
    assert row.smtp_enabled is False


async def test_apply_system_settings_env_overrides_skips_on_invalid_app_base_url(
    settings_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("APP_BASE_URL", "not-a-url")
    with caplog.at_level(logging.WARNING, logger=_BOOTSTRAP_LOGGER):
        async with AsyncSession(settings_engine) as session:
            await apply_system_settings_env_overrides(session)
    row = await _settings_row(settings_engine)
    assert row.app_base_url is None
    bootstrap_records = [r for r in caplog.records if r.name == _BOOTSTRAP_LOGGER]
    assert len(bootstrap_records) == 1
    assert "app_base_url" in bootstrap_records[0].getMessage()


async def test_apply_system_settings_env_overrides_applies_a_full_valid_configuration(
    settings_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SMTP_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_SECURITY", "starttls")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "a2flow@example.com")
    monkeypatch.setenv("SMTP_FROM_NAME", "A2Flow")
    monkeypatch.setenv("SMTP_USERNAME", "mailer")
    monkeypatch.setenv("SMTP_PASSWORD", "hunter2hunter2")

    async with AsyncSession(settings_engine) as session:
        await apply_system_settings_env_overrides(session)

    row = await _settings_row(settings_engine)
    assert row.smtp_enabled is True
    assert row.smtp_host == "smtp.example.com"
    assert row.smtp_port == 2525
    assert row.smtp_from_email == "a2flow@example.com"
    assert row.smtp_from_name == "A2Flow"
    assert row.smtp_username == "mailer"
    assert row.smtp_password is not None
    assert row.smtp_password != "hunter2hunter2"
    assert get_secret_cipher().decrypt(row.smtp_password) == "hunter2hunter2"
    assert row.updated_by == SYSTEM_USER_ID


async def test_apply_system_settings_env_overrides_skips_on_unusable_configuration(
    settings_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SMTP_ENABLED", "true")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "a2flow@example.com")
    with caplog.at_level(logging.WARNING, logger=_BOOTSTRAP_LOGGER):
        async with AsyncSession(settings_engine) as session:
            await apply_system_settings_env_overrides(session)
    row = await _settings_row(settings_engine)
    assert row.smtp_enabled is False
    assert row.smtp_host is None
    # Filtered by logger name: get_secret_cipher() may also log its own
    # one-time "generated a new secret encryption key" WARNING on this
    # worker's first use, which is unrelated to this function's own warning.
    bootstrap_records = [r for r in caplog.records if r.name == _BOOTSTRAP_LOGGER]
    assert len(bootstrap_records) == 1
    assert "smtpHost" in bootstrap_records[0].getMessage()


async def test_apply_system_settings_env_overrides_applies_partial_config_without_enabling(
    settings_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    async with AsyncSession(settings_engine) as session:
        await apply_system_settings_env_overrides(session)
    row = await _settings_row(settings_engine)
    assert row.smtp_host == "smtp.example.com"
    assert row.smtp_enabled is False


async def test_apply_system_settings_env_overrides_skips_on_invalid_port(
    settings_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SMTP_PORT", "70000")
    with caplog.at_level(logging.WARNING, logger=_BOOTSTRAP_LOGGER):
        async with AsyncSession(settings_engine) as session:
            await apply_system_settings_env_overrides(session)
    row = await _settings_row(settings_engine)
    assert row.smtp_port == 587
    assert "smtp_port" in caplog.records[-1].getMessage()


async def test_apply_system_settings_env_overrides_never_logs_the_password(
    settings_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SMTP_PASSWORD", "super-secret-value")
    monkeypatch.setenv("SMTP_PORT", "70000")  # forces the whole apply to fail
    with caplog.at_level(logging.WARNING, logger=_BOOTSTRAP_LOGGER):
        async with AsyncSession(settings_engine) as session:
            await apply_system_settings_env_overrides(session)
    assert "super-secret-value" not in caplog.text


async def test_apply_system_settings_env_overrides_is_idempotent_across_reboots(
    settings_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SMTP_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "a2flow@example.com")
    async with AsyncSession(settings_engine) as session:
        await apply_system_settings_env_overrides(session)
        await apply_system_settings_env_overrides(session)
    row = await _settings_row(settings_engine)
    assert row.smtp_enabled is True
    assert row.smtp_host == "smtp.example.com"


async def test_apply_system_settings_env_overrides_requires_the_row_to_exist(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    async with AsyncSession(engine) as session:  # note: settings row NOT seeded
        with pytest.raises(NotFoundError):
            await apply_system_settings_env_overrides(session)
