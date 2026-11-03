"""End-to-end tests for the cookie-based authentication and CSRF flow."""

import threading
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from dependencies.auth import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
)
from infrastructure.auth_tokens import hash_token
from infrastructure.password import hash_password
from models.auth_session import AuthSession
from models.login_failure import LoginFailure
from models.tenant import Tenant
from models.user import SYSTEM_USER_ID, Role, User, UserUpdate
from repositories.auth_session import SqlAuthSessionRepository
from repositories.effective_roles import SqlEffectiveRoleRepository
from repositories.exceptions import UnauthorizedError
from repositories.login_failure import SqlLoginFailureRepository
from repositories.tenant import SqlTenantRepository
from repositories.user import SqlUserRepository
from services.auth import AuthService
from services.user import UserService
from tests._engine import make_test_engine
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
                "tenantName": DEFAULT_TEST_TENANT_ID,
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
            "tenantName": DEFAULT_TEST_TENANT_ID,
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
                "tenantName": DEFAULT_TEST_TENANT_ID,
            },
        ),
        code="UNAUTHENTICATED",
        status=401,
    )


@pytest.mark.asyncio
async def test_login_overlong_password_is_unauthenticated_not_500(
    auth_client: AsyncClient,
) -> None:
    # bcrypt refuses passwords over 72 bytes; a 500 here would reveal that the
    # account exists, since unknown accounts never reach bcrypt.
    assert_err(
        await auth_client.post(
            "/api/v1/auth/login",
            json={
                "username": AUTH_USERNAME,
                "password": "A" * 100,
                "tenantName": DEFAULT_TEST_TENANT_ID,
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
                "tenantName": DEFAULT_TEST_TENANT_ID,
            },
        ),
        code="UNAUTHENTICATED",
        status=401,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("tenant_name", [DEFAULT_TEST_TENANT_ID, "no-such-tenant"])
async def test_login_rejection_still_runs_bcrypt(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tenant_name: str
) -> None:
    """An unknown user or tenant pays a bcrypt check, so timing hides which exist."""
    checks: list[bytes] = []
    real_checkpw = bcrypt.checkpw

    def _spy(plain: bytes, hashed: bytes) -> bool:
        checks.append(plain)
        return bool(real_checkpw(plain, hashed))

    monkeypatch.setattr("infrastructure.password.bcrypt.checkpw", _spy)
    assert_err(
        await auth_client.post(
            "/api/v1/auth/login",
            json={
                "username": "nobody",
                "password": AUTH_PASSWORD,
                "tenantName": tenant_name,
            },
        ),
        code="UNAUTHENTICATED",
        status=401,
    )
    assert checks == [AUTH_PASSWORD.encode()]


@pytest.mark.asyncio
@pytest.mark.parametrize("username", [AUTH_USERNAME, "nobody"])
async def test_login_runs_bcrypt_off_the_event_loop(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, username: str
) -> None:
    """A bcrypt round on the loop would stall every other request and stream."""
    loop_thread = threading.get_ident()
    threads: list[int] = []
    real_checkpw = bcrypt.checkpw

    def _spy(plain: bytes, hashed: bytes) -> bool:
        threads.append(threading.get_ident())
        return bool(real_checkpw(plain, hashed))

    monkeypatch.setattr("infrastructure.password.bcrypt.checkpw", _spy)
    await _attempt(auth_client, username, AUTH_PASSWORD)
    assert threads
    assert loop_thread not in threads


async def _attempt(client: AsyncClient, username: str, password: str) -> Any:
    """Post one login attempt against the default test tenant."""
    return await client.post(
        "/api/v1/auth/login",
        json={
            "username": username,
            "password": password,
            "tenantName": DEFAULT_TEST_TENANT_ID,
        },
    )


@pytest.mark.asyncio
async def test_login_locks_account_after_repeated_failures(
    auth_client: AsyncClient,
) -> None:
    """Five wrong passwords lock the account, even against the right one."""
    for _ in range(5):
        assert_err(
            await _attempt(auth_client, AUTH_USERNAME, "wrong"),
            code="UNAUTHENTICATED",
            status=401,
        )
    err = assert_err(
        await _attempt(auth_client, AUTH_USERNAME, AUTH_PASSWORD),
        code="TOO_MANY_LOGIN_ATTEMPTS",
        status=429,
    )
    assert "15 minutes" in err["message"]


@pytest.mark.asyncio
async def test_login_locks_unknown_username_the_same_way(
    auth_client: AsyncClient,
) -> None:
    """A nonexistent account locks after the same count, hiding existence."""
    for _ in range(5):
        await _attempt(auth_client, "nobody", "wrong")
    assert_err(
        await _attempt(auth_client, "nobody", "wrong"),
        code="TOO_MANY_LOGIN_ATTEMPTS",
        status=429,
    )


@pytest.mark.asyncio
async def test_login_success_resets_account_failures(
    auth_client: AsyncClient,
) -> None:
    """A successful login clears the account's count."""
    for _ in range(4):
        await _attempt(auth_client, AUTH_USERNAME, "wrong")
    assert_ok(await _attempt(auth_client, AUTH_USERNAME, AUTH_PASSWORD))
    for _ in range(4):
        await _attempt(auth_client, AUTH_USERNAME, "wrong")
    assert_ok(await _attempt(auth_client, AUTH_USERNAME, AUTH_PASSWORD))


@pytest.mark.asyncio
async def test_login_lockout_is_per_account(auth_client: AsyncClient) -> None:
    """Locking other accounts from the same client leaves this one usable."""
    for i in range(20):
        await _attempt(auth_client, f"spray-{i % 4}", "wrong")
    assert_ok(await _attempt(auth_client, AUTH_USERNAME, AUTH_PASSWORD))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("max_failures", "lockout_minutes", "age_minutes", "status"),
    [
        # Two old failures reach a limit of 2 only while the window covers them.
        (2, 60, 30, 429),
        (2, 15, 30, 401),
        # The default limit of 5 is not reached by two failures.
        (5, 60, 30, 401),
    ],
)
async def test_login_uses_the_tenants_limit_and_lockout(
    auth_service_engine: Any,
    max_failures: int,
    lockout_minutes: int,
    age_minutes: int,
    status: int,
) -> None:
    """The account limit and lockout come from the submitted tenant."""
    failed_at = datetime.now(UTC) - timedelta(minutes=age_minutes)
    async with AsyncSession(auth_service_engine, expire_on_commit=False) as session:
        tenant = await session.get(Tenant, DEFAULT_TEST_TENANT_ID)
        assert tenant is not None
        tenant.login_max_failures = max_failures
        tenant.login_lockout_minutes = lockout_minutes
        session.add(tenant)
        session.add_all(
            LoginFailure(key=f"{tenant.name}/someone", failed_at=failed_at)
            for _ in range(2)
        )
        await session.commit()
        service = AuthService(
            SqlUserRepository(session),
            SqlAuthSessionRepository(session),
            SqlTenantRepository(session),
            SqlLoginFailureRepository(session),
        )
        with pytest.raises(Exception) as exc_info:
            await service.login("someone", "wrong", tenant_name=tenant.name)
    assert getattr(exc_info.value, "http_status", None) == status


