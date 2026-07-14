"""API response envelope models used by routers and exception handlers.

Routers declare ``response_model=ApiResponse[T]`` and return an
``ApiResponse`` instance; exception handlers return an ``ApiResponse[None]``
with ``error`` populated. ``RequestContextMiddleware`` sets
``request.state.request_id`` / ``received_at`` so a small dependency can
construct an :class:`ApiMeta` for each response.
"""

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, field_serializer
from pydantic.alias_generators import to_camel

from models.base import iso_z

T = TypeVar("T")


class ApiMeta(BaseModel):
    """Request metadata included in every API response envelope."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    request_id: str
    received_at: datetime
    responded_at: datetime

    @field_serializer("received_at", "responded_at")
    def _serialize_iso_z(self, value: datetime) -> str:
        """Serialize datetimes as ISO-8601 with milliseconds and a ``Z`` suffix."""
        return iso_z(value)


class ApiError(BaseModel):
    """Structured error payload returned in the ``error`` field of an API response."""

    code: str
    message: str
    details: dict[str, Any] | None = None


class ApiResponse(BaseModel, Generic[T]):
    """Generic API response envelope wrapping typed data or an error body."""

    meta: ApiMeta
    data: T | None = None
    error: ApiError | None = None
