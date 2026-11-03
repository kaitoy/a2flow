"""Index due sessions and notifications by recipient

Adds ``execution_sessions.status`` for the session runner's due-session poll,
widens the notifications recipient index to ``(user_id, created_at)`` for the
bell's newest-first listing, and drops ``ix_auth_sessions_token_hash``, which
only duplicated the index behind ``uq_auth_sessions_token_hash``.

Revision ID: 61a67025a0bc
Revises: 3baf7438a170
Create Date: 2026-11-03 15:55:57.446209

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "61a67025a0bc"
down_revision: str | Sequence[str] | None = "3baf7438a170"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index("ix_auth_sessions_token_hash", table_name="auth_sessions")
    op.create_index(
        "ix_execution_sessions_status", "execution_sessions", ["status"], unique=False
    )
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.create_index(
        "ix_notifications_user_id_created_at",
        "notifications",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_notifications_user_id_created_at", table_name="notifications")
    op.create_index(
        "ix_notifications_user_id", "notifications", ["user_id"], unique=False
    )
    op.drop_index("ix_execution_sessions_status", table_name="execution_sessions")
    op.create_index(
        "ix_auth_sessions_token_hash", "auth_sessions", ["token_hash"], unique=False
    )
