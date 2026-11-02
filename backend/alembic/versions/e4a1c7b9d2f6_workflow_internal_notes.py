"""workflow internal notes

Adds ``workflows.internal_notes``: free-text notes shown only to an admin,
developer, or reviewer (why a version was restored, say). Not versioned, so
the published snapshot table is untouched.

Revision ID: e4a1c7b9d2f6
Revises: d93a5f0c2b17
Create Date: 2026-11-02 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4a1c7b9d2f6"
down_revision: str | Sequence[str] | None = "d93a5f0c2b17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "workflows",
        sa.Column("internal_notes", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("workflows") as batch:
        batch.drop_column("internal_notes")
