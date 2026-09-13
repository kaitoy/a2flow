"""add access_control to tags

Revision ID: 3bf69554bdb3
Revises: c9b571697e35
Create Date: 2026-09-13 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3bf69554bdb3"
down_revision: str | Sequence[str] | None = "c9b571697e35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing tags stay plain filters: the server default backfills ``false``
    # so the column can be NOT NULL from the start.
    op.add_column(
        "tags",
        sa.Column(
            "access_control",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Batch mode so SQLite (which rebuilds the table to drop a column) and
    # PostgreSQL (plain ALTER TABLE) both work.
    with op.batch_alter_table("tags") as batch_op:
        batch_op.drop_column("access_control")
