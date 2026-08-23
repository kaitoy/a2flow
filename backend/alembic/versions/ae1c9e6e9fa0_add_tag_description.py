"""add tag description

Adds a nullable free-text ``description`` column to ``tags``. No FK or check
constraint is involved, so a plain ``add_column``/``drop_column`` is enough --
unlike ``7c1e4a9d2b83``, this migration does not need ``batch_alter_table``.

Revision ID: ae1c9e6e9fa0
Revises: 7c1e4a9d2b83
Create Date: 2026-08-23 18:58:13.837298

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ae1c9e6e9fa0"
down_revision: str | Sequence[str] | None = "7c1e4a9d2b83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tags",
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tags", "description")
