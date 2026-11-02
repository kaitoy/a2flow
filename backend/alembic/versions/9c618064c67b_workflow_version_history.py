"""workflow version history

Keeps every published snapshot of a workflow instead of overwriting one row:
``workflow_published_versions`` gains a ``version`` counter (existing rows
become version 1) and its uniqueness moves from ``workflow_id`` to
``(workflow_id, version)``. ``workflow_executions`` gains ``workflow_version``,
the version a run copied its design from.

Both constraint changes go through ``batch_alter_table`` because SQLite cannot
add or drop a constraint in place.

Revision ID: 9c618064c67b
Revises: 3baf7438a170
Create Date: 2026-11-02 08:10:21.302450

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c618064c67b"
down_revision: str | Sequence[str] | None = "3baf7438a170"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "workflow_executions",
        sa.Column("workflow_version", sa.Integer(), nullable=True),
    )
    with op.batch_alter_table("workflow_published_versions") as batch:
        batch.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default="1")
        )
        batch.drop_constraint(
            "uq_workflow_published_versions_workflow_id", type_="unique"
        )
        batch.create_unique_constraint(
            "uq_workflow_published_versions_workflow_id_version",
            ["workflow_id", "version"],
        )


def downgrade() -> None:
    """Downgrade schema, keeping only each workflow's latest version."""
    op.execute(
        "DELETE FROM workflow_published_versions WHERE version < ("
        "SELECT MAX(v.version) FROM workflow_published_versions v "
        "WHERE v.workflow_id = workflow_published_versions.workflow_id)"
    )
    with op.batch_alter_table("workflow_published_versions") as batch:
        batch.drop_constraint(
            "uq_workflow_published_versions_workflow_id_version", type_="unique"
        )
        batch.create_unique_constraint(
            "uq_workflow_published_versions_workflow_id", ["workflow_id"]
        )
        batch.drop_column("version")
    op.drop_column("workflow_executions", "workflow_version")
