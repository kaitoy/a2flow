"""Tests for the startup bootstrap helpers in ``infrastructure.bootstrap``.

Covers :func:`seed_root_user` (the platform-wide super_admin, ``username="root"``)
and :func:`seed_default_tenant_and_admin_user` (the seeded ``Default`` tenant
plus its tenant-scoped ``admin`` user): each honours its own environment
variable (``ROOT_PASSWORD`` / ``ADMIN_PASSWORD``) or generates and logs a
random password exactly once when unset, and each is independently
idempotent. Also covers the ordering contract between the two — ``root`` must
be seeded first, or its "any real user exists" skip check would wrongly fire
once the Default-tenant admin exists.
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
    seed_default_tenant_and_admin_user,
    seed_root_user,
    seed_system_user,
)
from infrastructure.password import verify_password
from models.constraints import Password
from models.tenant import Tenant
from models.user import SYSTEM_USER_ID, Role, User

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
    stmt = select(Tenant).where(col(Tenant.slug) == "default")
    return (await session.exec(stmt)).first()


async def test_seed_default_tenant_and_admin_user_creates_tenant(
    engine: AsyncEngine,
) -> None:
    async with AsyncSession(engine) as session:
        await seed_default_tenant_and_admin_user(session)
    async with AsyncSession(engine) as session:
        tenant = await _default_tenant(session)
    assert tenant is not None
    assert tenant.name == "Default"
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
        stmt = select(Tenant).where(col(Tenant.slug) == "default")
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
                name="Default",
                slug="default",
                enabled=True,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await session.commit()
        await seed_default_tenant_and_admin_user(session)
    async with AsyncSession(engine) as session:
        stmt = select(Tenant).where(col(Tenant.slug) == "default")
        tenants = list((await session.exec(stmt)).all())
        users = await _real_users(session)
    assert len(tenants) == 1
    assert tenants[0].id == "preexisting-default"
    assert users[0].tenant_id == "preexisting-default"


async def test_seed_default_tenant_and_admin_user_skips_admin_when_username_exists(
    engine: AsyncEngine,
) -> None:
    """A pre-existing 'admin' user (e.g. from before this split) blocks re-creation.

    Simulates upgrading a deployment that ran the old single-seed bootstrap:
    the legacy super_admin 'admin' user is left completely untouched, while
    the Default tenant is still created.
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
    assert len(users) == 1
    assert users[0].id == "legacy-admin"
    assert users[0].roles == [Role.super_admin.value]
    assert users[0].tenant_id is None


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
