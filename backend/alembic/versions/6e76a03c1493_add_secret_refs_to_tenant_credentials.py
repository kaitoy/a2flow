"""Add secret references for the tenant's SSO client secret and LLM key

Adds ``tenants.oidc_client_secret_ref`` and ``tenants.llm_api_key_ref``: a
``NAME/KEY`` reference to one of the tenant's secrets (local or Vault-backed),
read each time it is used, in place of the encrypted value stored in
``oidc_client_secret`` / ``llm_api_key``. Both start empty, so every existing
tenant keeps using its stored values.

Revision ID: 6e76a03c1493
Revises: a7d3e9c41f2b
Create Date: 2026-11-19 20:54:41.686916

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6e76a03c1493"
down_revision: str | Sequence[str] | None = "a7d3e9c41f2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.add_column(sa.Column("llm_api_key_ref", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("oidc_client_secret_ref", sa.String(), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.drop_column("oidc_client_secret_ref")
        batch_op.drop_column("llm_api_key_ref")
