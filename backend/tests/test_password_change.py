"""Tests for self-service password change and the must-change-password gate."""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, func, select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from dependencies.auth import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from infrastructure.password import hash_password
from models.login_failure import LoginFailure
from models.user import SYSTEM_USER_ID, Role, User, UserCreate, UserUpdate
from repositories.auth_session import SqlAuthSessionRepository
from repositories.effective_roles import SqlEffectiveRoleRepository
from repositories.exceptions import ForbiddenError, UnauthorizedError
from repositories.login_failure import SqlLoginFailureRepository
from repositories.tenant import SqlTenantRepository
from repositories.user import SqlUserRepository
from services.auth import AuthService
from services.user import UserService
from tests._engine import make_test_engine
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_users
from tests.conftest import AUTH_PASSWORD, AUTH_USERNAME

NEW_PASSWORD = "a-brand-new-password"


async def _login(client: AsyncClient, password: str = AUTH_PASSWORD) -> Any:
    """Sign the seeded user in and return the response."""
    return await client.post(
        "/api/v1/auth/login",
        json={
            "username": AUTH_USERNAME,
            "password": password,
            "tenantName": DEFAULT_TEST_TENANT_ID,
        },
    )


async def _change(
    client: AsyncClient,
    current: str,
    new: str,
    *,
    headers: dict[str, str] | None = None,
) -> Any:
    """Call ``POST /auth/password`` with the session's CSRF token."""
    csrf = client.cookies.get(CSRF_COOKIE_NAME) or ""
    return await client.post(
        "/api/v1/auth/password",
        json={"currentPassword": current, "newPassword": new},
        headers={CSRF_HEADER_NAME: csrf, **(headers or {})},
    )


async def _set_seeded_user(engine: AsyncEngine, **values: Any) -> None:
    """Write columns of the seeded login user directly."""
    async with AsyncSession(engine) as session:
        await session.exec(
            update(User).where(col(User.username) == AUTH_USERNAME).values(**values)
        )
        await session.commit()


@pytest.mark.asyncio
async def test_change_password_replaces_it_and_keeps_the_session(
    auth_client: AsyncClient,
) -> None:
    assert_ok(await _login(auth_client))
    data = assert_ok(await _change(auth_client, AUTH_PASSWORD, NEW_PASSWORD))
    assert data["mustChangePassword"] is False
    assert data["hasPassword"] is True
    # The browser that changed it stays signed in.
    assert_ok(await auth_client.get("/api/v1/auth/me"))
    assert_err(await _login(auth_client), code="UNAUTHENTICATED", status=401)
    assert_ok(await _login(auth_client, NEW_PASSWORD))


