"""add script mcp servers

Adds the ``script`` MCP transport and the ``language`` / ``source`` columns it
uses. Hand-written: autogenerate does not detect a value added to an existing
enum. On SQLite ``mcptransport`` is a plain ``VARCHAR`` with no ``CHECK``
constraint, so only PostgreSQL's native enum type needs the new value.

Revision ID: 7c1e2d9a4b50
Revises: 3baf7438a170
Create Date: 2026-09-25 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlmodel.sql.sqltypes import AutoString

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c1e2d9a4b50"
down_revision: str | Sequence[str] | None = "3baf7438a170"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_script_language = sa.Enum("python", "javascript", name="scriptlanguage")


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE mcptransport ADD VALUE IF NOT EXISTS 'script'")
    _script_language.create(op.get_bind(), checkfirst=True)
    with op.batch_alter_table("mcp_servers") as batch_op:
        batch_op.add_column(sa.Column("language", _script_language, nullable=True))
        batch_op.add_column(sa.Column("source", AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema.

    PostgreSQL cannot drop a value from an enum type, so ``script`` stays in
    ``mcptransport``; script servers themselves are deleted first, since their
    rows would be meaningless without the columns.
    """
    op.execute("DELETE FROM mcp_servers WHERE transport = 'script'")
    with op.batch_alter_table("mcp_servers") as batch_op:
        batch_op.drop_column("source")
        batch_op.drop_column("language")
    _script_language.drop(op.get_bind(), checkfirst=True)
