"""Add the must-change-password flag

Adds ``users.must_change_password``, set when an admin chooses a user's password
(on create, or on resetting someone else's) and cleared once the user changes it
themselves. It starts false for every existing user, so nobody is suddenly
locked out of the app by the upgrade.

Revision ID: a7d3e9c41f2b
Revises: f2c6a8d03b71
Create Date: 2026-11-18 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7d3e9c41f2b"
down_revision: str | Sequence[str] | None = "f2c6a8d03b71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "must_change_password",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("must_change_password")
