"""Secret data models for create, update, database persistence, and read views.

A Secret is a named credential that MCP server headers reference through
``${secret:NAME}`` placeholders and AgentSkills reference through
``repo_auth_secret`` for authenticated repository clones. Two shapes exist,
discriminated by ``type``:

* ``local`` — the plaintext value is submitted once and stored in the ``value``
  column as Fernet ciphertext (see :mod:`infrastructure.secret_cipher`).
* ``vault`` — only a HashiCorp Vault KV v2 reference (``vault_mount``,
  ``vault_path``, ``vault_key``) is stored; the value is fetched live at
  resolution time (see :mod:`infrastructure.vault_client`).

Responses use :class:`SecretRead`, which omits ``value`` entirely so neither
the plaintext nor the ciphertext is ever serialized to clients — the same
write-only pattern as :class:`models.user.User.password`.

References are by name and resolved lazily: renaming or deleting a secret that
a header placeholder still mentions does not fail at edit time, but the next
connection attempt raises a resolution error naming the missing secret.
"""

from enum import StrEnum

from pydantic import model_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import Index, UniqueConstraint
from sqlmodel import SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity
from models.constraints import SecretName, SecretValue, VaultKey, VaultMount, VaultPath

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class SecretType(StrEnum):
    """Where a secret's value lives: encrypted in the local DB, or in Vault."""

    local = "local"
    vault = "vault"


class SecretUpdate(SQLModel):
    """Partial update payload for a Secret — all fields are optional.

    Omitting ``value`` on a ``local`` secret keeps the stored ciphertext
    unchanged. The per-type shape rules (which fields must be present or
    absent) are enforced against the merged result by
    :class:`services.secret.SecretService`, because a PATCH body alone cannot
    know the effective type.
    """

    model_config = _alias_config
    name: SecretName | None = None
    type: SecretType | None = None
    value: SecretValue | None = None
    vault_mount: VaultMount | None = None
    vault_path: VaultPath | None = None
    vault_key: VaultKey | None = None


class SecretCreate(SecretUpdate):
    """Creation payload for a Secret with required fields and shape validation."""

    name: SecretName
    type: SecretType

    @model_validator(mode="after")
    def _validate_shape(self) -> "SecretCreate":
        """Enforce exactly one shape per type.

        Returns:
            The validated model instance.

        Raises:
            ValueError: If a ``local`` secret is missing ``value`` or carries
                Vault fields, or a ``vault`` secret is missing any Vault field
                or carries a ``value``.
        """
        vault_fields = (self.vault_mount, self.vault_path, self.vault_key)
        if self.type is SecretType.local:
            if self.value is None:
                raise ValueError("A local secret requires a value")
            if any(field is not None for field in vault_fields):
                raise ValueError("A local secret must not set Vault fields")
        elif self.type is SecretType.vault:
            if any(field is None for field in vault_fields):
                raise ValueError(
                    "A vault secret requires vaultMount, vaultPath, and vaultKey"
                )
            if self.value is not None:
                raise ValueError("A vault secret must not set a value")
        return self


class Secret(SecretCreate, BaseEntity, table=True):
    """Database-persisted secret.

    The ``value`` column holds Fernet ciphertext for ``local`` secrets and is
    ``NULL`` for ``vault`` secrets. It is never exposed through the API: all
    routes respond with :class:`SecretRead`.
    """

    __tablename__ = "secrets"
    __table_args__ = (
        UniqueConstraint("name", name="uq_secrets_name"),
        Index("ix_secrets_name", "name"),
    )


class SecretRead(BaseEntity):
    """Read view of a Secret returned by the API, excluding the value entirely."""

    model_config = _alias_config
    name: str
    type: SecretType
    vault_mount: str | None = None
    vault_path: str | None = None
    vault_key: str | None = None
