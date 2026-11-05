"""Add user language and notification params

Adds ``users.language``, the language the GUI is shown in (``NULL`` follows the
browser), and ``notifications.params``, the values the web UI fills into its
translation of a notification type's fixed wording (``NULL`` on rows written
before this revision, which are shown as stored when they need a value).

Revision ID: 7c2e41d9a6f3
Revises: 61a67025a0bc
Create Date: 2026-11-05 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c2e41d9a6f3"
down_revision: str | Sequence[str] | None = "61a67025a0bc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("language", sa.String(length=16), nullable=True))
    op.add_column(
        "notifications",
        sa.Column(
            "params",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("notifications", "params")
    op.drop_column("users", "language")
