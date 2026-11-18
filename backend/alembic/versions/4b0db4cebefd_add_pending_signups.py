"""Add pending sign-ups

Adds ``pending_signups``: self-service sign-up forms waiting for the visitor to
open the confirmation link mailed to them.

Revision ID: 4b0db4cebefd
Revises: e3b7c9a4d1f6
Create Date: 2026-11-17 23:34:48.296911

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b0db4cebefd"
down_revision: str | Sequence[str] | None = "e3b7c9a4d1f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "pending_signups",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("first_name", sa.String(), nullable=False),
        sa.Column("last_name", sa.String(), nullable=False),
        sa.Column("password", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_pending_signups_token_hash"),
    )
    op.create_index(
        "ix_pending_signups_email_created_at",
        "pending_signups",
        ["email", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_pending_signups_email_created_at", table_name="pending_signups")
    op.drop_table("pending_signups")
