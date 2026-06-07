"""User data models for create, update, database persistence, and read views.

The ``User`` table stores a bcrypt hash in its ``password`` column. Responses
use :class:`UserRead`, which omits ``password`` entirely so the hash is never
serialized to clients.
"""

from datetime import UTC, datetime

from pydantic import field_serializer, field_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)

_PASSWORD_MIN_LENGTH = 12

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
    """Partial update payload for a User — all fields are optional."""

    model_config = _alias_config
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    password: str | None = None
    email: str | None = None
    enabled: bool | None = None
    email_verified: bool | None = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str | None) -> str | None:
        """Enforce the minimum password length when a password is supplied.

        Args:
            v: The plaintext password value, or ``None`` when omitted.

        Returns:
            The original value if valid.

        Raises:
            ValueError: If the password is shorter than :data:`_PASSWORD_MIN_LENGTH`.
        """
        if v is not None and len(v) < _PASSWORD_MIN_LENGTH:
            raise ValueError(
                f"Password must be at least {_PASSWORD_MIN_LENGTH} characters"
            )
        return v


class UserCreate(UserUpdate):
    """Creation payload for a User with required fields and boolean defaults."""

    username: str
    first_name: str
    last_name: str
    password: str
    email: str
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

    deleted_at: datetime | None = Field(default=None)

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
