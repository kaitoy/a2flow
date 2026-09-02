"""The one place test fixtures get a database engine from.

The suite runs on in-memory SQLite by default: zero setup, nothing to install,
and a fresh database per test for free. Pointing ``A2FLOW_TEST_PG_URL`` at a
reachable PostgreSQL server switches every fixture built on
:func:`make_test_engine` over to that server instead, so the same tests exercise
the dialect production actually runs on -- collation-driven sort order, ``jsonb``
rather than ``JSON``, a transaction that stays aborted after a failed statement.
``compose.test.yml`` at the repository root brings up a throwaway server for it.

``DB_URL`` is deliberately *not* involved. It is read at import time by
:mod:`infrastructure.locks` and :mod:`infrastructure.secret_cipher` to pick
their SQLite-vs-PostgreSQL branch, and ``tests/test_locks.py`` documents that it
covers the in-process branch that choice selects. Only the engine the fixtures
hand to repositories moves; which lock backend the process uses does not.

**Isolation on PostgreSQL.** Each pytest process (each ``pytest-xdist`` worker,
that is) creates one schema of its own, once, and builds the tables in it once
-- see :func:`provision_schema`. Individual tests then get a clean slate from a
single ``TRUNCATE`` across every table, which costs a few milliseconds on empty
tables where re-running ``create_all`` for all 30-odd tables would not. The
engine itself is still built per test rather than shared: ``asyncpg``
connections belong to the event loop that opened them, and ``pytest-asyncio``
gives every test a loop of its own.
"""

import os
import uuid
from typing import Any

from sqlalchemy import event as sa_event
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

#: Environment variable naming a PostgreSQL server to run the suite against.
#: Unset -- the default -- keeps every fixture on in-memory SQLite.
PG_URL_ENV = "A2FLOW_TEST_PG_URL"

#: Schema this process owns on the PostgreSQL server, created by
#: :func:`provision_schema` and dropped by :func:`drop_schema`. The
#: ``pytest-xdist`` worker id keeps parallel workers of one run apart, and the
#: random suffix keeps two concurrent runs (a lefthook hook and a terminal, say)
#: from sharing tables. Module level because each worker is its own process.
SCHEMA = f"a2flow_test_{os.environ.get('PYTEST_XDIST_WORKER', 'main')}_{uuid.uuid4().hex[:8]}"


def pg_url() -> str | None:
    """Return the PostgreSQL URL the suite should run against, if any.

    Returns:
        The value of ``A2FLOW_TEST_PG_URL``, or ``None`` when it is unset or
        empty -- meaning fixtures should use in-memory SQLite.
    """
    return os.environ.get(PG_URL_ENV) or None


def _require_pg_url() -> str:
    """Return the configured PostgreSQL URL, or raise if there is none.

    Returns:
        The value of ``A2FLOW_TEST_PG_URL``.

    Raises:
        RuntimeError: If the variable is unset; the caller is PostgreSQL-only
            machinery that should have been skipped.
    """
    url = pg_url()
    if url is None:
        raise RuntimeError(f"{PG_URL_ENV} is not set")
    return url


def _set_sqlite_fk(dbapi_conn: Any, _: object) -> None:
    """Enable foreign-key enforcement on a new SQLite connection.

    SQLite only honours foreign keys -- ``ON DELETE CASCADE`` and ``RESTRICT``
    included -- with this pragma set, and it resets per connection. Without it
    the tests covering those rules would pass for the wrong reason.

    Args:
        dbapi_conn: The freshly opened DBAPI connection.
        _: The connection record, unused but required by the ``connect`` hook.
    """
    dbapi_conn.execute("PRAGMA foreign_keys=ON")


def _admin_engine() -> AsyncEngine:
    """Return an autocommit engine on the server's default schema.

    Used for the statements that create and drop :data:`SCHEMA` itself, which
    cannot run inside the search path they are about to change.
    """
    return create_async_engine(_require_pg_url(), isolation_level="AUTOCOMMIT")


def _schema_engine() -> AsyncEngine:
    """Return an engine whose connections resolve unqualified names in :data:`SCHEMA`.

    ``public`` stays on the search path behind it so anything installed
    server-wide (an extension's functions, say) still resolves, while every
    table this suite creates or reads lands in the worker's own schema.
    """
    return create_async_engine(
        _require_pg_url(),
        connect_args={"server_settings": {"search_path": f"{SCHEMA},public"}},
    )


async def provision_schema() -> None:
    """Create this process's schema and build every table in it.

    Called once per pytest process from the session fixture in ``conftest.py``,
    so the per-test cost is a ``TRUNCATE`` rather than a full ``create_all``.
    """
    admin = _admin_engine()
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))
    finally:
        await admin.dispose()

    engine = _schema_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
    finally:
        await engine.dispose()


async def drop_schema() -> None:
    """Drop this process's schema and everything in it.

    ``CASCADE`` because the tables reference each other; the schema is this
    process's alone, so nothing outside the run can be caught by it.
    """
    admin = _admin_engine()
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
    finally:
        await admin.dispose()


async def _truncate_all(engine: AsyncEngine) -> None:
    """Empty every table in :data:`SCHEMA` in one statement.

    One ``TRUNCATE`` over all tables at once, rather than one per table, so the
    foreign keys between them never come into it -- and ``CASCADE`` covers any
    reference from a table the metadata does not know about. Deliberately not
    ``sorted_tables``: order is irrelevant to a single ``TRUNCATE``, and sorting
    warns about the ``tenants``/``users`` cycle it cannot resolve.

    Args:
        engine: An engine whose search path is this process's schema.
    """
    tables = ", ".join(f'"{name}"' for name in SQLModel.metadata.tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


async def make_sqlite_engine() -> AsyncEngine:
    """Return an engine over a fresh, empty in-memory SQLite database.

    ``StaticPool`` holds the one connection open for the engine's lifetime, so
    every session the test opens reaches the same database -- without it each
    connection to ``:memory:`` gets a private one of its own.

    Returns:
        An :class:`AsyncEngine` with every table created and empty.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    sa_event.listen(engine.sync_engine, "connect", _set_sqlite_fk)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


async def make_postgres_engine() -> AsyncEngine:
    """Return an engine over this process's emptied PostgreSQL schema.

    The tables were built once by :func:`provision_schema`; all this does is
    empty them, so the caller sees the same blank slate a fresh SQLite database
    would give it.

    Note that every engine from here points at that *one* schema, so two of them
    alive at the same time are not independent -- the newer one's ``TRUNCATE``
    empties what the older one wrote. A test that genuinely needs two unrelated
    databases at once has to force SQLite and say why; see
    ``tests/test_bootstrap.py``'s ``_fresh_seeded_engine(independent=True)``.

    Returns:
        An :class:`AsyncEngine` with every table created and empty.
    """
    engine = _schema_engine()
    await _truncate_all(engine)
    return engine


async def make_test_engine() -> AsyncEngine:
    """Return an engine over an empty database on the configured backend.

    The guarantee is the same either way -- every table exists and every one of
    them is empty -- so a fixture seeds it identically and never has to know
    which backend it got. Dispose it when the fixture tears down, as with any
    engine.

    Returns:
        An :class:`AsyncEngine` ready to seed and hand to repositories.
    """
    if pg_url() is None:
        return await make_sqlite_engine()
    return await make_postgres_engine()
