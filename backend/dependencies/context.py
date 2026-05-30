"""Request-scoped FastAPI dependencies and the application name constant.

Holds the lightweight, per-request dependencies that do not touch persistence or
singletons: the response metadata block, pagination query parameters, and the
current user id derived from request headers.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, Query, Request

from models.response import ApiMeta

APP_NAME = "A2Flow"


def build_api_meta(request: Request) -> ApiMeta:
    """Construct the ``ApiMeta`` block for the current request.

    Reads ``request_id`` and ``received_at`` from ``request.state`` (populated
    by ``RequestContextMiddleware``) and stamps ``responded_at`` with the
    current UTC time at the moment the dependency is resolved.
    """
    return ApiMeta(
        request_id=request.state.request_id,
        received_at=request.state.received_at,
        responded_at=datetime.now(UTC),
    )


ApiMetaDep = Annotated[ApiMeta, Depends(build_api_meta)]


@dataclass
class PaginationParams:
    """Query parameters for paginated list endpoints."""

    limit: int = Query(default=20, ge=1, le=1000)
    offset: int = Query(default=0, ge=0)


PaginationDep = Annotated[PaginationParams, Depends(PaginationParams)]


def get_current_user_id(
    x_user_id: Annotated[str | None, Header()] = None,
) -> str:
    """Return the user ID from the ``X-User-Id`` header, or an empty string if absent."""
    return x_user_id or ""


CurrentUserIdDep = Annotated[str, Depends(get_current_user_id)]
