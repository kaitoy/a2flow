"""Authentication endpoints: login, logout, current-user lookup, and OIDC sign-in.

Login establishes a server-side session and sets two cookies: an HttpOnly
``a2flow_session`` cookie carrying the opaque session token, and a readable
``a2flow_csrf`` cookie carrying the double-submit CSRF token. Both are session
cookies (no ``Max-Age``/``Expires``), so they are cleared when the browser
closes; server-side validity is governed by the sliding idle timeout.

The two ``/oidc/*`` routes are browser redirects, not API calls: they answer
``302`` with no envelope, and report every refusal as ``/login?sso_error=<code>``.
"""

import logging
from typing import Annotated
from urllib.parse import quote, urlencode, urlsplit

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from config import get_settings
from dependencies.auth import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    AuthServiceDep,
    CurrentUserDep,
    ImpersonationServiceDep,
    RealUserDep,
    verify_csrf,
)
from dependencies.authz import require_actor_roles
from dependencies.context import ApiMetaDep
from dependencies.repository import EffectiveRoleRepositoryDep
from dependencies.service import OidcLoginServiceDep
from models.constraints import TenantSlug
from models.response import ApiResponse
from models.user import Role, User, UserRead
from repositories.effective_roles import EffectiveRoleRepository
from services.oidc_login import (
    STATE_COOKIE_NAME,
    STATE_TTL_SECONDS,
    SsoErrorCode,
    SsoLoginError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _to_read(repo: EffectiveRoleRepository, user: User) -> UserRead:
    """Project a user into its read view, resolving its group-inherited roles.

    Every response from this router carries ``groupRoles`` alongside ``roles``:
    the frontend unions the two to decide which navigation and actions to show,
    so a user whose only ``developer`` grant comes from a group must still see
    the developer UI right after signing in.

    Args:
        repo: Repository resolving the roles inherited from group membership.
        user: The user to project.

    Returns:
        The read view, carrying both direct and inherited roles.
    """
    return UserRead.from_user(
        user,
        group_roles=await repo.group_roles_for_user(user.id),
        group_ids=(await repo.group_ids_for_users([user.id])).get(user.id, []),
    )


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
    effective_roles: EffectiveRoleRepositoryDep,
    meta: ApiMetaDep,
) -> ApiResponse[UserRead]:
    """Authenticate a user and start a session, returning the current user.

    On success, sets the session and CSRF cookies. On failure, raises
    ``UnauthorizedError`` (HTTP 401) with a generic message, or
    ``TooManyLoginAttemptsError`` (HTTP 429) once the account has too many
    recent failures.
    """
    result = await service.login(
        body.username, body.password, tenant_name=body.tenant_name
    )
    _set_auth_cookies(
        response,
        session_token=result.session_token,
        csrf_token=result.csrf_token,
    )
    return ApiResponse(meta=meta, data=await _to_read(effective_roles, result.user))


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

    Also sends ``Clear-Site-Data: "cache"`` so API responses the browser kept
    in its HTTP cache -- e.g. the design-chat history, which is sent with
    ``Cache-Control: private, no-cache`` so its polls can revalidate -- do not
    outlive the session on a shared machine. Browsers honor the header only in
    a secure context (HTTPS or localhost).
    """
    await service.logout(request.cookies.get(SESSION_COOKIE_NAME, ""))
    _clear_auth_cookies(response)
    response.headers["Clear-Site-Data"] = '"cache"'
    return ApiResponse(meta=meta, data=None)


@router.get("/me", response_model=ApiResponse[MeResponse])
async def me(
    user: CurrentUserDep,
    real_user: RealUserDep,
    effective_roles: EffectiveRoleRepositoryDep,
    meta: ApiMetaDep,
) -> ApiResponse[MeResponse]:
    """Return the currently authenticated (effective) user.

    ``impersonated_by`` is set whenever the real actor differs from the
    effective user, i.e. an impersonation is active.
    """
    impersonated_by = (
        await _to_read(effective_roles, real_user) if real_user.id != user.id else None
    )
    return ApiResponse(
        meta=meta,
        data=MeResponse(
            user=await _to_read(effective_roles, user),
            impersonated_by=impersonated_by,
        ),
    )


@router.post("/impersonate", response_model=ApiResponse[MeResponse])
async def start_impersonation(
    body: ImpersonateRequest,
    actor: RealUserDep,
    service: ImpersonationServiceDep,
    effective_roles: EffectiveRoleRepositoryDep,
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
            user=await _to_read(effective_roles, target),
            impersonated_by=await _to_read(effective_roles, actor),
        ),
    )


@router.delete("/impersonate", response_model=ApiResponse[MeResponse])
async def stop_impersonation(
    actor: RealUserDep,
    service: ImpersonationServiceDep,
    effective_roles: EffectiveRoleRepositoryDep,
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
        data=MeResponse(
            user=await _to_read(effective_roles, actor), impersonated_by=None
        ),
    )


def _origin(url: str) -> tuple[str, str, int | None]:
    """Return the ``(scheme, host, port)`` of ``url``, with the default port filled in."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    port = parts.port or {"http": 80, "https": 443}.get(scheme)
    return scheme, (parts.hostname or "").lower(), port


