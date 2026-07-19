"""End-to-end tests for the cookie-based authentication and CSRF flow."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from dependencies.auth import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
)
from infrastructure.password import hash_password
from models.auth_session import AuthSession
from models.user import SYSTEM_USER_ID, User
from repositories.auth_session import SqlAuthSessionRepository
from repositories.exceptions import UnauthorizedError
from repositories.tenant import SqlTenantRepository
from repositories.user import SqlUserRepository
from services.auth import AuthService
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_users
from tests.conftest import AUTH_PASSWORD, AUTH_USERNAME


async def _login(client: AsyncClient) -> Any:
    """Log in with the seeded credentials and return the parsed response data."""
    return assert_ok(
        await client.post(
            "/api/v1/auth/login",
            json={
                "username": AUTH_USERNAME,
                "password": AUTH_PASSWORD,
                "tenantSlug": DEFAULT_TEST_TENANT_ID,
            },
        )
    )


@pytest.mark.asyncio
async def test_login_success_sets_cookies(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/api/v1/auth/login",
        json={
            "username": AUTH_USERNAME,
            "password": AUTH_PASSWORD,
            "tenantSlug": DEFAULT_TEST_TENANT_ID,
        },
    )
    data = assert_ok(response)
    assert data["username"] == AUTH_USERNAME
    assert "password" not in data
    assert SESSION_COOKIE_NAME in response.cookies
    assert CSRF_COOKIE_NAME in response.cookies


@pytest.mark.asyncio
async def test_login_wrong_password_is_unauthenticated(
    auth_client: AsyncClient,
) -> None:
    assert_err(
        await auth_client.post(
            "/api/v1/auth/login",
            json={
                "username": AUTH_USERNAME,
                "password": "wrong-password-000",
                "tenantSlug": DEFAULT_TEST_TENANT_ID,
            },
        ),
        code="UNAUTHENTICATED",
        status=401,
    )


@pytest.mark.asyncio
async def test_login_unknown_user_is_unauthenticated(auth_client: AsyncClient) -> None:
    assert_err(
        await auth_client.post(
            "/api/v1/auth/login",
            json={
                "username": "nobody",
                "password": AUTH_PASSWORD,
                "tenantSlug": DEFAULT_TEST_TENANT_ID,
            },
        ),
        code="UNAUTHENTICATED",
        status=401,
    )


@pytest.mark.asyncio
async def test_me_requires_session(auth_client: AsyncClient) -> None:
    assert_err(
        await auth_client.get("/api/v1/auth/me"),
        code="UNAUTHENTICATED",
        status=401,
    )


@pytest.mark.asyncio
async def test_me_returns_current_user_after_login(auth_client: AsyncClient) -> None:
    await _login(auth_client)
    data = assert_ok(await auth_client.get("/api/v1/auth/me"))
    assert data["username"] == AUTH_USERNAME


@pytest.mark.asyncio
async def test_logout_requires_csrf_header(auth_client: AsyncClient) -> None:
    await _login(auth_client)
    # The session cookie is sent automatically, but no X-CSRF-Token header.
    assert_err(
        await auth_client.post("/api/v1/auth/logout"),
        code="CSRF_FAILED",
        status=403,
    )


@pytest.mark.asyncio
async def test_logout_revokes_session(auth_client: AsyncClient) -> None:
    await _login(auth_client)
    csrf = auth_client.cookies.get(CSRF_COOKIE_NAME)
    assert csrf is not None
    assert_ok(
        await auth_client.post("/api/v1/auth/logout", headers={CSRF_HEADER_NAME: csrf})
    )
    # The session is gone, so /auth/me is rejected even if a stale cookie lingers.
    assert_err(
        await auth_client.get("/api/v1/auth/me"),
        code="UNAUTHENTICATED",
        status=401,
    )


@pytest.mark.asyncio
async def test_invalid_session_clears_auth_cookies(auth_client: AsyncClient) -> None:
    """A 401 from a protected route must expire the stale session and CSRF cookies.

    Otherwise the still-present session cookie keeps the edge middleware treating
    the visitor as logged in, bouncing them back to a protected route instead of
    rendering ``/login``.
    """
    auth_client.cookies.set(SESSION_COOKIE_NAME, "bogus")
    response = await auth_client.get("/api/v1/auth/me")
    assert_err(response, code="UNAUTHENTICATED", status=401)

    set_cookies = response.headers.get_list("set-cookie")
    for name in (SESSION_COOKIE_NAME, CSRF_COOKIE_NAME):
        cleared = next((c for c in set_cookies if c.startswith(f"{name}=")), None)
        assert cleared is not None, f"{name} was not cleared on 401"
        assert "Max-Age=0" in cleared or "max-age=0" in cleared.lower()


@pytest_asyncio.fixture()
async def auth_service_engine() -> AsyncGenerator[Any, None]:
    """Provide an in-memory engine seeded with the system user for service tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await seed_users(engine, ids=())
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_authenticate_expires_idle_session(
    auth_service_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SESSION_IDLE_TIMEOUT_SECONDS", "60")
    async with AsyncSession(auth_service_engine) as session:
        session.add(
            User(
                username="idle",
                first_name="Idle",
                last_name="User",
                password=hash_password(AUTH_PASSWORD),
                email="idle@test.local",
                enabled=True,
                tenant_id=DEFAULT_TEST_TENANT_ID,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await session.commit()

    async with AsyncSession(auth_service_engine, expire_on_commit=False) as session:
        service = AuthService(
            SqlUserRepository(session),
            SqlAuthSessionRepository(session),
            SqlTenantRepository(session),
        )
        result = await service.login(
            "idle", AUTH_PASSWORD, tenant_slug=DEFAULT_TEST_TENANT_ID
        )
        # A fresh token authenticates fine.
        assert (await service.authenticate(result.session_token)).username == "idle"

        # Backdate the session beyond the idle window.
        stmt = select(AuthSession).where(col(AuthSession.user_id) == result.user.id)
        auth_session = (await session.exec(stmt)).one()
        auth_session.last_active_at = datetime.now(UTC) - timedelta(seconds=120)
        session.add(auth_session)
        await session.commit()

        with pytest.raises(UnauthorizedError):
            await service.authenticate(result.session_token)
        # The expired session is deleted on rejection.
        assert (await session.exec(stmt)).first() is None
