"""Add per-tenant data keys

Gives every tenant ``tenants.data_key``: a random Fernet key wrapped with the
master key (``SECRET_ENCRYPTION_KEY`` or the key file, see
:mod:`infrastructure.secret_cipher`), which from now on encrypts everything the
tenant owns. The existing ciphertexts -- the tenant's stored credentials, its
local secrets' values and its MCP tool certificates' private keys -- are
re-encrypted here from the master key to the new data key; ``downgrade`` does
the reverse. A value that does not decrypt is left as it is (it was unreadable
already) and logged.

The master key is loaded only when there is a tenant to migrate, so upgrading a
fresh database never generates a key file.

Revision ID: 9f4b2d7e1c08
Revises: 6e76a03c1493
Create Date: 2026-11-19 22:00:00.000000

"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from cryptography.fernet import Fernet

from alembic import op
from infrastructure.secret_cipher import (
    SecretCipher,
    load_fallback_keys,
    load_or_create_key,
)
from models.base import JSONColumn

# revision identifiers, used by Alembic.
revision: str = "9f4b2d7e1c08"
down_revision: str | Sequence[str] | None = "6e76a03c1493"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)

#: The ``tenants`` columns holding Fernet ciphertext of the tenant's own.
_TENANT_COLUMNS = (
    "vault_credential",
    "global_vault_credential",
    "oidc_client_secret",
    "llm_api_key",
)

_tenants = sa.table(
    "tenants",
    sa.column("id", sa.String),
    sa.column("data_key", sa.String),
    *(sa.column(name, sa.String) for name in _TENANT_COLUMNS),
)
_secrets = sa.table(
    "secrets",
    sa.column("id", sa.String),
    sa.column("tenant_id", sa.String),
    sa.column("entries", JSONColumn),
)
_certificates = sa.table(
    "mcp_tool_certificates",
    sa.column("id", sa.String),
    sa.column("tenant_id", sa.String),
    sa.column("private_key_encrypted", sa.String),
)


def _recrypt(value: str, source: SecretCipher, target: SecretCipher, label: str) -> str:
    """Re-encrypt one ciphertext from ``source`` to ``target``.

    Args:
        value: The stored ciphertext.
        source: The cipher it is encrypted with now.
        target: The cipher to encrypt it with instead.
        label: Names the value in the log line when it does not decrypt.

    Returns:
        The new ciphertext, or ``value`` unchanged if it does not decrypt.
    """
    try:
        return target.encrypt(source.decrypt(value))
    except ValueError:
        logger.warning("%s does not decrypt; left unchanged", label)
        return value


def _rekey(*, to_data_keys: bool) -> None:
    """Move every tenant's ciphertexts between the master key and its data key.

    Args:
        to_data_keys: ``True`` to generate each tenant's data key and move its
            ciphertexts onto it, ``False`` to move them back to the master key.
    """
    bind = op.get_bind()
    tenants = bind.execute(sa.select(_tenants)).mappings().all()
    if not tenants:
        return
    # The fallbacks too: an upgrade that coincides with a master-key rotation
    # finds values still under the previous key.
    master = SecretCipher(load_or_create_key(), load_fallback_keys())
    for tenant in tenants:
        tenant_id = tenant["id"]
        if to_data_keys:
            wrapped = master.encrypt(Fernet.generate_key().decode("ascii"))
        else:
            wrapped = tenant["data_key"]
        data_key = SecretCipher(master.decrypt(wrapped).encode("ascii"))
        source, target = (master, data_key) if to_data_keys else (data_key, master)

        updates = {
            name: _recrypt(
                tenant[name], source, target, f"tenants.{name} of {tenant_id}"
            )
            for name in _TENANT_COLUMNS
            if tenant[name]
        }
        if to_data_keys:
            updates["data_key"] = wrapped
        if updates:
            bind.execute(
                sa.update(_tenants).where(_tenants.c.id == tenant_id).values(**updates)
            )

        secrets = bind.execute(
            sa.select(_secrets.c.id, _secrets.c.entries).where(
                _secrets.c.tenant_id == tenant_id
            )
        ).all()
        for secret_id, entries in secrets:
            if not entries:
                continue
            bind.execute(
                sa.update(_secrets)
                .where(_secrets.c.id == secret_id)
                .values(
                    entries={
                        key: _recrypt(
                            value, source, target, f"secret {secret_id}/{key}"
                        )
                        for key, value in entries.items()
                    }
                )
            )

        certificates = bind.execute(
            sa.select(_certificates.c.id, _certificates.c.private_key_encrypted).where(
                _certificates.c.tenant_id == tenant_id
            )
        ).all()
        for certificate_id, private_key in certificates:
            bind.execute(
                sa.update(_certificates)
                .where(_certificates.c.id == certificate_id)
                .values(
                    private_key_encrypted=_recrypt(
                        private_key,
                        source,
                        target,
                        f"private key of tool certificate {certificate_id}",
                    )
                )
            )


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.add_column(sa.Column("data_key", sa.String(), nullable=True))
    _rekey(to_data_keys=True)
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.alter_column("data_key", existing_type=sa.String(), nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    _rekey(to_data_keys=False)
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.drop_column("data_key")
