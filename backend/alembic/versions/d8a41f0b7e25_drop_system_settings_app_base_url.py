"""Drop system_settings.app_base_url

The deployment's public base URL is now read from the ``APP_BASE_URL``
environment variable alone, which also derives the default CORS origin and
the cookies' ``Secure`` flag from it, so the column the admin UI used to edit
is gone. A value stored there is not carried over: set ``APP_BASE_URL``
instead. The downgrade restores the column empty.

Revision ID: d8a41f0b7e25
Revises: c5dc77c83686
Create Date: 2026-11-14 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8a41f0b7e25"
down_revision: str | Sequence[str] | None = "c5dc77c83686"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.drop_column("app_base_url")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.add_column(sa.Column("app_base_url", sa.String(), nullable=True))
