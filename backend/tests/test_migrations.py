"""Tests that the Alembic migration set matches the current SQLModel metadata.

Guards against migration files drifting from the models they describe: if a
model changes without an accompanying migration, ``alembic upgrade head``
against a fresh database won't produce the same schema ``SQLModel.metadata``
declares, and this test catches that before it reaches a real deploy.

It runs against both dialects, because a migration can be valid on one and not
the other -- ``batch_alter_table`` rebuilds, partial-index predicates, and the
``JSON``/``jsonb`` variants all render differently. SQLite runs always, against
a file under ``tmp_path``. PostgreSQL runs only when ``A2FLOW_TEST_PG_URL``
names a reachable server, against a database created for the one test and
dropped afterwards -- a whole database rather than a schema, so the reflection
below sees exactly what the migrations built and nothing else.
"""

import asyncio
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

import pytest
from alembic.config import Config
from sqlalchemy import Connection, column, inspect, make_url, text
from sqlalchemy import table as sql_table
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

from alembic import command
from infrastructure.database import to_async_url
from infrastructure.secret_cipher import SecretCipher, load_or_create_key
from models.base import JSONColumn
from tests._engine import PG_URL_ENV, pg_url

BACKEND_DIR = Path(__file__).resolve().parent.parent

T = TypeVar("T")

#: Reflected alongside the model tables but owned by Alembic, not by the models.
_ALEMBIC_TABLE = "alembic_version"


async def _run_on_server(base_url: str, statement: str) -> None:
    """Run one autocommit statement against the server's default database.

    ``CREATE DATABASE`` / ``DROP DATABASE`` cannot run inside a transaction, and
    neither can run from a connection to the database it names.

    Args:
        base_url: URL of any existing database on the target server.
        statement: The SQL to execute.
    """
    engine = create_async_engine(base_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text(statement))
    finally:
        await engine.dispose()


#: What :func:`_reflect` reports: the table names, then per table its column
#: names and its index names.
_Schema = tuple[set[str], dict[str, set[str]], dict[str, set[str]]]


def _reflect(conn: Connection) -> _Schema:
    """Return the connected database's tables, columns, and indexes.

    Args:
        conn: A synchronous connection, as handed over by ``run_sync``.

    Returns:
        The table names (excluding Alembic's own bookkeeping table), and
        mappings of table name to its column names and to its index names.
        Indexes a database creates behind a unique constraint are not listed,
        just as they are not among a model's ``Table.indexes``.
    """
    inspector = inspect(conn)
    tables = set(inspector.get_table_names()) - {_ALEMBIC_TABLE}
    columns = {t: {c["name"] for c in inspector.get_columns(t)} for t in tables}
    indexes = {
        t: {
            str(ix["name"])
            for ix in inspector.get_indexes(t)
            if not ix.get("duplicates_constraint")
        }
        for t in tables
    }
    return tables, columns, indexes


async def _reflect_url(url: str) -> _Schema:
    """Open ``url`` and reflect its schema through :func:`_reflect`.

    Args:
        url: The database to inspect, in either sync or async driver form.

    Returns:
        Whatever :func:`_reflect` reports for that database.
    """
    engine = create_async_engine(to_async_url(url))
    try:
        async with engine.connect() as conn:
            return await conn.run_sync(_reflect)
    finally:
        await engine.dispose()


