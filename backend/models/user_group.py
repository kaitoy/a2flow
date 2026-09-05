"""UserGroup data models for create, update, database persistence, and read views.

A UserGroup is a named, tenant-scoped bundle of users that carries a set of
:class:`~models.user.Role` grants. Every member of a group holds that group's
roles in addition to whatever roles are granted to them directly, so an
administrator can run "every developer gets ``developer``" as one record
instead of editing each account.

Roles are never *stored* on the member: a user's **effective roles** are
computed as ``user.roles | (roles of every group the user belongs to)`` at the
point of use — see :class:`repositories.effective_roles.SqlEffectiveRoleRepository`
and :func:`models.user.has_any_role`. Nothing is denormalized onto ``users``,
so removing a user from a group takes effect immediately and can never leave a
stale grant behind.

Membership lives in :class:`UserGroupMember` and is surfaced on the payload and
read models as ``member_ids``; it is not a column of :class:`UserGroup`. For
that reason :class:`UserGroup` deliberately does **not** inherit
:class:`UserGroupCreate` — a ``list[str]`` field on a ``table=True`` model has
no SQLAlchemy type and would fail at class creation. This mirrors
:class:`models.workflow_task_template.WorkflowTaskTemplate`, which keeps its
scalar columns separate from ``depends_on_ids`` for the same reason.

Tags follow the same shape: they are attached through
:class:`models.tag.UserGroupTag`, written with ``PUT /user-groups/{id}/tags``
(body :class:`models.tag.TagIdsUpdate`), and read back as ``tag_ids`` on
:class:`UserGroupRead` — never as a field of the write payloads or the table
class.

**The keystone invariant:** a group can never grant ``super_admin``. Three
layers enforce it — the ``roles`` field validator on :class:`UserGroupUpdate`,
the ``ck_user_groups_no_super_admin`` check constraint, and the fact that a
``super_admin`` is platform-scoped (``tenant_id IS NULL``) and therefore fails
the same-tenant membership check in
:class:`repositories.user_group.SqlUserGroupRepository`. Because of this,
``User``'s existing ``ck_users_super_admin_exclusive`` invariant survives
untouched: no group membership can ever add ``super_admin`` to anyone.
"""

from pydantic import field_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, JSONColumn
from models.constraints import DescText, EntityName
from models.tenant_scoped import TenantScoped
from models.user import Role

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)

#: Upper bound on the members one group may hold in a single write. Mirrors
#: :data:`models.user.MAX_RESOLVE_NAME_IDS` so a full page of users always fits.
MAX_GROUP_MEMBERS = 1000


class UserGroupUpdate(SQLModel):
    """Partial update payload for a UserGroup — every field is optional.

    ``tenant_id`` is intentionally absent: a group belongs to the tenant it was
    created in and cannot be moved. When ``roles`` is ``None`` the group's
    grants are left unchanged; an explicit list replaces them wholesale.
    ``member_ids`` follows the same replace-wholesale semantics.
    """

    model_config = _alias_config
    name: EntityName | None = None
    description: DescText | None = None
    #: Roles granted to every member; ``None`` leaves them unchanged on update.
    roles: list[Role] | None = None
    #: Ids of the users belonging to this group; ``None`` leaves membership
    #: unchanged on update.
    member_ids: list[str] | None = Field(default=None, max_length=MAX_GROUP_MEMBERS)

    @field_validator("roles")
    @classmethod
    def _dedupe_roles(cls, roles: list[Role] | None) -> list[Role] | None:
        """Drop duplicate roles while preserving their first-seen order.

        Args:
            roles: The submitted roles, or ``None`` to leave them unchanged.

        Returns:
            The deduplicated roles, or ``None`` when none were submitted.
        """
        if roles is None:
            return None
        return list(dict.fromkeys(roles))

    @field_validator("roles")
    @classmethod
    def _reject_super_admin(cls, roles: list[Role] | None) -> list[Role] | None:
        """Reject ``super_admin``, which is never grantable through a group.

        Raising here (rather than through a dedicated service-layer exception)
        makes the rule part of the request schema: it surfaces as HTTP 422
        ``VALIDATION_ERROR`` and lands in ``openapi.yaml``, so the generated
        frontend Zod schema rejects it client-side too.

        Args:
            roles: The submitted roles, or ``None`` to leave them unchanged.

        Returns:
            The roles unchanged when the rule holds.

        Raises:
            ValueError: If ``super_admin`` is among the submitted roles.
        """
        if roles is not None and Role.super_admin in roles:
            raise ValueError("A user group cannot grant the super_admin role")
        return roles

    @field_validator("member_ids")
    @classmethod
    def _dedupe_member_ids(cls, member_ids: list[str] | None) -> list[str] | None:
        """Drop duplicate member ids while preserving their first-seen order.

        Args:
            member_ids: The submitted member ids, or ``None`` to leave
                membership unchanged.

        Returns:
            The deduplicated ids, or ``None`` when none were submitted.
        """
        if member_ids is None:
            return None
        return list(dict.fromkeys(member_ids))


