"""Secret data models for create, update, database persistence, and read views.

A Secret is a named bundle of key/value entries — the same shape HashiCorp
Vault's KV engine uses, where one path holds a map of keys to values. MCP server
headers and environment variables reference a single entry through
``${secret:NAME/KEY}`` placeholders, and AgentSkills reference one through
``repo_auth_password``. The key is always required: a bare name identifies a map,
not a value.

Two shapes exist, discriminated by ``type``:

* ``local`` — the plaintext entries are submitted once and stored in the
  ``entries`` JSON column as ``{key: Fernet ciphertext}``. Keys stay in
  plaintext so they can be listed without decrypting anything (see
  :mod:`infrastructure.secret_cipher`).
* ``vault`` — only a HashiCorp Vault KV v2 reference (``vault_mount``,
  ``vault_path``) is stored; every key at that path is readable, fetched live at
  resolution time (see :mod:`infrastructure.vault_client`).

Responses use :class:`SecretRead`, which replaces ``entries`` with a bare
``keys`` list so no value — plaintext or ciphertext — is ever serialized to
clients, the same write-only pattern as :class:`models.user.User.password`.

References are by name and resolved lazily: renaming or deleting a secret that
a header placeholder still mentions does not fail at edit time, but the next
connection attempt raises a resolution error naming the missing secret.
"""

from enum import StrEnum

from pydantic import TypeAdapter, model_validator
from pydantic import ValidationError as PydanticValidationError
from pydantic.alias_generators import to_camel
from sqlalchemy import Column, Index, UniqueConstraint
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, JSONColumn
from models.constraints import (
    SecretEntryKey,
    SecretName,
    SecretValue,
    VaultMount,
    VaultPath,
)
from models.tenant_scoped import TenantScoped

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)

#: Maximum number of entries a single local secret may hold.
_MAX_ENTRIES = 50

#: Maximum length, in characters, of a plaintext entry value. Mirrors
#: :data:`models.constraints.SecretValue`, applied by hand on
#: :class:`SecretUpdate` because its values allow the empty keep-existing
#: sentinel and so cannot use the ``SecretValue`` alias.
_MAX_ENTRY_VALUE_LENGTH = 8192


class SecretType(StrEnum):
    """Where a secret's values live: encrypted in the local DB, or in Vault."""

    local = "local"
    vault = "vault"


def _validate_entry_key(key: str) -> None:
    """Reject an entry key that breaks the :data:`SecretEntryKey` rule.

    Args:
        key: The entry key to check.

    Raises:
        ValueError: If the key is empty, too long, or uses characters outside
            the slug charset (which would make ``${secret:NAME/KEY}``
            ambiguous).
    """
    try:
        TypeAdapter(SecretEntryKey).validate_python(key)
    except PydanticValidationError as exc:
        raise ValueError(
            f"Entry key {key!r} must be 1-256 characters of letters, digits, "
            "'.', '_' or '-'"
        ) from exc


class SecretUpdate(SQLModel):
    """Partial update payload for a Secret — all fields are optional.

    Omitting ``entries`` on a ``local`` secret keeps the stored map unchanged.
    Supplying it **replaces** the map wholesale: keys left out are deleted. Since
    clients never receive stored values, an empty-string value means "keep the
    ciphertext already stored under this key" — which is why the value type here
    is a plain ``str`` rather than
    :data:`~models.constraints.SecretValue`.

    The per-type shape rules (which fields must be present or absent) are
    enforced against the merged result by :class:`services.secret.SecretService`,
    because a PATCH body alone cannot know the effective type.
    """

    model_config = _alias_config
    name: SecretName | None = None
    type: SecretType | None = None
    entries: dict[str, str] | None = None
    vault_mount: VaultMount | None = None
    vault_path: VaultPath | None = None

    @model_validator(mode="after")
    def _validate_entries(self) -> "SecretUpdate":
        """Bound the entry count and check every key and value.

        Keys are checked here rather than through a ``dict[SecretEntryKey, ...]``
        annotation because that renders as JSON Schema ``patternProperties``,
        which the frontend's type generator degrades to ``unknown``. A plain
        ``dict[str, str]`` keeps the generated bindings usable.

        Returns:
            The validated model instance.

        Raises:
            ValueError: If the map has too many entries, or any key breaks the
                slug charset or length, or any value is too long.
        """
        if self.entries is None:
            return self
        if len(self.entries) > _MAX_ENTRIES:
            raise ValueError(f"At most {_MAX_ENTRIES} entries are allowed")
        for key, value in self.entries.items():
            _validate_entry_key(key)
            if len(value) > _MAX_ENTRY_VALUE_LENGTH:
                raise ValueError(
                    f"Entry values must be at most {_MAX_ENTRY_VALUE_LENGTH} characters"
                )
        return self


class SecretCreate(SecretUpdate):
    """Creation payload for a Secret with required fields and shape validation."""

    name: SecretName
    type: SecretType
    entries: dict[str, SecretValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_shape(self) -> "SecretCreate":
        """Enforce exactly one shape per type.

        Returns:
            The validated model instance.

        Raises:
            ValueError: If a ``local`` secret has no entries or carries Vault
                fields, or a ``vault`` secret is missing either Vault field or
                carries entries.
        """
        vault_fields = (self.vault_mount, self.vault_path)
        if self.type is SecretType.local:
            if not self.entries:
                raise ValueError("A local secret requires at least one entry")
            if any(field is not None for field in vault_fields):
                raise ValueError("A local secret must not set Vault fields")
        elif self.type is SecretType.vault:
            if any(field is None for field in vault_fields):
                raise ValueError("A vault secret requires vaultMount and vaultPath")
            if self.entries:
                raise ValueError("A vault secret must not set entries")
        return self


class Secret(SecretCreate, TenantScoped, BaseEntity, table=True):
    """Database-persisted secret.

    The ``entries`` column holds ``{key: Fernet ciphertext}`` for ``local``
    secrets and is empty for ``vault`` secrets. Its values are never exposed
    through the API: all routes respond with :class:`SecretRead`.
    """

    __tablename__ = "secrets"
    tenant_id: str = Field(foreign_key="tenants.id", ondelete="RESTRICT")
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_secrets_tenant_id_name"),
        Index("ix_secrets_tenant_id_name", "tenant_id", "name"),
    )

    entries: dict[str, str] = Field(
        default_factory=dict, sa_column=Column(JSONColumn, nullable=False)
    )


class SecretRead(BaseEntity):
    """Read view of a Secret returned by the API, excluding every value.

    ``keys`` lists the entry keys a ``local`` secret holds so the admin UI can
    show which entries exist without ever receiving their values. A ``vault``
    secret's keys live in Vault and are not enumerated here, so its ``keys`` is
    always empty.
    """

    model_config = _alias_config
    name: str
    type: SecretType
    keys: list[str] = []
    vault_mount: str | None = None
    vault_path: str | None = None
    #: Ids of the tags attached to this secret, which live in
    #: :class:`models.tag.SecretTag` rather than on the secret row.
    tag_ids: list[str] = []

    @classmethod
    def from_secret(cls, secret: Secret, *, tag_ids: list[str]) -> "SecretRead":
        """Build the read view of a stored secret, dropping every value.

        Args:
            secret: The persisted secret to project.
            tag_ids: Ids of the tags attached to ``secret``.

        Returns:
            A read view carrying the sorted entry keys but no values.
        """
        return cls(
            **secret.model_dump(exclude={"entries"}),
            keys=sorted(secret.entries),
            tag_ids=tag_ids,
        )
