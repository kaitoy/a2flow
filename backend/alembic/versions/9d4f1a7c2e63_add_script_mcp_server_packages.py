"""add script mcp server packages

Adds ``mcp_servers.packages``: the pip or npm packages a script server installs
before it runs. Existing rows get an empty list.

Revision ID: 9d4f1a7c2e63
Revises: 7c1e2d9a4b50
Create Date: 2026-09-27 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d4f1a7c2e63"
down_revision: str | Sequence[str] | None = "7c1e2d9a4b50"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("mcp_servers") as batch_op:
        batch_op.add_column(
            sa.Column(
                "packages",
                sa.JSON().with_variant(
                    postgresql.JSONB(astext_type=Text()), "postgresql"
                ),
                nullable=False,
                server_default="[]",
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("mcp_servers") as batch_op:
        batch_op.drop_column("packages")
