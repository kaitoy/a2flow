"""add default tenant llm mode

Revision ID: c7d41e8a92b5
Revises: 3baf7438a170
Create Date: 2026-11-23 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7d41e8a92b5"
down_revision: str | Sequence[str] | None = "3baf7438a170"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the mode a new tenant's LLM starts with to the system settings."""
    # The `llmmode` enum already exists (`tenants.llm_mode` created it), and
    # add_column does not emit CREATE TYPE, so PostgreSQL reuses it.
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "default_tenant_llm_mode",
                sa.Enum(
                    "system_default", "super_admin", "tenant_admin", name="llmmode"
                ),
                nullable=False,
                server_default="system_default",
            )
        )


def downgrade() -> None:
    """Drop the column; the shared `llmmode` type stays, `tenants` still uses it."""
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.drop_column("default_tenant_llm_mode")
