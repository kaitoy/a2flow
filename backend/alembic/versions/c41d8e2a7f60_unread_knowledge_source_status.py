"""unread knowledge source status

Adds ``unread`` to ``knowledgesourcestatus``, ahead of ``pending`` so that the
enum's declaration order -- which list sorting follows -- matches the model.
SQLite stores the enum as plain text with no CHECK constraint, so only
PostgreSQL has a type to alter. PostgreSQL cannot drop an enum value, so the
downgrade leaves it in place.

Revision ID: c41d8e2a7f60
Revises: b7e2d4f19a3c
Create Date: 2026-11-02 18:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c41d8e2a7f60"
down_revision: str | Sequence[str] | None = "b7e2d4f19a3c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "ALTER TYPE knowledgesourcestatus ADD VALUE IF NOT EXISTS 'unread' "
            "BEFORE 'pending'"
        )


def downgrade() -> None:
    """Downgrade schema: nothing to undo (see the module docstring)."""
