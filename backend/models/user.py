"""User data models for create, update, database persistence, and read views.

The ``User`` table stores a bcrypt hash in its ``password`` column. Responses
use :class:`UserRead`, which omits ``password`` entirely so the hash is never
serialized to clients.
"""

import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import EmailStr, field_serializer, field_validator, model_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    text,
)
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, JSONColumn, TZDateTime, iso_z_or_none
from models.constraints import Password, PersonName, Username

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class Role(StrEnum):
    """Application roles grantable to a user.

    Roles are independent grants (no inheritance): a user holds any subset of
    them, and each role unlocks a specific group of operations. The single
    exception is :attr:`super_admin`, which bypasses every authorization
    check and, for that reason, is mutually exclusive with every other role —
    see :func:`services.user._reject_super_admin_role_combination`.
    """

    #: All operations; bypasses every role and ownership check.
    super_admin = "super_admin"
    #: User CRUD and secrets CRUD.
    admin = "admin"
    #: MCP server CRUD, workflow CRUD, and agent-skill CRUD. Also grants
    #: workflow execution (``POST /workflows/{id}/execute``), including on
    #: ``draft`` workflows for pre-publish testing — see
    #: :meth:`services.workflow.WorkflowService.execute`.
    developer = "developer"
    #: Workflow execution (``POST /workflows/{id}/execute``), restricted to
    #: ``published`` workflows.
    requester = "requester"
    #: Eligibility as a designated approver of workflow approvals.
    approver = "approver"


def has_role(user: "User | UserRead", *allowed: Role) -> bool:
    """Return whether ``user`` holds any of the ``allowed`` roles.

    ``super_admin`` always passes, regardless of ``allowed`` — it bypasses
    every authorization check. This helper is the single source of truth for
    role checks, shared by the ``require_roles`` router dependency and the
    service-layer ownership checks.

    Args:
        user: The user whose roles to inspect.
        allowed: Roles that grant access. May be empty, in which case only a
            ``super_admin`` passes.

    Returns:
        ``True`` if the user holds ``super_admin`` or any role in ``allowed``.
    """
    roles = set(user.roles or [])
    if Role.super_admin in roles:
        return True
    return bool(roles & set(allowed))


#: Maximum number of palette colors allowed in an avatar config.
_MAX_AVATAR_COLORS = 8

#: Pattern every avatar palette entry must match: a six-digit ``#rrggbb`` hex color.
_AVATAR_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class AvatarConfig(SQLModel):
    """Customization for a user's generated (boring-avatars ``beam``) avatar.

    Holds the ordered ``colors`` palette the frontend feeds to the avatar
    renderer. The renderer picks entries from the palette by hashing the
    username seed, so the order is meaningful; an empty list means "use the
    application default palette".
    """

    model_config = _alias_config
    colors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_colors(self) -> "AvatarConfig":
        """Bound the palette length and require every entry to be a hex color.

        The renderer derives contrasting foreground colors by parsing each
        palette entry as hex, so a non-hex value renders wrong rather than
        failing loudly — hence the format check here.

        Returns:
            The validated model instance.

        Raises:
            ValueError: If the palette holds more than ``_MAX_AVATAR_COLORS``
                entries, or any entry is not a ``#rrggbb`` hex color.
        """
        if len(self.colors) > _MAX_AVATAR_COLORS:
            raise ValueError(f"At most {_MAX_AVATAR_COLORS} avatar colors are allowed")
        for color in self.colors:
            if not _AVATAR_COLOR_RE.match(color):
                raise ValueError(
                    "Avatar colors must be six-digit hex values like '#16BFA9'"
                )
        return self


#: Identifier of the seeded system user that owns the bootstrap records. It is the
#: ``created_by`` / ``updated_by`` of the very first records and is hidden from the
#: user list. The first real user is created with ``X-User-Id`` set to this value.
SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"


def _serialize_deleted_at(dt: datetime | None) -> str | None:
    """Serialize ``deleted_at`` as ISO-8601 with a ``Z`` suffix, or ``None`` when unset.

    Args:
        dt: The soft-delete timestamp, or ``None`` for an active record.

    Returns:
        The ISO-8601 string with a ``Z`` suffix, or ``None``.
    """
    return iso_z_or_none(dt)


class UserUpdate(SQLModel):
    """Partial update payload for a User — all fields are optional.

    ``username`` is intentionally absent: a user's username is immutable after
    creation, so it cannot be changed through the update endpoint.
    """

    model_config = _alias_config
    first_name: PersonName | None = None
    last_name: PersonName | None = None
    password: Password | None = None
    email: EmailStr | None = None
    enabled: bool | None = None
    email_verified: bool | None = None
    #: Roles to assign; ``None`` leaves the target's roles unchanged on update.
    roles: list[Role] | None = None
    #: Color palette for the generated avatar; ``None`` leaves it unchanged on
    #: update, and an explicit ``null`` from the client clears it.
    avatar_config: AvatarConfig | None = None
    #: Tenant this user belongs to. ``None`` is only valid for a ``super_admin``
    #: (platform-scoped by definition) or the seeded system user — every other
    #: user must carry a ``tenant_id``. Once non-null, it can never be changed;
    #: see :func:`services.user._require_tenant_for_non_super_admin` and the
    #: matching guard against reassignment in :meth:`services.user.UserService.update`.
    tenant_id: str | None = None

    @field_validator("roles")
    @classmethod
    def _dedupe_roles(cls, roles: list[Role] | None) -> list[Role] | None:
        """Drop duplicate roles while preserving their first-seen order."""
        if roles is None:
            return None
        return list(dict.fromkeys(roles))


