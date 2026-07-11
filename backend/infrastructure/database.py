"""SQLAlchemy/SQLModel database engine and session management.

The database is selected by ``config.Settings.db_url`` (the ``DB_URL``
environment variable). SQLite is the zero-config default; pointing ``DB_URL``
at a PostgreSQL database (e.g.
``postgresql://user:pass@host:5432/a2flow``) switches the whole application —
including the ADK session store — to PostgreSQL. Sync-style URLs are
normalized to their async-driver variants by :func:`to_async_url`.
"""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings

DB_URL = get_settings().db_url


def to_async_url(url: str) -> str:
    """Normalize a sync-style DB URL to its async-driver variant.

    ``sqlite://`` URLs are mapped to the ``aiosqlite`` driver and
    ``postgresql://`` / ``postgres://`` URLs to the ``asyncpg`` driver. URLs
    that already name an explicit driver (e.g. ``sqlite+aiosqlite://``,
    ``postgresql+asyncpg://``) pass through unchanged.

    Args:
        url: The database URL, typically from the ``DB_URL`` environment variable.

    Returns:
        The URL with an async driver suitable for ``create_async_engine``.
    """
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def is_sqlite_url(url: str) -> bool:
    """Return ``True`` when the URL targets SQLite (with or without a driver).

    Args:
        url: The database URL to inspect.

    Returns:
        ``True`` for ``sqlite://`` and ``sqlite+<driver>://`` URLs.
    """
    return url.startswith(("sqlite:", "sqlite+"))


ASYNC_DB_URL = to_async_url(DB_URL)


def _engine() -> AsyncEngine:
    """Create the async SQLAlchemy engine from the configured DB_URL.

    Non-SQLite engines enable ``pool_pre_ping`` so stale pooled connections
    (e.g. dropped by a PostgreSQL server restart) are detected and replaced
    transparently.
    """
    kwargs: dict[str, Any] = (
        {} if is_sqlite_url(ASYNC_DB_URL) else {"pool_pre_ping": True}
    )
    return create_async_engine(ASYNC_DB_URL, echo=False, **kwargs)


engine = _engine()


def _set_sqlite_pragmas(dbapi_conn: Any, _: object) -> None:
    """Enable foreign-key enforcement and WAL journal mode on each new SQLite connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


if engine.dialect.name == "sqlite":
    sa_event.listen(engine.sync_engine, "connect", _set_sqlite_pragmas)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for use as a FastAPI dependency.

    ``expire_on_commit`` is disabled so ORM objects keep their loaded attributes
    after a commit. Without this, an entity loaded before a later commit in the
    same request (e.g. the user whose login also inserts a session row) is
    expired, and reading its attributes during response serialization triggers
    lazy IO outside the async greenlet (``MissingGreenlet``).
    """
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
