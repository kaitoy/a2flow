"""Authentication and CSRF FastAPI dependencies.

``get_current_user`` resolves the logged-in user from the session cookie (and
caches it on ``request.state.user``); attaching it as a router dependency turns
every route in that router into an authenticated endpoint. ``verify_csrf``
enforces the double-submit cookie defense on state-changing requests. Both are
applied to the resource routers in :mod:`routers` and are easy to override in
tests via ``app.dependency_overrides``.

``get_auth_service``/``AuthServiceDep`` are defined here, not in
:mod:`dependencies.service`, and built directly from :mod:`repositories`
rather than from ``dependencies.repository``'s ``UserRepositoryDep``/
``AuthSessionRepositoryDep`` aliases. ``dependencies.repository`` imports
``CurrentTenantIdDep`` from this module to scope its tenant-aware repository
factories; importing ``dependencies.service`` here (which itself imports
``dependencies.repository``) would close that into a circular import.
"""

import secrets
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.database import get_session
from models.user import User
from repositories import SqlAuthSessionRepository, SqlUserRepository
from repositories.exceptions import CsrfError, ForbiddenError
from services import AuthService

#: Name of the HttpOnly cookie carrying the opaque session token.
SESSION_COOKIE_NAME = "a2flow_session"
#: Name of the readable cookie carrying the double-submit CSRF token.
CSRF_COOKIE_NAME = "a2flow_csrf"
#: Header the client must echo the CSRF cookie value in on unsafe requests.
CSRF_HEADER_NAME = "X-CSRF-Token"
#: HTTP methods that do not require CSRF validation.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

#: Local duplicate of ``dependencies.repository.DBSessionDep``. FastAPI caches
#: dependency results by the underlying callable (``get_session``), so this
#: resolves to the same per-request session as the alias in that module -- it
#: is redefined here only to avoid importing ``dependencies.repository``.
_DbSessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_auth_service(db: _DbSessionDep) -> AuthService:
    """Create an AuthService wiring the user and auth-session repositories."""
    return AuthService(SqlUserRepository(db), SqlAuthSessionRepository(db))


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(request: Request, auth_service: AuthServiceDep) -> User:
    """Resolve and return the authenticated user for the current request.

    Reads the session cookie, validates it through the :class:`AuthService`
    (which also slides the idle timeout), and stashes the user on
    ``request.state`` for downstream access.

    Args:
        request: The incoming request, used to read the session cookie.
        auth_service: Service that validates the session token.

    Returns:
        The authenticated user.

    Raises:
        UnauthorizedError: If no valid, unexpired session is present.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    user = await auth_service.authenticate(token)
    request.state.user = user
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def get_current_user_id(user: CurrentUserDep) -> str:
    """Return the authenticated user's ID, resolved from the session cookie.

    Args:
        user: The user resolved by :func:`get_current_user`.

    Returns:
        The authenticated user's ID.
    """
    return user.id


CurrentUserIdDep = Annotated[str, Depends(get_current_user_id)]


def get_current_tenant_id(user: CurrentUserDep) -> str:
    """Return the authenticated user's tenant id, resolved from the session cookie.

    Args:
        user: The user resolved by :func:`get_current_user`.

    Returns:
        The authenticated user's tenant id.

    Raises:
        ForbiddenError: If the user is platform-scoped (``tenant_id is None`` —
            the seeded system user, or an admin operating outside any tenant).
            Tenant-scoped routes are simply inaccessible to platform-scoped
            callers; there is no implicit "see everything" fallback.
    """
    if user.tenant_id is None:
        raise ForbiddenError("This operation requires a tenant-scoped account")
    return user.tenant_id


CurrentTenantIdDep = Annotated[str, Depends(get_current_tenant_id)]


async def verify_csrf(request: Request) -> None:
    """Enforce the double-submit CSRF defense on state-changing requests.

    Safe (read-only) methods pass through. For unsafe methods the request must
    carry a non-empty ``X-CSRF-Token`` header equal to the CSRF cookie value;
    the comparison is constant-time.

    Args:
        request: The incoming request.

    Raises:
        CsrfError: If the header is missing or does not match the cookie.
    """
    if request.method in SAFE_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
    header = request.headers.get(CSRF_HEADER_NAME, "")
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise CsrfError()
