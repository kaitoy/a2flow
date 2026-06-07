"""Tests for the startup bootstrap helpers in ``infrastructure.bootstrap``.

Covers :func:`seed_admin_user`: it creates the initial ``admin`` user on an
empty database, honours the ``ADMIN_PASSWORD`` environment variable, and is a
no-op once any real (non-system) user already exists.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.bootstrap import (
    DEFAULT_ADMIN_PASSWORD,
    seed_admin_user,
    seed_system_user,
)
from infrastructure.password import verify_password
from models.user import SYSTEM_USER_ID, User


@pytest_asyncio.fixture()
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Provide an in-memory SQLite engine with the schema and system user seeded."""
    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(mem_engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(mem_engine) as session:
        await seed_system_user(session)
    try:
        yield mem_engine
    finally:
        await mem_engine.dispose()


async def _real_users(session: AsyncSession) -> list[User]:
    """Return all non-system users currently persisted."""
    stmt = select(User).where(col(User.id) != SYSTEM_USER_ID)
    return list((await session.exec(stmt)).all())


async def test_seed_admin_user_creates_admin(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        await seed_admin_user(session)
    async with AsyncSession(engine) as session:
        users = await _real_users(session)
    assert len(users) == 1
    assert users[0].username == "admin"
    assert users[0].enabled is True
    assert users[0].created_by == SYSTEM_USER_ID


async def test_seed_admin_user_uses_default_password(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        await seed_admin_user(session)
    async with AsyncSession(engine) as session:
        admin = (await _real_users(session))[0]
    assert verify_password(DEFAULT_ADMIN_PASSWORD, admin.password)


async def test_seed_admin_user_honours_env_password(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_PASSWORD", "super-secret-pw")
    async with AsyncSession(engine) as session:
        await seed_admin_user(session)
    async with AsyncSession(engine) as session:
        admin = (await _real_users(session))[0]
    assert verify_password("super-secret-pw", admin.password)


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