@pytest.fixture(params=["sqlite", "postgresql"])
def migration_db(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    """Point ``DB_URL`` at an empty database of the requested dialect.

    ``alembic/env.py`` resolves its URL from ``get_settings().db_url``, so
    setting the variable is all it takes to aim the migrations somewhere. The
    ``asyncio.run`` calls are deliberate: this fixture is synchronous because
    ``command.upgrade`` runs ``asyncio.run`` of its own inside Alembic's async
    ``env.py``, which would fail from inside an already-running loop.

    Args:
        request: Carries the dialect parameter.
        tmp_path: Per-test directory holding the SQLite database file.
        monkeypatch: Used to set ``DB_URL`` for the duration of the test.

    Yields:
        The URL of the empty database the migrations should build into.
    """
    if request.param == "sqlite":
        url = f"sqlite:///{tmp_path / 'migration_test.db'}"
        monkeypatch.setenv("DB_URL", url)
        yield url
        return

    configured = pg_url()
    if configured is None:
        pytest.skip(f"{PG_URL_ENV} is not set; skipping the PostgreSQL dialect")
    base = make_url(to_async_url(configured))
    name = f"a2flow_migtest_{uuid.uuid4().hex[:12]}"
    base_url = base.render_as_string(hide_password=False)

    asyncio.run(_run_on_server(base_url, f'CREATE DATABASE "{name}"'))
    monkeypatch.setenv(
        "DB_URL", base.set(database=name).render_as_string(hide_password=False)
    )
    try:
        yield base.set(database=name).render_as_string(hide_password=False)
    finally:
        # FORCE terminates any connection Alembic or the reflection left behind;
        # without it a stray one makes the drop fail and leaks the database.
        asyncio.run(_run_on_server(base_url, f'DROP DATABASE "{name}" WITH (FORCE)'))


def test_upgrade_head_matches_model_metadata(migration_db: str) -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(cfg, "head")

    actual_tables, actual_columns, actual_indexes = asyncio.run(
        _reflect_url(migration_db)
    )
    expected_tables = set(SQLModel.metadata.tables.keys())
    assert actual_tables == expected_tables

    # Table names alone would miss a column added to a model without a
    # migration, which is the far likelier drift, so compare the columns too.
    for table in sorted(expected_tables):
        expected_columns = set(SQLModel.metadata.tables[table].columns.keys())
        assert actual_columns[table] == expected_columns, table

    # An index is invisible to the column check and to most tests, which run on
    # create_all(), so a model index without a migration would only show up as
    # a slow query in production.
    for table in sorted(expected_tables):
        expected_indexes = {
            str(ix.name) for ix in SQLModel.metadata.tables[table].indexes
        }
        assert actual_indexes[table] == expected_indexes, table


async def _users_password_nullable(url: str) -> bool:
    """Report whether the migrated ``users.password`` column accepts NULL.

    Args:
        url: The migrated database.

    Returns:
        ``True`` if the column is nullable.
    """
    engine = create_async_engine(to_async_url(url))
    try:
        async with engine.connect() as conn:
            columns = await conn.run_sync(lambda c: inspect(c).get_columns("users"))
    finally:
        await engine.dispose()
    return next(c["nullable"] for c in columns if c["name"] == "password")


def test_upgrade_head_makes_user_password_nullable(migration_db: str) -> None:
    """An SSO-only user has no password, so the migrated column must allow NULL."""
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")

    assert asyncio.run(_users_password_nullable(migration_db)) is True


#: The revision before tenants had data keys, and the one that adds them.
_BEFORE_DATA_KEYS = "6e76a03c1493"
_DATA_KEYS = "9f4b2d7e1c08"


async def _run(url: str, fn: Callable[[Connection], T]) -> T:
    """Run ``fn`` on a synchronous connection to ``url``, in one transaction.

    Args:
        url: The database to connect to.
        fn: The work to run, handed the connection by ``run_sync``.

    Returns:
        Whatever ``fn`` returns.
    """
    engine = create_async_engine(to_async_url(url))
    try:
        async with engine.begin() as conn:
            return await conn.run_sync(fn)
    finally:
        await engine.dispose()


def _seed_master_encrypted(conn: Connection, master: SecretCipher) -> None:
    """Insert a user, a tenant and a secret as the pre-data-key schema stored them.

    Args:
        conn: Connection to a database at :data:`_BEFORE_DATA_KEYS`.
        master: The master cipher every value is encrypted with.
    """
    now = datetime.now(UTC)
    audit = {"created_at": now, "updated_at": now, "created_by": "u", "updated_by": "u"}
    users = sql_table(
        "users",
        *(column(n) for n in ("id", "first_name", "last_name", "email", "enabled")),
        *(column(n) for n in ("email_verified", "username", *audit)),
        column("roles", JSONColumn),
    )
    conn.execute(
        users.insert().values(
            id="u",
            first_name="A",
            last_name="B",
            email="a@example.com",
            enabled=True,
            email_verified=True,
            username="a",
            # Platform-scoped, so the user needs no tenant of its own.
            roles=["super_admin"],
            **audit,
        )
    )
    tenants = sql_table(
        "tenants",
        *(column(n) for n in ("id", "display_name", "name", "enabled", "llm_api_key")),
        *(column(n) for n in audit),
    )
    conn.execute(
        tenants.insert().values(
            id="t",
            display_name="T",
            name="t",
            enabled=True,
            llm_api_key=master.encrypt("sk-tenant"),
            **audit,
        )
    )
    secrets = sql_table(
        "secrets",
        *(column(n) for n in ("id", "tenant_id", "name", "type", *audit)),
        column("entries", JSONColumn),
    )
    conn.execute(
        secrets.insert().values(
            id="s",
            tenant_id="t",
            name="s",
            type="local",
            entries={"k": master.encrypt("v")},
            **audit,
        )
    )


def _read_tenant_values(conn: Connection) -> tuple[str | None, str, str]:
    """Return the tenant's data key (if the column exists) and its two ciphertexts.

    Args:
        conn: Connection to the migrated database.

    Returns:
        ``(data_key, llm_api_key, the secret entry's ciphertext)``.
    """
    has_data_key = any(
        c["name"] == "data_key" for c in inspect(conn).get_columns("tenants")
    )
    data_key = (
        conn.execute(text("SELECT data_key FROM tenants WHERE id = 't'")).scalar_one()
        if has_data_key
        else None
    )
    llm_api_key = conn.execute(
        text("SELECT llm_api_key FROM tenants WHERE id = 't'")
    ).scalar_one()
    entries = conn.execute(
        sql_table("secrets", column("entries", JSONColumn)).select()
    ).scalar_one()
    return data_key, llm_api_key, entries["k"]


def test_data_key_migration_moves_tenant_ciphertexts_and_back(
    migration_db: str,
) -> None:
    """Upgrading re-encrypts a tenant's values under its own data key; downgrading undoes it."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(cfg, _BEFORE_DATA_KEYS)
    # The key the migration loads: the per-test key file, not the process-wide
    # cached cipher, which an earlier test may have built from another file.
    master = SecretCipher(load_or_create_key())
    asyncio.run(_run(migration_db, lambda c: _seed_master_encrypted(c, master)))

    command.upgrade(cfg, _DATA_KEYS)
    wrapped, llm_api_key, entry = asyncio.run(_run(migration_db, _read_tenant_values))
    assert wrapped is not None
    data_key = SecretCipher(master.decrypt(wrapped).encode("ascii"))
    assert data_key.decrypt(llm_api_key) == "sk-tenant"
    assert data_key.decrypt(entry) == "v"
    with pytest.raises(ValueError):
        master.decrypt(entry)

    command.downgrade(cfg, _BEFORE_DATA_KEYS)
    wrapped, llm_api_key, entry = asyncio.run(_run(migration_db, _read_tenant_values))
    assert wrapped is None
    assert master.decrypt(llm_api_key) == "sk-tenant"
    assert master.decrypt(entry) == "v"
