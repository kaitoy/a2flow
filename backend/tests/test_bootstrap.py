"""Tests for the startup bootstrap helpers in ``infrastructure.bootstrap``.

Covers :func:`seed_admin_user`: it creates the initial ``admin`` user on an
empty database, honours the ``ADMIN_PASSWORD`` environment variable (or
generates and logs a random one exactly once when unset), and is a no-op once
any real (non-system) user already exists.
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any, get_args

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.bootstrap import seed_admin_user, seed_system_user
from infrastructure.password import verify_password
from models.constraints import Password
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
    engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> str:
    """Run ``seed_admin_user`` and return the password generated for the log."""
    with caplog.at_level(logging.WARNING, logger=_BOOTSTRAP_LOGGER):
        async with AsyncSession(engine) as session:
            await seed_admin_user(session)
    record = caplog.records[-1]
    assert isinstance(record.args, tuple)
    password = record.args[0]
    assert isinstance(password, str)
    return password


async def test_seed_admin_user_creates_admin(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        await seed_admin_user(session)
    async with AsyncSession(engine) as session:
        users = await _real_users(session)
    assert len(users) == 1
    assert users[0].username == "admin"
    assert users[0].enabled is True
    assert users[0].created_by == SYSTEM_USER_ID


async def test_seed_admin_user_grants_super_admin_role(engine: AsyncEngine) -> None:
    """The seeded admin holds super_admin so it can manage users and roles."""
    async with AsyncSession(engine) as session:
        await seed_admin_user(session)
    async with AsyncSession(engine) as session:
        admin = (await _real_users(session))[0]
    assert admin.roles == [Role.super_admin.value]


async def test_seed_admin_user_honours_env_password(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("ADMIN_PASSWORD", "super-secret-pw")
    with caplog.at_level(logging.WARNING, logger=_BOOTSTRAP_LOGGER):
        async with AsyncSession(engine) as session:
            await seed_admin_user(session)
    async with AsyncSession(engine) as session:
        admin = (await _real_users(session))[0]
    assert verify_password("super-secret-pw", admin.password)
    assert caplog.records == []


async def test_seed_admin_user_generates_random_password_when_unset(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    password = await _seed_with_generated_password(engine, caplog)
    async with AsyncSession(engine) as session:
        admin = (await _real_users(session))[0]
    assert verify_password(password, admin.password)
    assert "ADMIN_PASSWORD not set" in caplog.records[-1].getMessage()


async def test_seed_admin_user_generated_password_meets_length_bounds(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    password = await _seed_with_generated_password(engine, caplog)
    assert _PASSWORD_CONSTRAINTS.min_length <= len(password)
    assert len(password) <= _PASSWORD_CONSTRAINTS.max_length


async def test_seed_admin_user_two_fresh_databases_get_different_passwords(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    engine_a = await _fresh_seeded_engine()
    engine_b = await _fresh_seeded_engine()
    try:
        password_a = await _seed_with_generated_password(engine_a, caplog)
        caplog.clear()
        password_b = await _seed_with_generated_password(engine_b, caplog)
    finally:
        await engine_a.dispose()
        await engine_b.dispose()
    assert password_a != password_b


async def test_seed_admin_user_logs_generated_password_only_once(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    with caplog.at_level(logging.WARNING, logger=_BOOTSTRAP_LOGGER):
        async with AsyncSession(engine) as session:
            await seed_admin_user(session)
            await seed_admin_user(session)
    assert len(caplog.records) == 1


async def test_seed_admin_user_is_idempotent(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        await seed_admin_user(session)
        await seed_admin_user(session)
    async with AsyncSession(engine) as session:
        users = await _real_users(session)
    assert len(users) == 1


async def test_seed_admin_user_skips_when_real_user_exists(
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
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await session.commit()
        await seed_admin_user(session)
    async with AsyncSession(engine) as session:
        users = await _real_users(session)
    assert len(users) == 1
    assert users[0].username == "alice"
