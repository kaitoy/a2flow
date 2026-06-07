"""FastAPI exception handlers that map domain exceptions to envelope error responses.

Each handler builds an :class:`ApiResponse` with ``data=None`` and ``error``
populated, mirroring the wire format produced by router success responses.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from models.response import ApiError, ApiMeta, ApiResponse
from repositories.exceptions import (
    CsrfError,
    DependencyCycleError,
    ForeignKeyViolationError,
    NotFoundError,
    QueryValidationError,
    ReferencedError,
    UnauthorizedError,
    UniqueViolationError,
)

logger = logging.getLogger(__name__)


def _envelope_error(
    request: Request,
    *,
    code: str,
    message: str,
    status_code: int,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Wrap an error in an :class:`ApiResponse` envelope and return a ``JSONResponse``."""
    meta = ApiMeta(
        request_id=request.state.request_id,
        received_at=request.state.received_at,
        responded_at=datetime.now(UTC),
    )
    env = ApiResponse[None](
        meta=meta,
        data=None,
        error=ApiError(code=code, message=message, details=details),
    )
    return JSONResponse(
        env.model_dump(by_alias=True, mode="json"),
        status_code=status_code,
    )


async def validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return HTTP 422 with VALIDATION_ERROR code for request validation failures."""
    assert isinstance(exc, RequestValidationError)
    return _envelope_error(
        request,
        code="VALIDATION_ERROR",
        message="Invalid request",
        status_code=422,
        details={"errors": exc.errors()},
    )


async def not_found_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return HTTP 404 with NOT_FOUND code when a requested entity does not exist."""
    assert isinstance(exc, NotFoundError)
    return _envelope_error(
        request,
        code="NOT_FOUND",
        message=str(exc),
        status_code=404,
        details={"entity": exc.entity, "id": exc.id},
    )


async def foreign_key_violation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return HTTP 422 with FOREIGN_KEY_VIOLATION code when a referenced entity is missing."""
    assert isinstance(exc, ForeignKeyViolationError)
    return _envelope_error(
        request,
        code="FOREIGN_KEY_VIOLATION",
        message=str(exc),
        status_code=422,
        details={"entity": exc.entity, "id": exc.id},
    )


async def query_validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return HTTP 400 with INVALID_QUERY code for malformed sort/filter parameters."""
    assert isinstance(exc, QueryValidationError)
    return _envelope_error(
        request,
        code="INVALID_QUERY",
        message=str(exc),
        status_code=400,
        details={"reason": exc.reason},
    )


async def dependency_cycle_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return HTTP 409 with DEPENDENCY_CYCLE code when edges would form a cycle."""
    assert isinstance(exc, DependencyCycleError)
    return _envelope_error(
        request,
        code="DEPENDENCY_CYCLE",
        message=str(exc),
        status_code=409,
        details={"taskId": exc.task_id, "dependsOnId": exc.depends_on_id},
    )


async def referenced_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return HTTP 409 with CONFLICT_REFERENCED code when an entity is still referenced by others."""
    assert isinstance(exc, ReferencedError)
    return _envelope_error(
        request,
        code="CONFLICT_REFERENCED",
        message=str(exc),
        status_code=409,
    )


async def unique_violation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return HTTP 409 with CONFLICT_UNIQUE code when a unique constraint is violated."""
    assert isinstance(exc, UniqueViolationError)
    return _envelope_error(
        request,
        code="CONFLICT_UNIQUE",
        message=str(exc),
        status_code=409,
        details={"field": exc.field, "value": exc.value},
    )


async def unauthorized_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return HTTP 401 with UNAUTHENTICATED code when no valid session is present."""
    assert isinstance(exc, UnauthorizedError)
    return _envelope_error(
        request,
        code="UNAUTHENTICATED",
        message=str(exc),
        status_code=401,
    )


async def csrf_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return HTTP 403 with CSRF_FAILED code when CSRF validation fails."""
    assert isinstance(exc, CsrfError)
    return _envelope_error(
        request,
        code="CSRF_FAILED",
        message=str(exc),
        status_code=403,
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return the original HTTP status code with an HTTP_{code} error code."""
    assert isinstance(exc, HTTPException)
    return _envelope_error(
        request,
        code=f"HTTP_{exc.status_code}",
        message=str(exc.detail),
        status_code=exc.status_code,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return HTTP 500 with INTERNAL_ERROR code and log the full exception traceback."""
    logger.exception("Unhandled exception", exc_info=exc)
    return _envelope_error(
        request,
        code="INTERNAL_ERROR",
        message="Internal server error",
        status_code=500,
    )