class UserCreate(UserUpdate):
    """Creation payload for a User with required fields and boolean defaults."""

    username: Username
    first_name: PersonName
    last_name: PersonName
    password: Password
    email: EmailStr
    enabled: bool = True
    email_verified: bool = False
    #: Roles granted to the new user; defaults to no roles (chat-only account).
    roles: list[Role] = Field(default_factory=list)


class User(UserCreate, BaseEntity, table=True):
    """Database-persisted application user. The ``password`` column holds a bcrypt hash.

    ``deleted_at`` marks a soft-deleted user: one that is still referenced by other
    records (via ``created_by`` / ``updated_by``) and therefore cannot be removed
    from the database. Soft-deleted users are hidden from the list endpoint but
    remain fetchable so their names can still be resolved. Two check constraints
    enforce the tenant/role invariant from both directions: a ``super_admin``
    may never carry a non-null ``tenant_id`` (platform-scoped by definition),
    and every other user (except the seeded system user) must carry one; see
    :func:`services.user._reject_super_admin_tenant_conflict` and
    :func:`services.user._require_tenant_for_non_super_admin` for the matching
    application-layer guards. Once assigned, a ``tenant_id`` can never change —
    see :meth:`services.user.UserService.update`.

    ``username`` uniqueness is two-tiered, since ``tenant_id`` can be null:
    ``uq_users_tenant_id_username`` enforces uniqueness within a tenant for
    tenant-scoped users, and ``ix_users_username_platform_scoped`` is a
    partial unique index (``tenant_id IS NULL``) enforcing uniqueness among
    platform-scoped users (``super_admin`` and the seeded system user) — a
    plain composite constraint alone would not catch that case, since SQL
    treats every ``NULL`` as distinct from every other ``NULL``.

    A third check constraint, ``ck_users_super_admin_exclusive``, enforces
    that a ``super_admin`` never holds any other role — see
    :func:`services.user._reject_super_admin_role_combination` for the
    matching application-layer guard.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "username", name="uq_users_tenant_id_username"),
        Index("ix_users_tenant_id_username", "tenant_id", "username"),
        Index(
            "ix_users_username_platform_scoped",
            "username",
            unique=True,
            postgresql_where=text("tenant_id IS NULL"),
            sqlite_where=text("tenant_id IS NULL"),
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="RESTRICT",
            name="fk_users_tenant_id",
        ),
        CheckConstraint(
            "tenant_id IS NULL OR CAST(roles AS TEXT) NOT LIKE '%\"super_admin\"%'",
            name="ck_users_super_admin_no_tenant",
        ),
        CheckConstraint(
            "tenant_id IS NOT NULL OR CAST(roles AS TEXT) LIKE '%\"super_admin\"%' "
            f"OR id = '{SYSTEM_USER_ID}'",
            name="ck_users_non_super_admin_requires_tenant",
        ),
        CheckConstraint(
            "CAST(roles AS TEXT) NOT LIKE '%\"super_admin\"%' "
            "OR CAST(roles AS TEXT) = '[\"super_admin\"]'",
            name="ck_users_super_admin_exclusive",
        ),
    )

    deleted_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    #: Set when the user has a custom uploaded avatar (see :class:`~models.user_avatar.UserAvatar`)
    #: and cleared when it is removed. Acts as a presence marker plus cache-busting
    #: timestamp so read views report a custom avatar without loading its blob.
    avatar_updated_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    #: Roles granted to the user, stored as a JSON list of :class:`Role` values.
    #: Overrides the typed ``list[Role]`` inherited from :class:`UserCreate` so
    #: it persists as a plain JSON column.
    roles: list[str] = Field(  # type: ignore[assignment]
        default_factory=list, sa_column=Column(JSONColumn, nullable=False)
    )
    #: Generated-avatar color palette, stored as a JSON blob. Overrides the
    #: typed :class:`AvatarConfig` inherited from :class:`UserUpdate` so it
    #: persists as a plain dict column.
    avatar_config: dict[str, Any] | None = Field(  # type: ignore[assignment]
        default=None, sa_column=Column(JSONColumn, nullable=True)
    )

    @field_serializer("deleted_at", "avatar_updated_at", when_used="json")
    def _serialize_deleted_at(self, dt: datetime | None) -> str | None:
        """Serialize the timestamp as ISO-8601 with a ``Z`` suffix, or ``None`` when unset."""
        return _serialize_deleted_at(dt)


class UserRead(BaseEntity):
    """Read view of a User returned by the API, excluding the password hash."""

    model_config = _alias_config
    username: str
    first_name: str
    last_name: str
    email: str
    enabled: bool
    email_verified: bool
    #: Roles granted to the user; empty for a chat-only account.
    roles: list[Role] = []
    deleted_at: datetime | None = None
    #: ISO-8601 timestamp of the last custom-avatar change, or ``None`` when the
    #: user has no uploaded avatar (the client then renders a generated default).
    avatar_updated_at: datetime | None = None
    #: Generated-avatar color palette, or ``None`` when the user has not
    #: customized it (the client then renders its default palette).
    avatar_config: AvatarConfig | None = None
    #: Tenant this user belongs to; ``None`` for a platform-scoped user.
    tenant_id: str | None = None

    @field_serializer("deleted_at", "avatar_updated_at", when_used="json")
    def _serialize_deleted_at(self, dt: datetime | None) -> str | None:
        """Serialize the timestamp as ISO-8601 with a ``Z`` suffix, or ``None`` when unset."""
        return _serialize_deleted_at(dt)
