"""Authentication and CSRF FastAPI dependencies.

``get_current_user`` resolves the *effective* user for the current request --
the real session-cookie identity, unless a valid impersonation is active (see
:data:`IMPERSONATE_HEADER_NAME` below), in which case it's the impersonation
target. Attaching it as a router dependency turns every route in that router
into an authenticated endpoint; because nearly everything in this app
(authorization checks, tenant scoping via ``CurrentTenantIdDep``, and audit
fields via ``CurrentUserIdDep``) is derived from ``CurrentUserDep``, this is
the single point through which impersonation transparently applies
everywhere else with no further code changes. ``verify_csrf`` enforces the
double-submit cookie defense on state-changing requests. Both are applied to
the resource routers in :mod:`routers` and are easy to override in tests via
``app.dependency_overrides``.

``RealUserDep`` resolves the real, session-cookie identity only, ignoring any
impersonation header -- used where a request must always act on the actual
logged-in user regardless of impersonation state: ``dependencies.authz``'s
``require_actor_roles`` (the impersonate start/stop routes' role gate -- see
that module's docstring for why gating those routes with the ordinary,
``CurrentUserDep``-based ``require_roles`` would lock an impersonating admin
out of ever stopping), ``POST /auth/logout``, and ``GET /auth/me``'s
``impersonated_by`` field.

An invalid/stale impersonation header (target since disabled, promoted, or
the impersonation already stopped elsewhere) is never treated as an error --
it silently falls back to the real user. The frontend persists its
impersonation selection to ``localStorage`` and attaches it starting with the
very first ``/auth/me`` call on page load; raising here would fail that call
and boot a legitimate admin all the way out to the login page over a merely
stale local selection, not just out of impersonation.

``get_auth_service``/``AuthServiceDep`` and
``get_impersonation_service``/``ImpersonationServiceDep`` are defined here,
not in :mod:`dependencies.service`, and built directly from
:mod:`repositories` rather than from ``dependencies.repository``'s
``UserRepositoryDep``/``AuthSessionRepositoryDep`` aliases.
``dependencies.repository`` imports ``CurrentTenantIdDep`` from this module to
scope its tenant-aware repository factories; importing
``dependencies.service`` here (which itself imports ``dependencies.repository``)
would close that into a circular import.
"""

import secrets
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.database import get_session
from models.user import User
from repositories import (
    SqlAuthSessionRepository,
    SqlImpersonationEventRepository,
    SqlTenantRepository,
    SqlUserRepository,
)
from repositories.exceptions import CsrfError, ForbiddenError
from services import AuthService, ImpersonationService

#: Name of the HttpOnly cookie carrying the opaque session token.
SESSION_COOKIE_NAME = "a2flow_session"
#: Name of the readable cookie carrying the double-submit CSRF token.
CSRF_COOKIE_NAME = "a2flow_csrf"
#: Header the client must echo the CSRF cookie value in on unsafe requests.
CSRF_HEADER_NAME = "X-CSRF-Token"
#: HTTP methods that do not require CSRF validation.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
#: Header a platform-scoped (super_admin) caller must send to select which
#: tenant to act within ("act as tenant X"). Distinct from the test-only
#: ``X-User-Tenant-Id`` header in ``tests/conftest.py``, which controls the
#: synthetic test user's own ``tenant_id``, not a super_admin's selected tenant.
TENANT_HEADER_NAME = "X-Tenant-Id"
#: Header naming the user id to impersonate. Re-validated by
#: :func:`get_current_user` on every request that carries it, not just when
#: impersonation starts -- see the module docstring.
IMPERSONATE_HEADER_NAME = "X-Impersonate-User-Id"

