"""Tests for ``/auth/oidc/start`` and ``/auth/oidc/callback`` over HTTP.

The real auth dependencies run (no header overrides); only the database, the
OIDC client (pointed at :class:`~tests._oidc_fake.FakeIdp`) and the secret
cipher are replaced.
"""

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from http.cookies import Morsel, SimpleCookie
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure.oidc_client import OidcClient
from infrastructure.secret_cipher import SecretCipher
from models.tenant import Tenant
from models.user import SYSTEM_USER_ID
from models.user_group import UserGroup
from services.oidc_login import STATE_COOKIE_NAME, OidcLoginService
from tests._engine import make_test_engine
from tests._oidc_fake import CLIENT_ID, ISSUER, FakeIdp
from tests._seed import seed_users

TENANT_ID = "t-acme"
CALLBACK_PATH = "/api/v1/auth/oidc/callback"


@dataclass
class Ctx:
    """The HTTP client, the fake IdP, and the engine behind them."""

    client: AsyncClient
    fake: FakeIdp
    engine: AsyncEngine


@pytest_asyncio.fixture()
async def ctx(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[Ctx, None]:
    """Serve the app over a throwaway DB with tenant ``acme`` set up for SSO."""
    from dependencies.singletons import get_oidc_client, get_secret_cipher
    from infrastructure.database import get_session
    from main import app

    engine = await make_test_engine()
    await seed_users(engine, ids=())
    cipher = SecretCipher(Fernet.generate_key())
    async with AsyncSession(engine, expire_on_commit=False) as db:
        db.add(
            Tenant(
                id=TENANT_ID,
                name="acme",
                display_name="Acme",
                enabled=True,
                oidc_enabled=True,
                oidc_issuer=ISSUER,
                oidc_client_id=CLIENT_ID,
                oidc_client_secret=cipher.encrypt("s3cret"),
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        monkeypatch.setenv("APP_BASE_URL", "http://test")
        get_settings.cache_clear()
        db.add(
            UserGroup(
                id="g-eng",
                name="Eng",
                idp_group="eng",
                roles=["developer"],
                tenant_id=TENANT_ID,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await db.commit()

    fake = FakeIdp()
    oidc = OidcClient(httpx.AsyncClient(transport=fake.transport), allowed_hosts=())

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_oidc_client] = lambda: oidc
    app.dependency_overrides[get_secret_cipher] = lambda: cipher
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield Ctx(client=ac, fake=fake, engine=engine)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def set_app_base_url(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    """Point the deployment's ``APP_BASE_URL`` at ``url``."""
    monkeypatch.setenv("APP_BASE_URL", url)
    get_settings.cache_clear()


def set_cookies(resp: httpx.Response) -> dict[str, Morsel[str]]:
    """Return the cookies a response sets, by name."""
    jar: SimpleCookie = SimpleCookie()
    for header in resp.headers.get_list("set-cookie"):
        jar.load(header)
    return dict(jar)


async def start(c: Ctx, tenant: str = "acme") -> tuple[httpx.Response, str, str]:
    """Start a sign-in; return the response, the state cookie and the ``state``."""
    resp = await c.client.get("/api/v1/auth/oidc/start", params={"tenant": tenant})
    assert resp.status_code == 302
    query = dict(parse_qsl(urlsplit(resp.headers["location"]).query))
    c.fake.next_claims = c.fake.claims(
        nonce=query["nonce"],
        sub="s1",
        email="alice@x.com",
        email_verified=True,
        groups=["eng"],
        preferred_username="alice",
    )
    return resp, set_cookies(resp)[STATE_COOKIE_NAME].value, query["state"]


async def callback(c: Ctx, *, cookie: str | None, **params: Any) -> httpx.Response:
    """Call the callback with the state cookie sent explicitly (or not at all)."""
    headers = {"Cookie": f"{STATE_COOKIE_NAME}={cookie}"} if cookie else {}
    return await c.client.get(
        "/api/v1/auth/oidc/callback", params=params, headers=headers
    )


def assert_state_cleared(resp: httpx.Response) -> None:
    """Assert the response deletes the state cookie on the callback path."""
    morsel = set_cookies(resp)[STATE_COOKIE_NAME]
    assert morsel.value == ""
    assert morsel["path"] == CALLBACK_PATH
    assert morsel["max-age"] == "0"


@pytest.mark.asyncio
async def test_full_sso_round_trip_sets_session(ctx: Ctx) -> None:
    resp, cookie, state = await start(ctx)
    assert resp.headers["location"].startswith(f"{ISSUER}/authorize?")
    morsel = set_cookies(resp)[STATE_COOKIE_NAME]
    assert morsel["httponly"] is True
    assert morsel["samesite"].lower() == "lax"
    assert morsel["path"] == CALLBACK_PATH
    assert morsel["max-age"] == "600"

    done = await callback(ctx, cookie=cookie, code="code-1", state=state)
    assert done.status_code == 302
    assert done.headers["location"] == "/"
    cookies = set_cookies(done)
    assert cookies["a2flow_session"]["httponly"] is True
    assert cookies["a2flow_csrf"].value
    assert_state_cleared(done)

    me = await ctx.client.get(
        "/api/v1/auth/me",
        headers={"Cookie": f"a2flow_session={cookies['a2flow_session'].value}"},
    )
    assert me.status_code == 200
    assert me.json()["data"]["user"]["username"] == "alice"


@pytest.mark.asyncio
async def test_start_unknown_tenant_redirects_unavailable(ctx: Ctx) -> None:
    for params in ({"tenant": "nope"}, {}):
        resp = await ctx.client.get("/api/v1/auth/oidc/start", params=params)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login?sso_error=unavailable"
        assert STATE_COOKIE_NAME not in set_cookies(resp)


@pytest.mark.asyncio
async def test_start_redirects_to_app_base_url_origin(
    ctx: Ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_app_base_url(monkeypatch, "https://a2.example.com")
    resp = await ctx.client.get("/api/v1/auth/oidc/start", params={"tenant": "acme"})
    assert resp.status_code == 302
    assert resp.headers["location"] == (
        "https://a2.example.com/api/v1/auth/oidc/start?tenant=acme&hop=1"
    )
    assert STATE_COOKIE_NAME not in set_cookies(resp)
    assert ctx.fake.requests == []


@pytest.mark.asyncio
async def test_start_refuses_cross_site_navigation(ctx: Ctx) -> None:
    """A page on another site must not be able to start a sign-in (login CSRF)."""
    resp = await ctx.client.get(
        "/api/v1/auth/oidc/start",
        params={"tenant": "acme"},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login?sso_error=unavailable"
    assert STATE_COOKIE_NAME not in set_cookies(resp)
    assert ctx.fake.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("site", ["same-origin", "same-site", "none"])
async def test_start_allows_same_site_and_user_initiated(ctx: Ctx, site: str) -> None:
    resp = await ctx.client.get(
        "/api/v1/auth/oidc/start",
        params={"tenant": "acme"},
        headers={"Sec-Fetch-Site": site},
    )
    assert resp.headers["location"].startswith(f"{ISSUER}/authorize?")
    assert STATE_COOKIE_NAME in set_cookies(resp)


@pytest.mark.asyncio
async def test_start_hops_to_app_base_url_only_once(
    ctx: Ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_app_base_url(monkeypatch, "https://a2.example.com")
    resp = await ctx.client.get(
        "/api/v1/auth/oidc/start", params={"tenant": "acme", "hop": "1"}
    )
    assert resp.status_code == 302
    assert resp.headers["location"].startswith(f"{ISSUER}/authorize?")
    assert STATE_COOKIE_NAME in set_cookies(resp)


@pytest.mark.asyncio
async def test_callback_state_mismatch_is_failed(ctx: Ctx) -> None:
    _, cookie_a, _ = await start(ctx)
    _, _, state_b = await start(ctx)
    resp = await callback(ctx, cookie=cookie_a, code="code-1", state=state_b)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login?sso_error=failed"
    assert "a2flow_session" not in set_cookies(resp)
    assert_state_cleared(resp)
    assert ctx.fake.count("/token") == 0


@pytest.mark.asyncio
async def test_callback_without_cookie_is_failed(ctx: Ctx) -> None:
    resp = await callback(ctx, cookie=None, code="code-1", state="whatever")
    assert resp.headers["location"] == "/login?sso_error=failed"
    assert_state_cleared(resp)


@pytest.mark.asyncio
async def test_callback_idp_error_param_is_failed(ctx: Ctx) -> None:
    _, cookie, state = await start(ctx)
    resp = await callback(ctx, cookie=cookie, error="access_denied", state=state)
    assert resp.headers["location"] == "/login?sso_error=failed"
    assert_state_cleared(resp)


@pytest.mark.asyncio
async def test_unexpected_errors_never_become_a_500(
    ctx: Ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(OidcLoginService, "complete", boom)
    monkeypatch.setattr(OidcLoginService, "start", boom)
    resp = await callback(ctx, cookie="cookie", code="code-1", state="state")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login?sso_error=failed"
    assert_state_cleared(resp)
    resp = await ctx.client.get("/api/v1/auth/oidc/start", params={"tenant": "acme"})
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login?sso_error=unavailable"
