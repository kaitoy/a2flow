"""TenantScoped mixin providing a required tenant_id foreign key."""

from sqlmodel import Field, SQLModel


class TenantScoped(SQLModel):
    """Mixin providing a required tenant_id foreign key for tenant-scoped resources.

    ``tenant_id`` references ``tenants.id`` (``ondelete=RESTRICT`` — a tenant
    with any scoped resources cannot be hard-deleted) and is indexed, since it
    is the primary filter key for every tenant-scoped list/query. Unlike
    ``User.tenant_id``, this is NOT nullable: every row that carries this
    mixin belongs to exactly one tenant.

    Place this mixin *between* an entity's ``...Create`` base and
    ``BaseEntity`` (e.g. ``class AgentSkill(AgentSkillCreate, TenantScoped,
    BaseEntity, table=True)``) so ``tenant_id`` lands right after the audit
    columns in the generated table, matching declaration order instead of
    reverse-MRO order.

    Tier-1 models that also declare a composite ``(tenant_id, <field>)``
    unique constraint/index should redeclare ``tenant_id`` without
    ``index=True`` (keeping ``foreign_key``/``ondelete`` identical) to avoid a
    redundant single-column index alongside the composite one, whose leading
    column already serves tenant_id-only lookups.
    """

    tenant_id: str = Field(foreign_key="tenants.id", ondelete="RESTRICT", index=True)