@pytest.mark.asyncio
async def test_wrong_current_password_is_refused_and_counted(
    auth_client_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = auth_client_env
    assert_ok(await _login(client))
    assert_err(
        await _change(client, "not-my-password", NEW_PASSWORD),
        code="INVALID_CURRENT_PASSWORD",
        status=422,
    )
    async with AsyncSession(engine) as session:
        count = (
            await session.exec(select(func.count()).select_from(LoginFailure))
        ).one()
    # Counted against the same account key sign-in uses.
    assert count == 1


@pytest.mark.asyncio
async def test_same_password_is_refused(auth_client: AsyncClient) -> None:
    assert_ok(await _login(auth_client))
    assert_err(
        await _change(auth_client, AUTH_PASSWORD, AUTH_PASSWORD),
        code="PASSWORD_UNCHANGED",
        status=422,
    )


@pytest.mark.asyncio
async def test_short_new_password_is_refused(auth_client: AsyncClient) -> None:
    assert_ok(await _login(auth_client))
    assert_err(
        await _change(auth_client, AUTH_PASSWORD, "short"),
        code="VALIDATION_ERROR",
        status=422,
    )


@pytest.mark.asyncio
async def test_change_password_requires_csrf(auth_client: AsyncClient) -> None:
    assert_ok(await _login(auth_client))
    assert_err(
        await auth_client.post(
            "/api/v1/auth/password",
            json={"currentPassword": AUTH_PASSWORD, "newPassword": NEW_PASSWORD},
        ),
        code="CSRF_FAILED",
        status=403,
    )


@pytest.mark.asyncio
async def test_flagged_user_is_held_at_the_password_change(
    auth_client_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = auth_client_env
    await _set_seeded_user(engine, must_change_password=True)
    assert_ok(await _login(client))

    assert_err(
        await client.get("/api/v1/tags"),
        code="PASSWORD_CHANGE_REQUIRED",
        status=403,
    )
    # /auth stays open, so the client can learn why and act on it.
    me = assert_ok(await client.get("/api/v1/auth/me"))
    assert me["user"]["mustChangePassword"] is True

    assert_ok(await _change(client, AUTH_PASSWORD, NEW_PASSWORD))
    assert_ok(await client.get("/api/v1/tags"))


@pytest.mark.asyncio
async def test_change_password_is_refused_while_impersonating(
    auth_client_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = auth_client_env
    await _set_seeded_user(engine, roles=[Role.admin.value])
    async with AsyncSession(engine, expire_on_commit=False) as session:
        target = User(
            username="target",
            first_name="Target",
            last_name="User",
            password=hash_password(AUTH_PASSWORD),
            email="target@test.local",
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        session.add(target)
        await session.commit()
    assert_ok(await _login(client))
    csrf = client.cookies.get(CSRF_COOKIE_NAME) or ""
    assert_ok(
        await client.post(
            "/api/v1/auth/impersonate",
            json={"targetUserId": target.id},
            headers={CSRF_HEADER_NAME: csrf},
        )
    )
    assert_err(
        await _change(
            client,
            AUTH_PASSWORD,
            NEW_PASSWORD,
            headers={"X-Impersonate-User-Id": target.id},
        ),
        code="FORBIDDEN",
        status=403,
    )


@pytest_asyncio.fixture()
async def engine() -> AsyncGenerator[Any, None]:
    """Provide a throwaway engine seeded with the system user."""
    eng = await make_test_engine()
    await seed_users(eng, ids=())
    try:
        yield eng
    finally:
        await eng.dispose()


def _user(
    name: str, *, roles: list[str] | None = None, password: str | None = AUTH_PASSWORD
) -> User:
    """Build an enabled user in the default test tenant."""
    return User(
        username=name,
        first_name=name,
        last_name="User",
        password=hash_password(password) if password else None,
        email=f"{name}@test.local",
        tenant_id=DEFAULT_TEST_TENANT_ID,
        roles=roles or [],
        created_by=SYSTEM_USER_ID,
        updated_by=SYSTEM_USER_ID,
    )


def _services(session: AsyncSession) -> tuple[AuthService, UserService]:
    """Build the auth and user services over one session."""
    sessions = SqlAuthSessionRepository(session)
    auth = AuthService(
        SqlUserRepository(session),
        sessions,
        SqlTenantRepository(session),
        SqlLoginFailureRepository(session),
    )
    users = UserService(
        SqlUserRepository(session), SqlEffectiveRoleRepository(session), sessions
    )
    return auth, users


@pytest.mark.asyncio
async def test_change_password_revokes_only_the_other_sessions(engine: Any) -> None:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(_user("me"))
        await session.commit()
        auth, _ = _services(session)
        here = await auth.login("me", AUTH_PASSWORD, tenant_name=DEFAULT_TEST_TENANT_ID)
        elsewhere = await auth.login(
            "me", AUTH_PASSWORD, tenant_name=DEFAULT_TEST_TENANT_ID
        )

        await auth.change_password(
            here.user, here.session_token, AUTH_PASSWORD, NEW_PASSWORD
        )

        assert (await auth.authenticate(here.session_token)).username == "me"
        with pytest.raises(UnauthorizedError):
            await auth.authenticate(elsewhere.session_token)


@pytest.mark.asyncio
async def test_sso_only_user_cannot_change_a_password(engine: Any) -> None:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        sso = _user("sso", password=None)
        session.add(sso)
        await session.commit()
        auth, _ = _services(session)
        with pytest.raises(ForbiddenError):
            await auth.change_password(sso, "token", "anything", NEW_PASSWORD)


@pytest.mark.asyncio
async def test_admin_chosen_passwords_must_be_changed(engine: Any) -> None:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        admin, other = _user("boss", roles=[Role.admin.value]), _user("other")
        session.add_all([admin, other])
        await session.commit()
        _, users = _services(session)
        roles = [Role.admin.value]

        created = await users.create(
            UserCreate(
                username="fresh",
                first_name="Fresh",
                last_name="User",
                password=NEW_PASSWORD,
                email="fresh@example.com",
            ),
            acting_user=admin,
        )
        assert created.must_change_password is True

        reset = await users.update(
            other.id,
            UserUpdate(password=NEW_PASSWORD),
            acting_user=admin,
            acting_roles=roles,
        )
        assert reset.must_change_password is True

        # An admin resetting their own password already knows it.
        own = await users.update(
            admin.id,
            UserUpdate(password=NEW_PASSWORD),
            acting_user=admin,
            acting_roles=roles,
        )
        assert own.must_change_password is False

        # Editing anything but the password leaves the flag alone.
        renamed = await users.update(
            other.id,
            UserUpdate(first_name="Renamed"),
            acting_user=admin,
            acting_roles=roles,
        )
        assert renamed.must_change_password is True
