"""FastAPI exception handlers that map exceptions to envelope error responses.

Each handler builds an :class:`ApiResponse` with ``data=None`` and ``error``
populated, mirroring the wire format produced by router success responses.
Every domain error is a :class:`HttpMappedError` and goes through
:func:`api_error_handler`; the rest cover FastAPI's own request validation,
``HTTPException``, and anything unhandled.
"""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from dependencies.auth import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME
from models.response import ApiError, ApiMeta, ApiResponse
from repositories.exceptions import HttpMappedError, UnauthorizedError

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


def _sanitize_validation_errors(
    errors: Sequence[Any],
) -> list[dict[str, Any]]:
    """Return validation errors with non-JSON-serializable context stringified.

    A ``ValueError`` raised inside a Pydantic validator is surfaced by
    ``RequestValidationError.errors()`` as ``ctx={"error": <ValueError>}``; the
    exception object cannot be JSON-serialized into the response envelope. This
    replaces any such non-primitive ``ctx`` value with its string form.

    Args:
        errors: The raw error dicts from ``RequestValidationError.errors()``.

    Returns:
        A copy of the errors safe to serialize as JSON.
    """
    safe: list[dict[str, Any]] = []
    for err in errors:
        entry = dict(err)
        ctx = entry.get("ctx")
        if isinstance(ctx, dict):
            entry["ctx"] = {
                key: value
                if isinstance(value, str | int | float | bool | None.__class__)
                else str(value)
                for key, value in ctx.items()
            }
        safe.append(entry)
    return safe


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
        details={"errors": _sanitize_validation_errors(exc.errors())},
    )


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render any :class:`HttpMappedError` as the envelope its class describes.

    The class carries the code, status, and details; the only per-class twist
    handled here is :class:`UnauthorizedError`, which also clears the session
    and CSRF cookies. Those are session cookies with no ``Max-Age``, so a
    server-side idle expiry leaves a stale cookie in the browser; clearing it
    ensures the edge middleware (which only checks cookie presence) stops
    treating the visitor as logged in and lets ``/login`` render instead of
    bouncing back to a protected route.
    """
    assert isinstance(exc, HttpMappedError)
    exc.log()
    response = _envelope_error(
        request,
        code=exc.code,
        message=exc.public_message(),
        status_code=exc.http_status,
        details=exc.details(),
    )
    if isinstance(exc, UnauthorizedError):
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")
        response.delete_cookie(CSRF_COOKIE_NAME, path="/")
    return response


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
