"""add roles to users

Revision ID: eb161101d0b7
Revises: 3baf7438a170
Create Date: 2026-07-11 19:18:45.909331

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "eb161101d0b7"
down_revision: str | Sequence[str] | None = "3baf7438a170"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column(
            "roles",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    # Grant the pre-existing seeded admin account the super_admin role so an
    # upgraded deployment keeps a user able to manage roles.
    op.execute(
        """UPDATE users SET roles = '["super_admin"]' WHERE username = 'admin'"""
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "roles")
