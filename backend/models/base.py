from datetime import UTC, datetime

import uuid_utils
from sqlmodel import Field, SQLModel


class AuditedBase(SQLModel):
    id: str = Field(
        default_factory=lambda: str(uuid_utils.uuid7()),
        primary_key=True,
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC)},
    )
    created_by: str = Field(default="")
    updated_by: str = Field(default="")
