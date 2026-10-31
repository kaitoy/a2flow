"""Tests for the admin-managed tenant settings routes (``/tenant-settings``)."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from models.user import SYSTEM_USER_ID
from tests._engine import make_test_engine
from tests._envelope import assert_err, assert_ok
from tests._seed import seed_users
from tests.conftest import _install_auth_overrides

_PATH = "/api/v1/tenant-settings"


@pytest_asyncio.fixture()
async def settings_client() -> AsyncGenerator[AsyncClient, None]:
    """Client bound to a throwaway database holding the default test tenant."""
    from infrastructure.database import get_session
    from main import app

    engine = await make_test_engine()
    await seed_users(engine, ids=())

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    _install_auth_overrides(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-Id": SYSTEM_USER_ID, "X-User-Roles": "admin"},
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def test_get_returns_defaults(settings_client: AsyncClient) -> None:
    assert assert_ok(await settings_client.get(_PATH)) == {
        "loginMaxFailures": 5,
        "loginLockoutMinutes": 15,
    }


async def test_patch_updates_and_null_keeps(settings_client: AsyncClient) -> None:
    assert assert_ok(
        await settings_client.patch(
            _PATH, json={"loginMaxFailures": 3, "loginLockoutMinutes": 60}
        )
    ) == {"loginMaxFailures": 3, "loginLockoutMinutes": 60}
    assert assert_ok(
        await settings_client.patch(_PATH, json={"loginMaxFailures": None})
    ) == {"loginMaxFailures": 3, "loginLockoutMinutes": 60}


@pytest.mark.parametrize(
    "body",
    [
        {"loginMaxFailures": 0},
        {"loginMaxFailures": 101},
        {"loginLockoutMinutes": 0},
        {"loginLockoutMinutes": 1441},
    ],
)
async def test_patch_rejects_out_of_range(
    settings_client: AsyncClient, body: dict[str, int]
) -> None:
    assert_err(
        await settings_client.patch(_PATH, json=body),
        code="VALIDATION_ERROR",
        status=422,
    )


@pytest.mark.parametrize("role", ["developer", "requester", "approver", ""])
async def test_non_admin_is_forbidden(settings_client: AsyncClient, role: str) -> None:
    headers = {"X-User-Roles": role}
    assert_err(
        await settings_client.get(_PATH, headers=headers), code="FORBIDDEN", status=403
    )
    assert_err(
        await settings_client.patch(
            _PATH, json={"loginMaxFailures": 3}, headers=headers
        ),
        code="FORBIDDEN",
        status=403,
    )


async def test_group_granted_admin_may_edit(settings_client: AsyncClient) -> None:
    assert_ok(
        await settings_client.patch(
            _PATH,
            json={"loginMaxFailures": 7},
            headers={"X-User-Roles": "", "X-User-Group-Roles": "admin"},
        )
    )