#: Local duplicate of ``dependencies.repository.DBSessionDep``. FastAPI caches
#: dependency results by the underlying callable (``get_session``), so this
#: resolves to the same per-request session as the alias in that module -- it
#: is redefined here only to avoid importing ``dependencies.repository``.
_DbSessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_auth_service(db: _DbSessionDep) -> AuthService:
    """Create an AuthService wiring the user, auth-session, and tenant repositories."""
    return AuthService(
        SqlUserRepository(db), SqlAuthSessionRepository(db), SqlTenantRepository(db)
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_impersonation_service(db: _DbSessionDep) -> ImpersonationService:
    """Create an ImpersonationService wiring the audit-trail and user repositories."""
    return ImpersonationService(
        SqlImpersonationEventRepository(db), SqlUserRepository(db)
    )


ImpersonationServiceDep = Annotated[
    ImpersonationService, Depends(get_impersonation_service)
]


async def get_session_user(request: Request, auth_service: AuthServiceDep) -> User:
    """Resolve and return the real, session-cookie-authenticated user.

    Reads the session cookie and validates it through the :class:`AuthService`
    (which also slides the idle timeout). Unlike :func:`get_current_user`,
    this is never affected by an impersonation header -- see the module
    docstring for where that distinction matters.

    Args:
        request: The incoming request, used to read the session cookie.
        auth_service: Service that validates the session token.

    Returns:
        The real, authenticated user.

    Raises:
        UnauthorizedError: If no valid, unexpired session is present.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    user = await auth_service.authenticate(token)
    request.state.session_user = user
    return user


RealUserDep = Annotated[User, Depends(get_session_user)]


async def get_current_user(
    request: Request,
    session_user: RealUserDep,
    impersonation_service: ImpersonationServiceDep,
) -> User:
    """Resolve and return the *effective* user for the current request.

    Returns the real session user unchanged, unless the request carries
    :data:`IMPERSONATE_HEADER_NAME` naming a user the real session user has an
    open, still-valid impersonation of -- see the module docstring for why an
    invalid header falls back to the real user instead of raising, and why
    nearly every other authorization/tenant-scoping/audit-field concern in the
    app composes with impersonation for free by depending on this instead of
    :data:`RealUserDep`.

    Args:
        request: The incoming request, used to read the impersonation header.
        session_user: The real, session-authenticated user.
        impersonation_service: Service that validates and resolves an active
            impersonation.

    Returns:
        The effective user: the impersonation target if one is active and
        valid, otherwise ``session_user``.
    """
    target_id = request.headers.get(IMPERSONATE_HEADER_NAME, "").strip()
    if not target_id:
        request.state.user = session_user
        return session_user
    effective = await impersonation_service.resolve_effective_user(
        actor=session_user, target_user_id=target_id
    )
    request.state.user = effective
    return effective


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


def get_current_tenant_id(user: CurrentUserDep, request: Request) -> str:
    """Return the tenant id the current request is scoped to.

    A tenant-scoped user (``tenant_id is not None``) is always scoped to
    their own tenant -- the :data:`TENANT_HEADER_NAME` header is ignored for
    them, so a tenant-scoped caller can never escalate into another tenant by
    sending it. A platform-scoped caller (``tenant_id is None`` -- a
    super_admin, or the seeded system user) has no tenant of their own, so
    the tenant to act within is instead read from that header: the frontend's
    tenant switcher sets it from the super_admin's active tenant selection,
    letting them act as any one tenant at a time.

    Args:
        user: The user resolved by :func:`get_current_user`.
        request: The incoming request, used to read :data:`TENANT_HEADER_NAME`
            for a platform-scoped caller.

    Returns:
        The tenant id this request is scoped to.

    Raises:
        ForbiddenError: If the caller is platform-scoped and the header is
            missing or empty. There is no implicit "see everything" fallback
            and no server-side default tenant.
    """
    if user.tenant_id is not None:
        return user.tenant_id
    tenant_id = request.headers.get(TENANT_HEADER_NAME, "").strip()
    if not tenant_id:
        raise ForbiddenError(
            f"Select a tenant to act as via the {TENANT_HEADER_NAME} header"
        )
    return tenant_id


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
