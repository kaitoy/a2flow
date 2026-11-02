"""workflow prompt

Splits a workflow's text into a prompt and a description. What used to be
``description`` / ``generated_description`` was always the text handed to a
run as context, so those columns become ``prompt`` / ``generated_prompt``,
and a new, nullable ``description`` holds a plain explanation no run reads.
The published snapshot follows the same split (its old ``description`` held
the resolved prompt), and a run's copied ``description`` becomes ``prompt``.

Renames go through ``batch_alter_table`` so SQLite can apply them.

Revision ID: b7e2d4f19a3c
Revises: 9c618064c67b
Create Date: 2026-11-02 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e2d4f19a3c"
down_revision: str | Sequence[str] | None = "9c618064c67b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _description() -> sa.Column[str]:
    """Return a fresh nullable ``description`` column."""
    return sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True)


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("workflows") as batch:
        batch.alter_column("description", new_column_name="prompt")
        batch.alter_column("generated_description", new_column_name="generated_prompt")
    op.add_column("workflows", _description())
    with op.batch_alter_table("workflow_published_versions") as batch:
        batch.alter_column("description", new_column_name="prompt")
    op.add_column("workflow_published_versions", _description())
    with op.batch_alter_table("workflow_executions") as batch:
        batch.alter_column("description", new_column_name="prompt")


def downgrade() -> None:
    """Downgrade schema, dropping the new descriptions."""
    with op.batch_alter_table("workflow_executions") as batch:
        batch.alter_column("prompt", new_column_name="description")
    with op.batch_alter_table("workflow_published_versions") as batch:
        batch.drop_column("description")
        batch.alter_column("prompt", new_column_name="description")
    with op.batch_alter_table("workflows") as batch:
        batch.drop_column("description")
        batch.alter_column("generated_prompt", new_column_name="generated_description")
        batch.alter_column("prompt", new_column_name="description")
