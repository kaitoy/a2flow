from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class Meta(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    request_id: str
    received_at: datetime
    responded_at: datetime


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ApiResponse(BaseModel, Generic[T]):
    meta: Meta
    data: T | None = None
    error: ErrorBody | None = None
