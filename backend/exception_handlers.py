"""FastAPI exception handlers that map domain exceptions to structured JSON error responses."""

import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from repositories.exceptions import (
    ForeignKeyViolationError,
    NotFoundError,
    ReferencedError,
)

logger = logging.getLogger(__name__)


async def validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return HTTP 422 with VALIDATION_ERROR code for request validation failures."""
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(
        {
            "code": "VALIDATION_ERROR",
            "message": "Invalid request",
            "details": {"errors": exc.errors()},
        },
        status_code=422,
    )


async def not_found_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return HTTP 404 with NOT_FOUND code when a requested entity does not exist."""
    assert isinstance(exc, NotFoundError)
    return JSONResponse(
        {
            "code": "NOT_FOUND",
            "message": str(exc),
            "details": {"entity": exc.entity, "id": exc.id},
        },
        status_code=404,
    )


async def foreign_key_violation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return HTTP 422 with FOREIGN_KEY_VIOLATION code when a referenced entity is missing."""
    assert isinstance(exc, ForeignKeyViolationError)
    return JSONResponse(
        {
            "code": "FOREIGN_KEY_VIOLATION",
            "message": str(exc),
            "details": {"entity": exc.entity, "id": exc.id},
        },
        status_code=422,
    )


async def referenced_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return HTTP 409 with CONFLICT_REFERENCED code when an entity is still referenced by others."""
    assert isinstance(exc, ReferencedError)
    return JSONResponse(
        {"code": "CONFLICT_REFERENCED", "message": str(exc)},
        status_code=409,
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return the original HTTP status code with an HTTP_{code} error code."""
    assert isinstance(exc, HTTPException)
    return JSONResponse(
        {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail)},
        status_code=exc.status_code,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return HTTP 500 with INTERNAL_ERROR code and log the full exception traceback."""
    logger.exception("Unhandled exception", exc_info=exc)
    return JSONResponse(
        {"code": "INTERNAL_ERROR", "message": "Internal server error"},
        status_code=500,
    )
