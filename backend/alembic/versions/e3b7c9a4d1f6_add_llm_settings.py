"""Add LLM settings

Adds the platform-wide LLM (``system_settings.llm_model`` and
``system_settings.llm_api_key``) and a tenant's own (``tenants.llm_mode``,
``tenants.llm_model``, ``tenants.llm_api_key``). Every existing tenant starts in
``system_default`` mode, so nothing changes for it until a ``super_admin`` says
otherwise. Both API keys are Fernet ciphertext.

Revision ID: e3b7c9a4d1f6
Revises: d8a41f0b7e25
Create Date: 2026-11-15 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3b7c9a4d1f6"
down_revision: str | Sequence[str] | None = "d8a41f0b7e25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ``add_column`` does not create a PostgreSQL enum type the way ``create_table``
# does, so the type is created (and dropped) by hand; SQLite has no such type.
_llm_mode = sa.Enum("system_default", "super_admin", "tenant_admin", name="llmmode")


def upgrade() -> None:
    """Upgrade schema."""
    _llm_mode.create(op.get_bind(), checkfirst=True)
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.add_column(sa.Column("llm_model", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("llm_api_key", sa.String(), nullable=True))
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.add_column(
            sa.Column(
                "llm_mode",
                _llm_mode,
                nullable=False,
                server_default="system_default",
            )
        )
        batch_op.add_column(sa.Column("llm_model", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("llm_api_key", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.drop_column("llm_api_key")
        batch_op.drop_column("llm_model")
        batch_op.drop_column("llm_mode")
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.drop_column("llm_api_key")
        batch_op.drop_column("llm_model")
    _llm_mode.drop(op.get_bind(), checkfirst=True)
