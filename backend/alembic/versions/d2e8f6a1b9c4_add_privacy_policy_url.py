"""add privacy policy url

Revision ID: d2e8f6a1b9c4
Revises: c7d41e8a92b5
Create Date: 2026-11-23 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2e8f6a1b9c4"
down_revision: str | Sequence[str] | None = "c7d41e8a92b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the privacy policy address the sign-in pages link to."""
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "privacy_policy_url",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=True,
            )
        )


def downgrade() -> None:
    """Drop the privacy policy address."""
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.drop_column("privacy_policy_url")
