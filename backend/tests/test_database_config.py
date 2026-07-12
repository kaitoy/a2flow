"""Tests for database-backend switching via the ``DB_URL`` environment variable.

Covers URL normalization, dialect-specific ``IntegrityError`` classification,
and ADK session-service factory branching.
"""

import pytest
from google.adk.sessions.database_session_service import DatabaseSessionService
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from sqlalchemy.exc import IntegrityError

from dependencies import singletons
from infrastructure.database import is_sqlite_url, to_async_url
from repositories._integrity import is_foreign_key_error, is_unique_error


class TestToAsyncUrl:
    """URL normalization to async-driver variants."""

    def test_sqlite_gets_aiosqlite_driver(self) -> None:
        assert to_async_url("sqlite:///a2flow.db") == "sqlite+aiosqlite:///a2flow.db"

    def test_postgresql_gets_asyncpg_driver(self) -> None:
        assert (
            to_async_url("postgresql://u:p@host:5432/db")
            == "postgresql+asyncpg://u:p@host:5432/db"
        )

    def test_legacy_postgres_scheme_gets_asyncpg_driver(self) -> None:
        assert (
            to_async_url("postgres://u:p@host:5432/db")
            == "postgresql+asyncpg://u:p@host:5432/db"
        )

    def test_explicit_driver_passes_through(self) -> None:
        assert (
            to_async_url("sqlite+aiosqlite:///:memory:")
            == "sqlite+aiosqlite:///:memory:"
        )
        assert (
            to_async_url("postgresql+asyncpg://u:p@host/db")
            == "postgresql+asyncpg://u:p@host/db"
        )


class TestIsSqliteUrl:
    """SQLite URL detection used for session-service branching."""

    def test_sqlite_urls(self) -> None:
        assert is_sqlite_url("sqlite:///a2flow.db")
        assert is_sqlite_url("sqlite+aiosqlite:///:memory:")

    def test_non_sqlite_urls(self) -> None:
        assert not is_sqlite_url("postgresql://u:p@host/db")
        assert not is_sqlite_url("postgresql+asyncpg://u:p@host/db")


def _integrity_error(message: str) -> IntegrityError:
    """Build an IntegrityError whose ``orig`` carries the given driver message."""
    return IntegrityError("INSERT ...", {}, Exception(message))


class TestIntegrityClassification:
    """Constraint-failure classification for both SQLite and PostgreSQL."""

    def test_sqlite_foreign_key_message(self) -> None:
        assert is_foreign_key_error(_integrity_error("FOREIGN KEY constraint failed"))

    def test_postgresql_foreign_key_message(self) -> None:
        assert is_foreign_key_error(
            _integrity_error(
                'insert or update on table "workflows" violates foreign key'
                ' constraint "fk_workflows_agent_skill_id"'
            )
        )

    def test_sqlite_unique_message(self) -> None:
        assert is_unique_error(
            _integrity_error("UNIQUE constraint failed: users.username")
        )

    def test_postgresql_unique_message(self) -> None:
        assert is_unique_error(
            _integrity_error(
                'duplicate key value violates unique constraint "uq_users_username"'
            )
        )

    def test_unrelated_message_matches_neither(self) -> None:
        error = _integrity_error("NOT NULL constraint failed: users.username")
        assert not is_foreign_key_error(error)
        assert not is_unique_error(error)


class TestSessionServiceFactory:
    """get_session_service branches on the DB_URL scheme."""

    def _build(self, monkeypatch: pytest.MonkeyPatch, db_url: str) -> object:
        """Invoke the un-cached factory with a patched DB_URL."""
        monkeypatch.setattr(singletons, "DB_URL", db_url)
        monkeypatch.setattr(singletons, "ASYNC_DB_URL", to_async_url(db_url))
        return singletons.get_session_service.__wrapped__()

    def test_sqlite_url_uses_sqlite_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service = self._build(monkeypatch, "sqlite:///a2flow.db")
        assert isinstance(service, SqliteSessionService)

    def test_postgresql_url_uses_database_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service = self._build(monkeypatch, "postgresql://u:p@localhost:5432/a2flow")
        assert isinstance(service, DatabaseSessionService)
