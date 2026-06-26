"""User data models for create, update, database persistence, and read views.

The ``User`` table stores a bcrypt hash in its ``password`` column. Responses
use :class:`UserRead`, which omits ``password`` entirely so the hash is never
serialized to clients.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import EmailStr, field_serializer, model_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import Column, Index, UniqueConstraint
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, JSONColumn, TZDateTime
from models.constraints import Password, PersonName, Username

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)

#: Maximum number of part selections or color overrides allowed in an avatar config.
_MAX_AVATAR_ENTRIES = 50

#: Maximum length, in characters, of each avatar config key and value.
_MAX_AVATAR_VALUE_LENGTH = 128


class AvatarConfig(SQLModel):
    """Customization for a user's generated (Humation) avatar.

    Holds the part ``selections`` (selection-slot id -> part id), ``colors``
    (color-slot id -> hex value), and an optional ``background`` the frontend
    feeds to the Humation avatar renderer. The inner mapping keys are Humation
    slot identifiers defined by the frontend asset package, so they are not
    validated against a manifest here; only their sizes are bounded.
    """

    model_config = _alias_config
    selections: dict[str, str] = Field(default_factory=dict)
    colors: dict[str, str] = Field(default_factory=dict)
    background: str | None = None

    @model_validator(mode="after")
    def _validate_sizes(self) -> "AvatarConfig":
        """Bound the number of entries and the length of each key and value.

        Returns:
            The validated model instance.

        Raises:
            ValueError: If a mapping has more than ``_MAX_AVATAR_ENTRIES`` entries,
                or any key, value, or the background exceeds
                ``_MAX_AVATAR_VALUE_LENGTH`` characters.
        """
        for mapping in (self.selections, self.colors):
            if len(mapping) > _MAX_AVATAR_ENTRIES:
                raise ValueError(
                    f"At most {_MAX_AVATAR_ENTRIES} avatar entries are allowed"
                )
            for key, value in mapping.items():
                if (
                    len(key) > _MAX_AVATAR_VALUE_LENGTH
                    or len(value) > _MAX_AVATAR_VALUE_LENGTH
                ):
                    raise ValueError(
                        "Avatar config keys and values must be at most "
                        f"{_MAX_AVATAR_VALUE_LENGTH} characters"
                    )
        if (
            self.background is not None
            and len(self.background) > _MAX_AVATAR_VALUE_LENGTH
        ):
            raise ValueError(
                f"Avatar background must be at most {_MAX_AVATAR_VALUE_LENGTH} characters"
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
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


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
    #: Customization for the generated avatar; ``None`` leaves it unchanged on
    #: update, and an explicit ``null`` from the client clears it.
    avatar_config: AvatarConfig | None = None


class UserCreate(UserUpdate):
    """Creation payload for a User with required fields and boolean defaults."""

    username: Username
    first_name: PersonName
    last_name: PersonName
    password: Password
    email: EmailStr
    enabled: bool = True
    email_verified: bool = False


class User(UserCreate, BaseEntity, table=True):
    """Database-persisted application user. The ``password`` column holds a bcrypt hash.

    ``deleted_at`` marks a soft-deleted user: one that is still referenced by other
    records (via ``created_by`` / ``updated_by``) and therefore cannot be removed
    from the database. Soft-deleted users are hidden from the list endpoint but
    remain fetchable so their names can still be resolved.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        Index("ix_users_username", "username"),
    )

    deleted_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    #: Set when the user has a custom uploaded avatar (see :class:`~models.user_avatar.UserAvatar`)
    #: and cleared when it is removed. Acts as a presence marker plus cache-busting
    #: timestamp so read views report a custom avatar without loading its blob.
    avatar_updated_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    #: Generated-avatar customization, stored as a JSON blob. Overrides the
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
    deleted_at: datetime | None = None
    #: ISO-8601 timestamp of the last custom-avatar change, or ``None`` when the
    #: user has no uploaded avatar (the client then renders a generated default).
    avatar_updated_at: datetime | None = None
    #: Generated-avatar customization, or ``None`` when the user has not
    #: customized it (the client then renders a username-seeded default).
    avatar_config: AvatarConfig | None = None

    @field_serializer("deleted_at", "avatar_updated_at", when_used="json")
    def _serialize_deleted_at(self, dt: datetime | None) -> str | None:
        """Serialize the timestamp as ISO-8601 with a ``Z`` suffix, or ``None`` when unset."""
        return _serialize_deleted_at(dt)