def _sso_error(code: SsoErrorCode) -> str:
    """Return the login-page URL that shows the toast for ``code``."""
    return f"/login?sso_error={quote(code.value)}"


@router.get(
    "/oidc/start",
    status_code=302,
    response_class=RedirectResponse,
    responses={
        302: {"description": "Redirect to the identity provider or login page."}
    },
)
async def oidc_start(
    request: Request,
    service: OidcLoginServiceDep,
    tenant: str = "",
    hop: str | None = None,
) -> RedirectResponse:
    """Begin an OpenID Connect sign-in for the tenant named ``tenant``.

    Unguarded browser redirect (no envelope). If the deployment's
    ``app_base_url`` names another origin than this request's, the browser is
    first sent to the same path on that origin, so the state cookie is set where
    the identity provider will call back. That hop happens at most once: it adds
    ``hop=1`` to the query, and a request carrying ``hop`` skips the origin
    comparison, so a backend that never sees the public origin (no trusted proxy
    headers) costs one extra redirect rather than a redirect loop. Otherwise it is sent to the identity
    provider with the encrypted state cookie, scoped to the callback path.
    A request the browser marks ``Sec-Fetch-Site: cross-site`` is refused the
    same way, so another site cannot sign a visitor in to an account it chose.
    Every failure -- including an unexpected one -- redirects to the login page
    with ``sso_error=unavailable``, which never reveals whether a tenant exists.

    Args:
        request: The incoming request.
        service: The sign-in service.
        tenant: The tenant name typed on the login screen.
        hop: Marker set by the origin redirect; its presence disables a second one.
    """
    if request.headers.get("sec-fetch-site") == "cross-site":
        return RedirectResponse(_sso_error(SsoErrorCode.unavailable), status_code=302)
    try:
        base_url = await service.app_base_url()
        if (
            hop is None
            and base_url
            and _origin(base_url) != _origin(str(request.base_url))
        ):
            parts = urlsplit(base_url)
            query = urlencode([*request.query_params.multi_items(), ("hop", "1")])
            target = f"{parts.scheme}://{parts.netloc}{request.url.path}?{query}"
            return RedirectResponse(target, status_code=302)
        begun = await service.start(tenant)
    except SsoLoginError as exc:
        return RedirectResponse(_sso_error(exc.code), status_code=302)
    except Exception:
        logger.exception("Unexpected error starting an SSO sign-in")
        return RedirectResponse(_sso_error(SsoErrorCode.unavailable), status_code=302)
    response = RedirectResponse(begun.authorization_url, status_code=302)
    response.set_cookie(
        STATE_COOKIE_NAME,
        begun.state_cookie,
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path=request.url_for("oidc_callback").path,
    )
    return response


@router.get(
    "/oidc/callback",
    status_code=302,
    response_class=RedirectResponse,
    responses={302: {"description": "Redirect to the app or login page."}},
)
async def oidc_callback(
    request: Request,
    service: OidcLoginServiceDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Finish an OpenID Connect sign-in from the identity provider's redirect.

    Unguarded browser redirect (no envelope). On success sets the session and
    CSRF cookies and redirects to ``/``; on any refusal -- including an
    unexpected error, logged under the request id -- redirects to
    ``/login?sso_error=<code>``. The state cookie is always deleted.

    Args:
        request: The incoming request.
        service: The sign-in service.
        code: The authorization code.
        state: The ``state`` echoed by the identity provider.
        error: Set when the identity provider refused the sign-in.
    """
    try:
        result = await service.complete(
            state_cookie=request.cookies.get(STATE_COOKIE_NAME),
            state=state,
            code=code,
            error=error,
        )
        response = RedirectResponse("/", status_code=302)
        _set_auth_cookies(
            response,
            session_token=result.session_token,
            csrf_token=result.csrf_token,
        )
    except SsoLoginError as exc:
        response = RedirectResponse(_sso_error(exc.code), status_code=302)
    except Exception:
        logger.exception("Unexpected error completing an SSO sign-in")
        response = RedirectResponse(_sso_error(SsoErrorCode.failed), status_code=302)
    response.delete_cookie(
        STATE_COOKIE_NAME,
        path=request.url_for("oidc_callback").path,
        secure=_cookie_secure(),
        httponly=True,
        samesite="lax",
    )
    return response
