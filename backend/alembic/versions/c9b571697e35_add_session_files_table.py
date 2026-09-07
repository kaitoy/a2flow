"""add session_files table

Revision ID: c9b571697e35
Revises: 3baf7438a170
Create Date: 2026-09-07 21:33:20.832212

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9b571697e35"
down_revision: str | Sequence[str] | None = "3baf7438a170"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "session_files",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("updated_by", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tenant_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "workflow_execution_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("content_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "origin",
            sa.Enum("user", "agent", name="sessionfileorigin"),
            nullable=False,
        ),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["workflow_execution_id"],
            ["workflow_executions.id"],
            name="fk_session_files_workflow_execution_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_execution_id", "name", name="uq_session_files_execution_name"
        ),
    )
    op.create_index(
        op.f("ix_session_files_tenant_id"), "session_files", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_session_files_workflow_execution_id",
        "session_files",
        ["workflow_execution_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_session_files_workflow_execution_id", table_name="session_files")
    op.drop_index(op.f("ix_session_files_tenant_id"), table_name="session_files")
    op.drop_table("session_files")
    sa.Enum(name="sessionfileorigin").drop(op.get_bind(), checkfirst=True)
