"""add skill revision store fields

Revision ID: 0739268e975b
Revises: eb161101d0b7
Create Date: 2026-07-12 09:49:32.239231

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0739268e975b"
down_revision: str | Sequence[str] | None = "eb161101d0b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # `pending` as a server default, not just a Python-side one: existing rows
    # need a value for the NOT NULL column, and it is the honest one -- their
    # repositories have never been published into the revisioned store, so an
    # admin has to pull each skill once before workflows can run on it again.
    op.add_column(
        "agent_skills",
        sa.Column(
            "sync_status",
            sa.Enum("pending", "ready", "failed", name="skillsyncstatus"),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "agent_skills",
        sa.Column("sync_error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        "agent_skills",
        sa.Column("commit_sha", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        "agent_skills",
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Nullable, and left NULL for existing rows: they were pinned to an absolute
    # local path, not a revision, so there is no sha to backfill. Those sessions
    # fall back to whatever revision their skill publishes on its first pull
    # (see `WorkflowSessionService.resolve_agent`).
    op.add_column(
        "workflow_sessions",
        sa.Column(
            "agent_skill_commit_sha",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
    )
    op.drop_column("workflow_sessions", "skill_dir")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "workflow_sessions",
        sa.Column("skill_dir", sa.VARCHAR(), nullable=False, server_default=""),
    )
    op.drop_column("workflow_sessions", "agent_skill_commit_sha")
    op.drop_column("agent_skills", "synced_at")
    op.drop_column("agent_skills", "commit_sha")
    op.drop_column("agent_skills", "sync_error")
    op.drop_column("agent_skills", "sync_status")
    sa.Enum(name="skillsyncstatus").drop(op.get_bind(), checkfirst=True)