@pytest.mark.asyncio
@pytest.mark.parametrize(("age_minutes", "status"), [(1, 429), (16, 401)])
async def test_login_failures_expire_after_window(
    auth_service_engine: Any, age_minutes: int, status: int
) -> None:
    """Failures older than the window no longer count."""
    failed_at = datetime.now(UTC) - timedelta(minutes=age_minutes)
    async with AsyncSession(auth_service_engine, expire_on_commit=False) as session:
        session.add_all(
            LoginFailure(key=f"{DEFAULT_TEST_TENANT_ID}/old", failed_at=failed_at)
            for _ in range(5)
        )
        await session.commit()
        service = AuthService(
            SqlUserRepository(session),
            SqlAuthSessionRepository(session),
            SqlTenantRepository(session),
            SqlLoginFailureRepository(session),
        )
        with pytest.raises(Exception) as exc_info:
            await service.login("old", "wrong", tenant_name=DEFAULT_TEST_TENANT_ID)
    assert getattr(exc_info.value, "http_status", None) == status


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
    assert data["user"]["username"] == AUTH_USERNAME
    assert data["impersonatedBy"] is None


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
    response = await auth_client.post(
        "/api/v1/auth/logout", headers={CSRF_HEADER_NAME: csrf}
    )
    assert_ok(response)
    # Cached API responses (e.g. the design-chat history) must not outlive it.
    assert response.headers["clear-site-data"] == '"cache"'
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
    """Provide a throwaway engine seeded with the system user for service tests."""
    engine = await make_test_engine()
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
            SqlLoginFailureRepository(session),
        )
        result = await service.login(
            "idle", AUTH_PASSWORD, tenant_name=DEFAULT_TEST_TENANT_ID
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


@pytest.mark.asyncio
async def test_login_prunes_sessions_past_the_idle_timeout(
    auth_service_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An abandoned session is never presented again, so a later login deletes it."""
    monkeypatch.setenv("SESSION_IDLE_TIMEOUT_SECONDS", "60")
    async with AsyncSession(auth_service_engine) as session:
        session.add(
            User(
                username="pruner",
                first_name="Prune",
                last_name="User",
                password=hash_password(AUTH_PASSWORD),
                email="pruner@test.local",
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
            SqlLoginFailureRepository(session),
        )
        abandoned = await service.login(
            "pruner", AUTH_PASSWORD, tenant_name=DEFAULT_TEST_TENANT_ID
        )
        alive = await service.login(
            "pruner", AUTH_PASSWORD, tenant_name=DEFAULT_TEST_TENANT_ID
        )
        stmt = select(AuthSession).where(
            col(AuthSession.token_hash) == hash_token(abandoned.session_token)
        )
        stale = (await session.exec(stmt)).one()
        stale.last_active_at = datetime.now(UTC) - timedelta(seconds=120)
        session.add(stale)
        await session.commit()

        latest = await service.login(
            "pruner", AUTH_PASSWORD, tenant_name=DEFAULT_TEST_TENANT_ID
        )

        rows = (await session.exec(select(AuthSession.token_hash))).all()
        assert hash_token(abandoned.session_token) not in rows
        assert hash_token(alive.session_token) in rows
        assert hash_token(latest.session_token) in rows


@pytest.mark.asyncio
async def test_authenticate_touches_the_session_only_once_it_is_stale(
    auth_service_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A recently refreshed session is not written again on every request.

    Polling would otherwise turn every authenticated read into an UPDATE on
    the primary. With a 60 s idle timeout the refresh interval is 30 s.
    """
    monkeypatch.setenv("SESSION_IDLE_TIMEOUT_SECONDS", "60")
    async with AsyncSession(auth_service_engine, expire_on_commit=False) as session:
        session.add(
            User(
                username="poller",
                first_name="Poller",
                last_name="User",
                password=hash_password(AUTH_PASSWORD),
                email="poller@test.local",
                enabled=True,
                tenant_id=DEFAULT_TEST_TENANT_ID,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await session.commit()
        service = AuthService(
            SqlUserRepository(session),
            SqlAuthSessionRepository(session),
            SqlTenantRepository(session),
            SqlLoginFailureRepository(session),
        )
        result = await service.login(
            "poller", AUTH_PASSWORD, tenant_name=DEFAULT_TEST_TENANT_ID
        )
        stmt = select(AuthSession).where(col(AuthSession.user_id) == result.user.id)

        async def _slid_by(backdate_seconds: int) -> timedelta:
            """Backdate the session, authenticate, and return how far it slid."""
            auth_session = (await session.exec(stmt)).one()
            backdated = datetime.now(UTC) - timedelta(seconds=backdate_seconds)
            auth_session.last_active_at = backdated
            session.add(auth_session)
            await session.commit()
            await service.authenticate(result.session_token)
            session.expunge_all()
            stored = (await session.exec(stmt)).one().last_active_at
            return stored.replace(tzinfo=stored.tzinfo or UTC) - backdated

        # Refreshed 10 s ago: left alone.
        assert await _slid_by(10) == timedelta(0)
        # Refreshed 40 s ago: past the interval, so it slides forward.
        assert await _slid_by(40) > timedelta(seconds=30)


@pytest.mark.asyncio
async def test_password_reset_revokes_the_targets_sessions(
    auth_service_engine: Any,
) -> None:
    """An admin's password reset signs out every browser holding the old login."""
    async with AsyncSession(auth_service_engine, expire_on_commit=False) as session:
        target, admin = (
            User(
                username=name,
                first_name=name,
                last_name="User",
                password=hash_password(AUTH_PASSWORD),
                email=f"{name}@test.local",
                enabled=True,
                tenant_id=DEFAULT_TEST_TENANT_ID,
                roles=roles,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
            for name, roles in (("target", []), ("boss", [Role.admin.value]))
        )
        session.add_all([target, admin])
        await session.commit()

        sessions = SqlAuthSessionRepository(session)
        auth = AuthService(
            SqlUserRepository(session),
            sessions,
            SqlTenantRepository(session),
            SqlLoginFailureRepository(session),
        )
        stolen = await auth.login(
            "target", AUTH_PASSWORD, tenant_name=DEFAULT_TEST_TENANT_ID
        )
        kept = await auth.login(
            "boss", AUTH_PASSWORD, tenant_name=DEFAULT_TEST_TENANT_ID
        )

        users = UserService(
            SqlUserRepository(session), SqlEffectiveRoleRepository(session), sessions
        )
        await users.update(
            target.id,
            UserUpdate(password="a-brand-new-password"),
            acting_user=admin,
            acting_roles=[Role.admin.value],
        )

        with pytest.raises(UnauthorizedError):
            await auth.authenticate(stolen.session_token)
        assert (await auth.authenticate(kept.session_token)).username == "boss"


@pytest.mark.asyncio
async def test_login_rejects_disabled_tenant(auth_service_engine: Any) -> None:
    async with AsyncSession(auth_service_engine) as session:
        session.add(
            User(
                username="tenantoff",
                first_name="Tenant",
                last_name="Off",
                password=hash_password(AUTH_PASSWORD),
                email="tenantoff@test.local",
                enabled=True,
                tenant_id=DEFAULT_TEST_TENANT_ID,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        tenant = await session.get(Tenant, DEFAULT_TEST_TENANT_ID)
        assert tenant is not None
        tenant.enabled = False
        session.add(tenant)
        await session.commit()

    async with AsyncSession(auth_service_engine, expire_on_commit=False) as session:
        service = AuthService(
            SqlUserRepository(session),
            SqlAuthSessionRepository(session),
            SqlTenantRepository(session),
            SqlLoginFailureRepository(session),
        )
        with pytest.raises(UnauthorizedError):
            await service.login(
                "tenantoff", AUTH_PASSWORD, tenant_name=DEFAULT_TEST_TENANT_ID
            )


@pytest.mark.asyncio
async def test_authenticate_rejects_when_tenant_disabled_mid_session(
    auth_service_engine: Any,
) -> None:
    async with AsyncSession(auth_service_engine) as session:
        session.add(
            User(
                username="tenantuser",
                first_name="Tenant",
                last_name="User",
                password=hash_password(AUTH_PASSWORD),
                email="tenantuser@test.local",
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
            SqlLoginFailureRepository(session),
        )
        result = await service.login(
            "tenantuser", AUTH_PASSWORD, tenant_name=DEFAULT_TEST_TENANT_ID
        )
        assert (
            await service.authenticate(result.session_token)
        ).username == "tenantuser"

        tenant = await session.get(Tenant, DEFAULT_TEST_TENANT_ID)
        assert tenant is not None
        tenant.enabled = False
        session.add(tenant)
        await session.commit()

        with pytest.raises(UnauthorizedError):
            await service.authenticate(result.session_token)
        # Rejected session is deleted, matching the disabled-user path.
        stmt = select(AuthSession).where(col(AuthSession.user_id) == result.user.id)
        assert (await session.exec(stmt)).first() is None
