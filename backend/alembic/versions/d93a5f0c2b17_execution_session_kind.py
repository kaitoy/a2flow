"""execution session kind

Adds ``execution_sessions.kind``, telling a session that works the run's tasks
(``task``, every existing row) from a consultation forked while one waits on an
approval (``consultation``). The server default fills the existing rows.
A partial unique index then allows at most one open (not ``done``)
consultation per session, so two first questions racing each other share one.

Revision ID: d93a5f0c2b17
Revises: c41d8e2a7f60
Create Date: 2026-11-02 18:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d93a5f0c2b17"
down_revision: str | Sequence[str] | None = "c41d8e2a7f60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KIND = sa.Enum("task", "consultation", name="executionsessionkind")

_OPEN_CONSULTATION = sa.text("kind = 'consultation' AND status != 'done'")


def upgrade() -> None:
    """Upgrade schema."""
    _KIND.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "execution_sessions",
        sa.Column("kind", _KIND, nullable=False, server_default="task"),
    )
    op.create_index(
        "uq_execution_sessions_open_consultation",
        "execution_sessions",
        ["parent_id"],
        unique=True,
        sqlite_where=_OPEN_CONSULTATION,
        postgresql_where=_OPEN_CONSULTATION,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_execution_sessions_open_consultation", table_name="execution_sessions"
    )
    with op.batch_alter_table("execution_sessions") as batch:
        batch.drop_column("kind")
    _KIND.drop(op.get_bind(), checkfirst=True)
