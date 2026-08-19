"""Tests that the Alembic migration set matches the current SQLModel metadata.

Guards against migration files drifting from the models they describe: if a
model changes without an accompanying migration, ``alembic upgrade head``
against a fresh database won't produce the same schema ``SQLModel.metadata``
declares, and this test catches that before it reaches a real deploy.
"""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlmodel import SQLModel

from alembic import command

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_upgrade_head_matches_model_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "migration_test.db"
    monkeypatch.setenv("DB_URL", f"sqlite:///{db_path}")

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    actual_tables = set(inspector.get_table_names()) - {"alembic_version"}
    expected_tables = set(SQLModel.metadata.tables.keys())
    assert actual_tables == expected_tables

    # Table names alone would miss a column added to a model without a
    # migration, which is the far likelier drift, so compare the columns too.
    for table in sorted(expected_tables):
        actual_columns = {c["name"] for c in inspector.get_columns(table)}
        expected_columns = set(SQLModel.metadata.tables[table].columns.keys())
        assert actual_columns == expected_columns, table
