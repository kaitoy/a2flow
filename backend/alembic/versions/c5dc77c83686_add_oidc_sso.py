"""Add OIDC single sign-on

Adds the per-tenant OIDC configuration (``tenants.oidc_*``), the provider's
subject id on a user (``users.oidc_subject``, unique per tenant), makes
``users.password`` nullable for accounts that only sign in through SSO, and adds
``user_groups.idp_group`` (unique per tenant) to mirror an identity-provider
group.

The downgrade restores ``users.password NOT NULL``, so it fails while any
SSO-only user (``password IS NULL``) exists; delete those users first.

Revision ID: c5dc77c83686
Revises: 7c2e41d9a6f3
Create Date: 2026-11-10 23:31:57.207713

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5dc77c83686"
down_revision: str | Sequence[str] | None = "7c2e41d9a6f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.add_column(
            sa.Column(
                "oidc_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch_op.add_column(sa.Column("oidc_issuer", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("oidc_client_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("oidc_client_secret", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "oidc_groups_claim",
                sa.String(),
                nullable=False,
                server_default="groups",
            )
        )
        batch_op.add_column(
            sa.Column(
                "oidc_trust_email",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("oidc_subject", sa.String(length=255), nullable=True)
        )
        batch_op.alter_column("password", existing_type=sa.String(), nullable=True)
        batch_op.create_index(
            "ix_users_tenant_id_oidc_subject",
            ["tenant_id", "oidc_subject"],
            unique=True,
            postgresql_where=sa.text("oidc_subject IS NOT NULL"),
            sqlite_where=sa.text("oidc_subject IS NOT NULL"),
        )

    with op.batch_alter_table("user_groups") as batch_op:
        batch_op.add_column(
            sa.Column("idp_group", sa.String(length=255), nullable=True)
        )
        batch_op.create_index(
            "ix_user_groups_tenant_id_idp_group",
            ["tenant_id", "idp_group"],
            unique=True,
            postgresql_where=sa.text("idp_group IS NOT NULL"),
            sqlite_where=sa.text("idp_group IS NOT NULL"),
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("user_groups") as batch_op:
        batch_op.drop_index(
            "ix_user_groups_tenant_id_idp_group",
            postgresql_where=sa.text("idp_group IS NOT NULL"),
            sqlite_where=sa.text("idp_group IS NOT NULL"),
        )
        batch_op.drop_column("idp_group")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index(
            "ix_users_tenant_id_oidc_subject",
            postgresql_where=sa.text("oidc_subject IS NOT NULL"),
            sqlite_where=sa.text("oidc_subject IS NOT NULL"),
        )
        batch_op.alter_column("password", existing_type=sa.String(), nullable=False)
        batch_op.drop_column("oidc_subject")

    with op.batch_alter_table("tenants") as batch_op:
        batch_op.drop_column("oidc_trust_email")
        batch_op.drop_column("oidc_groups_claim")
        batch_op.drop_column("oidc_client_secret")
        batch_op.drop_column("oidc_client_id")
        batch_op.drop_column("oidc_issuer")
        batch_op.drop_column("oidc_enabled")
