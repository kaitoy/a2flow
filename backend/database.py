"""SQLAlchemy/SQLModel database engine and session management."""

import os
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

DB_URL = os.getenv("DB_URL", "sqlite:///a2flow.db")


def _to_aiosqlite_url(url: str) -> str:
    """Convert a ``sqlite:///`` URL to the ``sqlite+aiosqlite:///`` async variant."""
    return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)


def _engine() -> AsyncEngine:
    """Create the async SQLAlchemy engine from the configured DB_URL."""
    return create_async_engine(_to_aiosqlite_url(DB_URL), echo=False)


engine = _engine()


@sa_event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn: Any, _: object) -> None:
    """Enable foreign-key enforcement and WAL journal mode on each new SQLite connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


async def init_db() -> None:
    """Create all SQLModel-defined tables if they do not already exist."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for use as a FastAPI dependency."""
    async with AsyncSession(engine) as session:
        yield session
