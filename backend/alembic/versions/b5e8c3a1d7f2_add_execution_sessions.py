"""add execution sessions

Adds ``execution_sessions`` -- one row per ADK session taking part in a
workflow execution -- and ``workflow_tasks.session_id``, the session a task is
assigned to. Every existing execution gets its main-session row (sharing the
execution's ``session_id``), and every task that has already left ``pending``
is assigned to it, since until now the main session was the only one there was.
So is every ``pending`` task that is already runnable (all its dependencies
``completed``): tasks are assigned only when a task write frees them, and a run
in flight across the upgrade would otherwise find nothing assigned to it.

Revision ID: b5e8c3a1d7f2
Revises: 9d4f1a7c2e63
Create Date: 2026-09-30 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql
from sqlmodel.sql.sqltypes import AutoString

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5e8c3a1d7f2"
down_revision: str | Sequence[str] | None = "9d4f1a7c2e63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_status = sa.Enum(
    "queued",
    "running",
    "waiting_for_input",
    "waiting_for_approval",
    "idle",
    "done",
    "error",
    name="executionsessionstatus",
)


def _json() -> sa.types.TypeEngine[object]:
    """Return the column type ``models.base.JSONColumn`` renders to."""
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "execution_sessions",
        sa.Column("id", AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", AutoString(), nullable=False),
        sa.Column("updated_by", AutoString(), nullable=False),
        sa.Column("tenant_id", AutoString(), nullable=False),
        sa.Column("workflow_execution_id", AutoString(), nullable=False),
        sa.Column("parent_id", AutoString(), nullable=True),
        sa.Column("status", _status, nullable=False),
        sa.Column("pending_input", _json(), nullable=True),
        sa.Column("waiting_on", _json(), nullable=False, server_default="[]"),
        sa.Column("active_run_id", AutoString(), nullable=True),
        sa.Column("run_event_index", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["workflow_execution_id"],
            ["workflow_executions.id"],
            ondelete="CASCADE",
            name="fk_execution_sessions_workflow_execution_id",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["execution_sessions.id"],
            ondelete="CASCADE",
            name="fk_execution_sessions_parent_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_execution_sessions_tenant_id", "execution_sessions", ["tenant_id"]
    )
    op.create_index(
        "ix_execution_sessions_workflow_execution_id",
        "execution_sessions",
        ["workflow_execution_id"],
    )

    op.create_table(
        "session_stream_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", AutoString(), nullable=False),
        sa.Column("run_id", AutoString(), nullable=False),
        sa.Column("payload", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["execution_sessions.id"],
            ondelete="CASCADE",
            name="fk_session_stream_events_session_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        # Ids are viewers' stream cursors; see the model for why SQLite needs this.
        sqlite_autoincrement=True,
    )
    op.create_index(
        "ix_session_stream_events_session_id_id",
        "session_stream_events",
        ["session_id", "id"],
    )

    with op.batch_alter_table("workflow_tasks") as batch_op:
        batch_op.add_column(sa.Column("session_id", AutoString(), nullable=True))
        batch_op.create_foreign_key(
            "fk_workflow_tasks_session_id",
            "execution_sessions",
            ["session_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_workflow_tasks_session_id", ["session_id"])

    # PostgreSQL types the CASE as text, which its native enum will not take
    # without a cast; SQLite stores the enum as plain text and has no ``::``.
    cast = (
        "::executionsessionstatus" if op.get_bind().dialect.name == "postgresql" else ""
    )
    op.execute(
        f"""
        INSERT INTO execution_sessions (
            id, created_at, updated_at, created_by, updated_by, tenant_id,
            workflow_execution_id, parent_id, status
        )
        SELECT session_id, created_at, created_at, created_by, created_by,
               tenant_id, id, NULL,
               (CASE WHEN finished_at IS NULL THEN 'idle' ELSE 'done' END){cast}
        FROM workflow_executions
        """
    )
    op.execute(
        """
        UPDATE workflow_tasks
        SET session_id = (
            SELECT e.session_id FROM workflow_executions e
            WHERE e.id = workflow_tasks.workflow_execution_id
        )
        WHERE status <> 'pending'
           OR NOT EXISTS (
               SELECT 1 FROM workflow_task_dependencies d
               JOIN workflow_tasks p ON p.id = d.depends_on_id
               WHERE d.task_id = workflow_tasks.id AND p.status <> 'completed'
           )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("workflow_tasks") as batch_op:
        batch_op.drop_index("ix_workflow_tasks_session_id")
        batch_op.drop_constraint("fk_workflow_tasks_session_id", type_="foreignkey")
        batch_op.drop_column("session_id")
    op.drop_index(
        "ix_session_stream_events_session_id_id", table_name="session_stream_events"
    )
    op.drop_table("session_stream_events")
    op.drop_index(
        "ix_execution_sessions_workflow_execution_id", table_name="execution_sessions"
    )
    op.drop_index("ix_execution_sessions_tenant_id", table_name="execution_sessions")
    op.drop_table("execution_sessions")
    _status.drop(op.get_bind(), checkfirst=True)
