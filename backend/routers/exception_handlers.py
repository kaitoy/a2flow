"""FastAPI exception handlers that map domain exceptions to envelope error responses.

Each handler builds an :class:`ApiResponse` with ``data=None`` and ``error``
populated, mirroring the wire format produced by router success responses.
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
from repositories.exceptions import (
    AvatarValidationError,
    CsrfError,
    DependencyCycleError,
    ForbiddenError,
    ForeignKeyViolationError,
    McpConnectionError,
    NotFoundError,
    QueryValidationError,
    ReferencedError,
    RegistryUnavailableError,
    SecretResolutionError,
    SecretValidationError,
    SessionRunInProgressError,
    SkillCloneError,
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


async def avatar_validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return HTTP 422 with INVALID_AVATAR code for an unsupported or oversized avatar image."""
    assert isinstance(exc, AvatarValidationError)
    return _envelope_error(
        request,
        code="INVALID_AVATAR",
        message=str(exc),
        status_code=422,
        details={"reason": exc.reason},
    )


async def secret_validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return HTTP 422 with INVALID_SECRET code when a merged secret shape is invalid."""
    assert isinstance(exc, SecretValidationError)
    return _envelope_error(
        request,
        code="INVALID_SECRET",
        message=str(exc),
        status_code=422,
        details={"reason": exc.reason},
    )


async def secret_resolution_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return HTTP 502 with SECRET_RESOLUTION_FAILED code when a secret reference cannot be resolved.

    The raw ``reason`` is logged server-side only, mirroring the MCP and skill
    clone handlers, since it can embed decryption or Vault failure internals.
    """
    assert isinstance(exc, SecretResolutionError)
    logger.warning("Secret %s resolution failed: %s", exc.secret_name, exc.reason)
    return _envelope_error(
        request,
        code="SECRET_RESOLUTION_FAILED",
        message=f"Failed to resolve secret {exc.secret_name!r}",
        status_code=502,
        details={"secret": exc.secret_name},
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


async def skill_clone_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return HTTP 502 with SKILL_CLONE_FAILED code when a skill repository cannot be cloned."""
    assert isinstance(exc, SkillCloneError)
    logger.warning("Skill %s clone failed: %s", exc.skill_id, exc.reason)
    return _envelope_error(
        request,
        code="SKILL_CLONE_FAILED",
        message=f"Failed to prepare skill {exc.skill_id!r}",
        status_code=502,
        details={"skillId": exc.skill_id},
    )


async def mcp_connection_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return HTTP 502 with MCP_UNREACHABLE code when a remote MCP server cannot be reached."""
    assert isinstance(exc, McpConnectionError)
    logger.warning("MCP server %s unreachable: %s", exc.server, exc.reason)
    return _envelope_error(
        request,
        code="MCP_UNREACHABLE",
        message=f"MCP server {exc.server!r} unreachable",
        status_code=502,
        details={"server": exc.server},
    )


async def registry_unavailable_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return HTTP 502 with REGISTRY_UNREACHABLE code when the MCP registry fails."""
    assert isinstance(exc, RegistryUnavailableError)
    logger.warning("MCP registry unavailable: %s", exc.reason)
    return _envelope_error(
        request,
        code="REGISTRY_UNREACHABLE",
        message="MCP registry unavailable",
        status_code=502,
    )


async def session_run_in_progress_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return HTTP 409 with SESSION_RUN_IN_PROGRESS code when a session is already running."""
    assert isinstance(exc, SessionRunInProgressError)
    return _envelope_error(
        request,
        code="SESSION_RUN_IN_PROGRESS",
        message=str(exc),
        status_code=409,
        details={"threadId": exc.thread_id},
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
    """Return HTTP 401 with UNAUTHENTICATED code when no valid session is present.

    Also clears the session and CSRF cookies on the response. The cookies are
    session cookies with no ``Max-Age``, so a server-side idle expiry leaves a
    stale cookie in the browser; clearing it here ensures the edge middleware
    (which only checks cookie presence) stops treating the visitor as logged in
    and lets ``/login`` render instead of bouncing back to a protected route.
    """
    assert isinstance(exc, UnauthorizedError)
    response = _envelope_error(
        request,
        code="UNAUTHENTICATED",
        message=str(exc),
        status_code=401,
    )
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
    return response


async def csrf_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return HTTP 403 with CSRF_FAILED code when CSRF validation fails."""
    assert isinstance(exc, CsrfError)
    return _envelope_error(
        request,
        code="CSRF_FAILED",
        message=str(exc),
        status_code=403,
    )


async def forbidden_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return HTTP 403 with FORBIDDEN code when the user lacks permission."""
    assert isinstance(exc, ForbiddenError)
    return _envelope_error(
        request,
        code="FORBIDDEN",
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
