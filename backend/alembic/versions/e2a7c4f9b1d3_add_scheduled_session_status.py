"""add scheduled session status

Adds the ``scheduled`` execution-session status and the ``resume_at`` column
it waits on. Hand-written: autogenerate does not detect a value added to an
existing enum. On SQLite ``executionsessionstatus`` is a plain ``VARCHAR``, so
only PostgreSQL's native enum type needs the new value -- placed before
``idle`` so the type's order matches the declaration order lists sort by.

Revision ID: e2a7c4f9b1d3
Revises: b5e8c3a1d7f2
Create Date: 2026-10-03 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2a7c4f9b1d3"
down_revision: str | Sequence[str] | None = "b5e8c3a1d7f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "ALTER TYPE executionsessionstatus "
            "ADD VALUE IF NOT EXISTS 'scheduled' BEFORE 'idle'"
        )
    with op.batch_alter_table("execution_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("resume_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema.

    PostgreSQL cannot drop a value from an enum type, so ``scheduled`` stays in
    ``executionsessionstatus``; sessions waiting on a time are left ``idle``.
    """
    op.execute(
        "UPDATE execution_sessions SET status = 'idle' WHERE status = 'scheduled'"
    )
    with op.batch_alter_table("execution_sessions") as batch_op:
        batch_op.drop_column("resume_at")
