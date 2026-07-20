"""Tenant data models for create, update, and database persistence.

A Tenant is the top-level organizational boundary for multi-tenancy: every
tenant-scoped user (``User.tenant_id``) belongs to exactly one Tenant, and a
user's ``roles`` (see :class:`models.user.Role`) apply within that tenant
only — except ``super_admin``, which is platform-wide and ignores tenancy.
"""

from pydantic.alias_generators import to_camel
from sqlalchemy import Index, UniqueConstraint
from sqlmodel import SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity
from models.constraints import EntityName, TenantSlug

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class TenantUpdate(SQLModel):
    """Partial update payload for a Tenant — all fields are optional."""

    model_config = _alias_config
    display_name: EntityName | None = None
    name: TenantSlug | None = None
    enabled: bool | None = None


class TenantCreate(TenantUpdate):
    """Creation payload for a Tenant with required fields."""

    display_name: EntityName
    name: TenantSlug
    #: New tenants are active by default.
    enabled: bool = True


class Tenant(TenantCreate, BaseEntity, table=True):
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
