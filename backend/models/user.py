"""User data models for create, update, database persistence, and read views.

The ``User`` table stores a bcrypt hash in its ``password`` column. Responses
use :class:`UserRead`, which omits ``password`` entirely so the hash is never
serialized to clients.
"""

from datetime import UTC, datetime

from pydantic import EmailStr, field_serializer
from pydantic.alias_generators import to_camel
from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, TZDateTime
from models.constraints import Password, PersonName, Username

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)

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

    @field_serializer("deleted_at", when_used="json")
    def _serialize_deleted_at(self, dt: datetime | None) -> str | None:
        """Serialize ``deleted_at`` as ISO-8601 with a ``Z`` suffix, or ``None`` when unset."""
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

    @field_serializer("deleted_at", when_used="json")
    def _serialize_deleted_at(self, dt: datetime | None) -> str | None:
        """Serialize ``deleted_at`` as ISO-8601 with a ``Z`` suffix, or ``None`` when unset."""
        return _serialize_deleted_at(dt)
