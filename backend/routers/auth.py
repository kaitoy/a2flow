"""Authentication endpoints: login, logout, and current-user lookup.

Login establishes a server-side session and sets two cookies: an HttpOnly
``a2flow_session`` cookie carrying the opaque session token, and a readable
``a2flow_csrf`` cookie carrying the double-submit CSRF token. Both are session
cookies (no ``Max-Age``/``Expires``), so they are cleared when the browser
closes; server-side validity is governed by the sliding idle timeout.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from config import get_settings
from dependencies import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    ApiMetaDep,
    AuthServiceDep,
    CurrentUserDep,
    ImpersonationServiceDep,
    RealUserDep,
    require_actor_roles,
    verify_csrf,
)
from models.constraints import TenantSlug
from models.response import ApiResponse
from models.user import Role, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Credentials submitted to the login endpoint."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    username: str
    password: str
    #: Name (the URL-safe kebab-case identifier) of the tenant the user
    #: belongs to. Required to disambiguate a tenant-scoped user's username
    #: (unique only within its tenant); must be omitted for a platform-scoped
    #: user (``root``, or any other super_admin).
    tenant_name: TenantSlug | None = None


class MeResponse(BaseModel):
    """Response shape for ``GET /auth/me`` and the impersonate start/stop endpoints.

    ``user`` is the effective identity (the impersonation target, while one
    is active). ``impersonated_by`` is the real, session-authenticated actor
    when it differs from ``user`` -- the signal the frontend uses to render
    an "acting as" indicator and to self-heal a stale local impersonation
    selection when it comes back ``None``.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    user: UserRead
    impersonated_by: UserRead | None = None


class ImpersonateRequest(BaseModel):
    """Body submitted to start impersonating another user."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    target_user_id: str


def _cookie_secure() -> bool:
    """Return whether auth cookies should carry the ``Secure`` attribute.

    Controlled by ``config.Settings.session_cookie_secure`` (the
    ``SESSION_COOKIE_SECURE`` environment variable, default ``false`` for
    local HTTP development); set it to ``true`` when serving over HTTPS.
    """
    return get_settings().session_cookie_secure


def _set_auth_cookies(
    response: Response, *, session_token: str, csrf_token: str
) -> None:
    """Set the session and CSRF cookies on the response as session cookies."""
    secure = _cookie_secure()
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    """Remove the session and CSRF cookies from the client."""
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


@router.post("/login", response_model=ApiResponse[UserRead])
async def login(
    body: LoginRequest,
    response: Response,
    service: AuthServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[UserRead]:
    """Authenticate a user and start a session, returning the current user.

    On success, sets the session and CSRF cookies. On failure, raises
    ``UnauthorizedError`` (HTTP 401) with a generic message.
    """
    result = await service.login(
        body.username, body.password, tenant_name=body.tenant_name
    )
    _set_auth_cookies(
        response,
        session_token=result.session_token,
        csrf_token=result.csrf_token,
    )
    return ApiResponse(meta=meta, data=UserRead.model_validate(result.user))


@router.post("/logout", response_model=ApiResponse[None])
async def logout(
    request: Request,
    response: Response,
    service: AuthServiceDep,
    _user: RealUserDep,
    _csrf: Annotated[None, Depends(verify_csrf)],
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    """Revoke the current session and clear the auth cookies.

    Depends on :data:`~dependencies.RealUserDep`, not the possibly-
    impersonated ``CurrentUserDep`` -- logout must always end the real
    session regardless of any impersonation header on this request.
    """
    await service.logout(request.cookies.get(SESSION_COOKIE_NAME, ""))
    _clear_auth_cookies(response)
    return ApiResponse(meta=meta, data=None)


@router.get("/me", response_model=ApiResponse[MeResponse])
async def me(
    user: CurrentUserDep,
    real_user: RealUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[MeResponse]:
    """Return the currently authenticated (effective) user.

    ``impersonated_by`` is set whenever the real actor differs from the
    effective user, i.e. an impersonation is active.
    """
    impersonated_by = (
        UserRead.model_validate(real_user) if real_user.id != user.id else None
    )
    return ApiResponse(
        meta=meta,
        data=MeResponse(
            user=UserRead.model_validate(user), impersonated_by=impersonated_by
        ),
    )


@router.post("/impersonate", response_model=ApiResponse[MeResponse])
async def start_impersonation(
    body: ImpersonateRequest,
    actor: RealUserDep,
    service: ImpersonationServiceDep,
    _role: Annotated[None, Depends(require_actor_roles(Role.admin))],
    _csrf: Annotated[None, Depends(verify_csrf)],
    meta: ApiMetaDep,
) -> ApiResponse[MeResponse]:
    """Start impersonating another user, recording the audit event.

    Gated by :func:`~dependencies.require_actor_roles` (checked against the
    real actor, not any already-active impersonation) rather than the
    ordinary ``require_roles`` -- see that dependency's docstring.
    """
    target = await service.start(actor=actor, target_user_id=body.target_user_id)
    return ApiResponse(
        meta=meta,
        data=MeResponse(
            user=UserRead.model_validate(target),
            impersonated_by=UserRead.model_validate(actor),
        ),
    )


@router.delete("/impersonate", response_model=ApiResponse[MeResponse])
async def stop_impersonation(
    actor: RealUserDep,
    service: ImpersonationServiceDep,
    _csrf: Annotated[None, Depends(verify_csrf)],
    meta: ApiMetaDep,
) -> ApiResponse[MeResponse]:
    """Stop impersonating, closing the open audit event.

    A no-op, never an error, if no impersonation is currently open for the
    real actor -- so a client can always safely call this regardless of its
    own local state.
    """
    await service.stop(actor=actor)
    return ApiResponse(
        meta=meta,
        data=MeResponse(user=UserRead.model_validate(actor), impersonated_by=None),
    )
