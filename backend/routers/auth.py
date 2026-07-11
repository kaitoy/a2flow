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
    verify_csrf,
)
from models.response import ApiResponse
from models.user import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Credentials submitted to the login endpoint."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    username: str
    password: str


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
    result = await service.login(body.username, body.password)
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
    _user: CurrentUserDep,
    _csrf: Annotated[None, Depends(verify_csrf)],
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    """Revoke the current session and clear the auth cookies."""
    await service.logout(request.cookies.get(SESSION_COOKIE_NAME, ""))
    _clear_auth_cookies(response)
    return ApiResponse(meta=meta, data=None)


@router.get("/me", response_model=ApiResponse[UserRead])
async def me(
    user: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[UserRead]:
    """Return the currently authenticated user."""
    return ApiResponse(meta=meta, data=UserRead.model_validate(user))
