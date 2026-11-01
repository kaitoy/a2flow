"""Tenant data models for create, update, and database persistence.

A Tenant is the top-level organizational boundary for multi-tenancy: every
tenant-scoped user (``User.tenant_id``) belongs to exactly one Tenant, and a
user's ``roles`` (see :class:`models.user.Role`) apply within that tenant
only — except ``super_admin``, which is platform-wide and ignores tenancy.

A tenant may also carry the connection to **its own** HashiCorp Vault, which its
``vault``-type secrets are read from (see :mod:`infrastructure.vault_client`).
The tenant's own ``admin`` sets it through :class:`TenantSettingsUpdate`.
``vault_addr`` is :data:`models.constraints.HttpUrl`, so a tenant user cannot
point A2Flow at a private address.

A tenant without its own Vault reads from the **global Vault** whose address is
in :class:`models.system_settings.SystemSettings`, logging in with a credential
of its own (:class:`TenantGlobalVaultFields`) that a ``super_admin`` registers.
What that credential may read is decided by the policies attached to it in
Vault, which is what keeps tenants apart there.

Both credentials -- the static token, or the AppRole secret id -- follow the
write-only pattern of :class:`models.system_settings.SystemSettings`: they are
stored as Fernet ciphertext (encrypted in :class:`services.tenant.TenantService`)
and never serialized; the read views replace them with ``*_credential_set``
flags.
"""

from enum import StrEnum
from typing import Annotated

from pydantic.alias_generators import to_camel
from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity
from models.constraints import (
    EntityName,
    HttpUrl,
    ShortText,
    TenantSlug,
    VaultMount,
)

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


#: AppRole login mount used when a tenant names none.
DEFAULT_VAULT_APPROLE_MOUNT = "approle"

#: Failed sign-ins an account may have before it is locked, unless its tenant
#: sets otherwise. Also the limit for platform-scoped accounts, which have no
#: tenant.
DEFAULT_LOGIN_MAX_FAILURES = 5
#: How long, in minutes, failures are counted and an account stays locked,
#: unless its tenant sets otherwise.
DEFAULT_LOGIN_LOCKOUT_MINUTES = 15
#: Upper bound of :attr:`TenantUpdate.login_lockout_minutes` (one day). Failure
#: rows older than this can never count again, so they are pruned.
MAX_LOGIN_LOCKOUT_MINUTES = 1440

#: A tenant's failed sign-in limit.
LoginMaxFailures = Annotated[int, Field(ge=1, le=100)]
#: A tenant's lockout duration in minutes.
LoginLockoutMinutes = Annotated[int, Field(ge=1, le=MAX_LOGIN_LOCKOUT_MINUTES)]


class VaultAuthMethod(StrEnum):
    """How A2Flow authenticates to a tenant's Vault."""

    #: A static token, sent as ``X-Vault-Token`` as is.
    token = "token"
    #: An AppRole login (role id + secret id) that mints short-lived tokens.
    approle = "approle"


class TenantVaultFields(SQLModel):
    """The tenant's own Vault connection, as its ``admin`` submits it.

    ``vault_credential`` is write-only and, like
    :attr:`models.system_settings.SystemSettingsUpdate.smtp_password`, an
    **empty string** means "keep the stored one" while an explicit ``null``
    clears it. The cross-field rules (an address needs an auth method and a
    credential, AppRole needs a role id) are checked against the merged result
    by :func:`services.vault_settings.prepare_vault_fields`.
    """

    model_config = _alias_config
    vault_addr: HttpUrl | None = None
    vault_auth_method: VaultAuthMethod | None = None
    vault_role_id: ShortText | None = None
    vault_approle_mount: VaultMount | None = None
    vault_credential: str | None = Field(default=None, max_length=4096)


class TenantGlobalVaultFields(SQLModel):
    """The tenant's credential for the global Vault, as a ``super_admin`` submits it.

    The address is the global one, so there is none here. ``global_vault_credential``
    has the same write-only semantics as ``vault_credential``, and the same
    cross-field rules apply (:func:`services.vault_settings.prepare_vault_fields`).
    """

    model_config = _alias_config
    global_vault_auth_method: VaultAuthMethod | None = None
    global_vault_role_id: ShortText | None = None
    global_vault_approle_mount: VaultMount | None = None
    global_vault_credential: str | None = Field(default=None, max_length=4096)


class TenantUpdate(TenantGlobalVaultFields):
    """Partial update payload for a Tenant — all fields are optional.

    ``name`` is intentionally absent: a tenant's name (slug) is immutable
    after creation, so it cannot be changed through the update endpoint. The
    tenant's own Vault connection is absent too: it is a tenant setting,
    changed through :class:`TenantSettingsUpdate`. The credential for the
    global Vault is here, since only a ``super_admin`` registers it.
    """

    display_name: EntityName | None = None
    enabled: bool | None = None
    #: Failed sign-ins within :attr:`login_lockout_minutes` that lock an
    #: account of this tenant.
    login_max_failures: LoginMaxFailures | None = None
    #: Minutes over which failures are counted and for which a locked account
    #: stays locked, measured from the oldest failure still counted.
    login_lockout_minutes: LoginLockoutMinutes | None = None


