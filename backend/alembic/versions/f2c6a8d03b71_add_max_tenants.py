"""Add the tenant limit

Adds ``system_settings.max_tenants``, the most tenants a deployment may hold.
It is nullable and starts empty, which means no limit, so nothing changes for
an existing deployment until a ``super_admin`` sets one.

Revision ID: f2c6a8d03b71
Revises: 4b0db4cebefd
Create Date: 2026-11-18 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2c6a8d03b71"
down_revision: str | Sequence[str] | None = "4b0db4cebefd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.add_column(sa.Column("max_tenants", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.drop_column("max_tenants")
