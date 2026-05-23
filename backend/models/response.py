"""API response envelope models used by the response middleware and Pydantic serialization."""

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class Meta(BaseModel):
    """Request metadata included in every API response envelope."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    request_id: str
    received_at: datetime
    responded_at: datetime


class ErrorBody(BaseModel):
    """Structured error payload returned in the ``error`` field of an API response."""

    code: str
    message: str
    details: dict[str, Any] | None = None


class ApiResponse(BaseModel, Generic[T]):
    """Generic API response envelope wrapping typed data or an error body."""

    meta: Meta
    data: T | None = None
    error: ErrorBody | None = None
