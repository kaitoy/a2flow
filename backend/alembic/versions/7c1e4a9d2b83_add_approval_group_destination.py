"""add approval group destination

Adds the two columns that let an approval be addressed to a user group instead
of a single user:

* ``approvals.approver_group_id`` -- the group destination, mutually exclusive
  with the existing ``approver`` column (``ck_approvals_single_destination``).
* ``approvals.decided_by`` -- which user actually resolved the request, stamped
  alongside ``decided_at``.

No data is backfilled. ``decided_by`` stays ``NULL`` for approvals decided
before this migration: the resolver is *usually* recoverable from
``updated_by``, but that column also moves when the response comment is edited
afterwards, so backfilling from it would record a decision that never happened.

``ck_approvals_single_destination`` is "at most one destination", not an
``XOR``: ``approver`` has always been nullable, so pre-existing rows may name
no destination at all and must keep validating. "Exactly one" is enforced on
the write path by ``models.approval.ApprovalCreate``.

Every ``ALTER`` runs inside ``batch_alter_table`` because SQLite -- the default
``DB_URL`` -- supports neither ``ADD CONSTRAINT`` for foreign keys nor for check
constraints; batch mode rebuilds the table instead. ``alembic/env.py`` does not
set ``render_as_batch``, so autogenerate would have emitted the unsupported bare
form. On PostgreSQL batch mode degrades to plain ``ALTER TABLE`` statements.

Revision ID: 7c1e4a9d2b83
Revises: 3baf7438a170
Create Date: 2026-08-18 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c1e4a9d2b83"
down_revision: str | Sequence[str] | None = "3baf7438a170"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("approvals", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "approver_group_id",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("decided_by", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_approvals_approver_group_id",
            "user_groups",
            ["approver_group_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_approvals_decided_by",
            "users",
            ["decided_by"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_check_constraint(
            "ck_approvals_single_destination",
            "approver IS NULL OR approver_group_id IS NULL",
        )
        batch_op.create_index(
            "ix_approvals_approver_group_id", ["approver_group_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("approvals", schema=None) as batch_op:
        batch_op.drop_index("ix_approvals_approver_group_id")
        batch_op.drop_constraint("ck_approvals_single_destination", type_="check")
        batch_op.drop_constraint("fk_approvals_decided_by", type_="foreignkey")
        batch_op.drop_constraint("fk_approvals_approver_group_id", type_="foreignkey")
        batch_op.drop_column("decided_by")
        batch_op.drop_column("approver_group_id")