class UserGroupCreate(UserGroupUpdate):
    """Creation payload for a UserGroup with a required name and empty defaults."""

    name: EntityName
    #: Roles granted to every member; defaults to none.
    roles: list[Role] = []
    #: Ids of the users to place in the group; defaults to an empty group.
    member_ids: list[str] = Field(default=[], max_length=MAX_GROUP_MEMBERS)


class UserGroup(TenantScoped, BaseEntity, table=True):
    """Database-persisted user group holding a set of role grants.

    This table holds only the scalar fields of a group. Membership lives in
    :class:`UserGroupMember` and is not a column here — see the module
    docstring for why :class:`UserGroupCreate` is not inherited.

    ``name`` is unique within a tenant, so ``tenant_id`` is redeclared without
    its own index and folded into a composite constraint instead.
    """

    __tablename__ = "user_groups"
    tenant_id: str = Field(foreign_key="tenants.id", ondelete="RESTRICT")
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_user_groups_tenant_id_name"),
        Index("ix_user_groups_tenant_id_name", "tenant_id", "name"),
        CheckConstraint(
            "CAST(roles AS TEXT) NOT LIKE '%\"super_admin\"%'",
            name="ck_user_groups_no_super_admin",
        ),
    )

    name: str
    description: str | None = None
    #: Roles granted to every member, stored as a JSON list of :class:`Role`
    #: values — the same representation as ``users.roles``.
    roles: list[str] = Field(
        default_factory=list, sa_column=Column(JSONColumn, nullable=False)
    )


class UserGroupMember(SQLModel, table=True):
    """Join row placing one user in one UserGroup.

    A row ``(group_id=G, user_id=U)`` means user ``U`` holds every role granted
    to group ``G``. Both sides cascade-delete: with the group because
    membership is meaningless without it, and with the user because a
    membership row is not audit data. The user side specifically must **not**
    be ``RESTRICT`` — :meth:`repositories.user.SqlUserRepository.delete` hard
    deletes and falls back to a soft delete on ``IntegrityError``, so a
    restricting membership row would make every grouped user permanently
    un-hard-deletable and leave a ghost member behind in the group UI.
    """

    __tablename__ = "user_group_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["group_id"],
            ["user_groups.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        Index("ix_user_group_members_user_id", "user_id"),
    )

    group_id: str = Field(primary_key=True)
    user_id: str = Field(primary_key=True)


class UserGroupRead(BaseEntity):
    """Read view of a UserGroup returned by the API, including its members and tags."""

    model_config = _alias_config
    name: str
    description: str | None = None
    #: Roles granted to every member of this group.
    roles: list[Role] = []
    #: Ids of the users belonging to this group.
    member_ids: list[str] = []
    #: Ids of the tags attached to this group.
    tag_ids: list[str] = []
    #: Tenant this group belongs to.
    tenant_id: str

    @classmethod
    def from_group(
        cls, group: UserGroup, *, member_ids: list[str], tag_ids: list[str]
    ) -> "UserGroupRead":
        """Build the read view of a stored group with its membership and tags attached.

        Args:
            group: The persisted group to project.
            member_ids: Ids of the users belonging to ``group``, which live in
                :class:`UserGroupMember` rather than on the group row.
            tag_ids: Ids of the tags attached to ``group``, which live in
                :class:`models.tag.UserGroupTag` rather than on the group row.

        Returns:
            A read view carrying the group's scalar fields plus its members and
            tags.
        """
        return cls(**group.model_dump(), member_ids=member_ids, tag_ids=tag_ids)


class UserGroupMembershipUpdate(SQLModel):
    """Request body for ``PUT /users/{user_id}/groups``: the user's full group set.

    Replaces the target user's membership wholesale, which is why this is a
    ``PUT`` rather than a ``PATCH``. It exists as a sub-resource of the user
    instead of a ``group_ids`` field on :class:`models.user.UserUpdate` because
    :class:`models.user.User` inherits ``UserCreate``, so any field added there
    would have to become a column of ``users`` — and membership belongs in
    :class:`UserGroupMember`, not duplicated on the user row.
    """

    model_config = _alias_config
    group_ids: list[str] = Field(default=[], max_length=MAX_GROUP_MEMBERS)

    @field_validator("group_ids")
    @classmethod
    def _dedupe_group_ids(cls, group_ids: list[str]) -> list[str]:
        """Drop duplicate group ids while preserving their first-seen order.

        Args:
            group_ids: The submitted group ids.

        Returns:
            The deduplicated ids.
        """
        return list(dict.fromkeys(group_ids))