class TenantCreate(TenantUpdate):
    """Creation payload for a Tenant with required fields."""

    display_name: EntityName
    name: TenantSlug
    #: New tenants are active by default.
    enabled: bool = True
    login_max_failures: LoginMaxFailures = DEFAULT_LOGIN_MAX_FAILURES
    login_lockout_minutes: LoginLockoutMinutes = DEFAULT_LOGIN_LOCKOUT_MINUTES


class Tenant(TenantCreate, TenantVaultFields, BaseEntity, table=True):
    """Database-persisted tenant: the top-level organizational boundary.

    ``display_name`` is a unique, human-readable label; ``name`` is a
    unique, URL-safe kebab-case identifier intended for use in paths or
    subdomains by later tasks. ``enabled`` supports deactivating a tenant
    without deleting it — and, transitively, without deleting or orphaning
    its users (see ``User.tenant_id``'s ``ON DELETE RESTRICT`` foreign key
    in :mod:`models.user`).
    """

    __tablename__ = "tenants"
    __table_args__ = (
        UniqueConstraint("display_name", name="uq_tenants_display_name"),
        Index("ix_tenants_display_name", "display_name"),
        UniqueConstraint("name", name="uq_tenants_name"),
        Index("ix_tenants_name", "name"),
    )

    #: Fernet ciphertext, never exposed through the API (every route responds
    #: with :class:`TenantRead`). Longer than the plaintext the update payload
    #: caps, so it is redeclared without that cap.
    vault_credential: str | None = None
    #: Fernet ciphertext, like :attr:`vault_credential`.
    global_vault_credential: str | None = None


class TenantSettingsUpdate(TenantVaultFields):
    """Partial update of the settings a tenant's own ``admin`` may change.

    Exposed on ``PATCH /tenant-settings``, which acts on the caller's tenant
    rather than on a tenant id: sign-in throttling and the tenant's own Vault.
    """

    login_max_failures: LoginMaxFailures | None = None
    login_lockout_minutes: LoginLockoutMinutes | None = None


class TenantSettings(SQLModel):
    """Read view of the settings a tenant's own ``admin`` may change.

    ``vault_credential_set`` reports only whether a Vault credential is stored,
    so the form can show it as configured without ever receiving it.
    """

    model_config = _alias_config
    login_max_failures: int
    login_lockout_minutes: int
    vault_addr: str | None = None
    vault_auth_method: VaultAuthMethod | None = None
    vault_role_id: str | None = None
    vault_approle_mount: str | None = None
    #: Whether a Vault credential is stored. The credential is never serialized.
    vault_credential_set: bool = False

    @classmethod
    def from_tenant(cls, tenant: Tenant) -> "TenantSettings":
        """Project a tenant into its admin-managed settings.

        Args:
            tenant: The persisted tenant row.

        Returns:
            The settings, with ``vault_credential_set`` in place of the
            credential.
        """
        return cls(
            login_max_failures=tenant.login_max_failures,
            login_lockout_minutes=tenant.login_lockout_minutes,
            vault_addr=tenant.vault_addr,
            vault_auth_method=tenant.vault_auth_method,
            vault_role_id=tenant.vault_role_id,
            vault_approle_mount=tenant.vault_approle_mount,
            vault_credential_set=bool(tenant.vault_credential),
        )


class TenantRead(BaseEntity):
    """Read view of a Tenant, excluding its own Vault connection.

    The tenant's own Vault connection is a tenant setting (see
    :class:`TenantSettings`), so it is left out here. Its credential for the
    global Vault is reported only as ``global_vault_credential_set``.
    """

    model_config = _alias_config
    display_name: str
    name: str
    enabled: bool
    login_max_failures: int = DEFAULT_LOGIN_MAX_FAILURES
    login_lockout_minutes: int = DEFAULT_LOGIN_LOCKOUT_MINUTES
    global_vault_auth_method: VaultAuthMethod | None = None
    global_vault_role_id: str | None = None
    global_vault_approle_mount: str | None = None
    #: Whether a global Vault credential is stored. It is never serialized.
    global_vault_credential_set: bool = False

    @classmethod
    def from_tenant(cls, tenant: Tenant) -> "TenantRead":
        """Build the read view of a tenant, dropping its Vault credentials.

        Args:
            tenant: The persisted tenant row.

        Returns:
            A read view carrying every field except the ``vault_*`` ones and
            ``global_vault_credential``, plus the
            ``global_vault_credential_set`` flag derived from it.
        """
        exclude = set(TenantVaultFields.model_fields) | {"global_vault_credential"}
        return cls(
            **tenant.model_dump(exclude=exclude),
            global_vault_credential_set=bool(tenant.global_vault_credential),
        )
