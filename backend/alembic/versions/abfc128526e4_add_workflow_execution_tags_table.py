"""add workflow_execution_tags table

Revision ID: abfc128526e4
Revises: 3bf69554bdb3
Create Date: 2026-09-15 22:51:39.883358

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "abfc128526e4"
down_revision: str | Sequence[str] | None = "3bf69554bdb3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "workflow_execution_tags",
        sa.Column("resource_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tag_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(
            ["resource_id"], ["workflow_executions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("resource_id", "tag_id"),
    )
    op.create_index(
        "ix_workflow_execution_tags_tag_id",
        "workflow_execution_tags",
        ["tag_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_workflow_execution_tags_tag_id", table_name="workflow_execution_tags"
    )
    op.drop_table("workflow_execution_tags")
