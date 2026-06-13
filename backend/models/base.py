"""Base SQLModel entity with audit fields and camelCase JSON serialization."""

from datetime import UTC, datetime
from typing import Any, cast

import uuid_utils
from pydantic import field_serializer
from pydantic.alias_generators import to_camel
from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

TZDateTime = cast("type[Any]", DateTime(timezone=True))
"""Timezone-aware ``DateTime`` column type for ``Field(sa_type=...)``.

Maps to ``timestamptz`` on PostgreSQL (asyncpg rejects tz-aware values on
naive columns) and is a storage no-op on SQLite. Cast because SQLModel's
``sa_type`` stub only admits type objects while instances are supported at
runtime.
"""


class BaseEntity(SQLModel):
    """Abstract SQLModel base providing a UUID7 primary key, audit timestamps, and camelCase aliases.

    ``created_by`` / ``updated_by`` are required foreign keys to ``users.id``
    (``ondelete=RESTRICT``); every persistent entity therefore records the user
    who created and last updated it, and a referenced user cannot be hard-deleted.

    Audit timestamps use timezone-aware columns (``timestamptz`` on
    PostgreSQL); asyncpg rejects tz-aware values on naive columns. SQLite's
    storage format is unaffected by the flag.
    """

    model_config = SQLModelConfig(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: str = Field(
        default_factory=lambda: str(uuid_utils.uuid7()),
        primary_key=True,
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TZDateTime,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TZDateTime,
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )
    created_by: str = Field(foreign_key="users.id", ondelete="RESTRICT")
    updated_by: str = Field(foreign_key="users.id", ondelete="RESTRICT")

    @field_serializer("created_at", "updated_at", when_used="json")
    def _serialize_audit_datetime(self, dt: datetime) -> str:
        """Serialize audit datetimes as ISO-8601 with a Z suffix, normalizing naive values to UTC."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
