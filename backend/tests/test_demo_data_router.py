"""Tests for the demo-data routes (``/demo-data``).

What a load or clear writes is covered by ``tests/test_demo_data.py``; these
check the HTTP surface: the ``admin`` gate, that a route acts on the caller's
tenant only, and that a load hands each new demo skill to the clone job.
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from models.user import SYSTEM_USER_ID
from tests._engine import make_test_engine
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users
from tests.conftest import _install_auth_overrides

_PATH = "/api/v1/demo-data"

#: A second tenant, to show a route never reaches past the caller's own.
_OTHER_TENANT_ID = "tenant-other"


def _as(
    tenant_id: str = DEFAULT_TEST_TENANT_ID, roles: str = "admin"
) -> dict[str, str]:
    """Return the test headers acting as a user of ``tenant_id`` holding ``roles``."""
    return {"X-User-Roles": roles, "X-User-Tenant-Id": tenant_id}


@pytest_asyncio.fixture()
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Throwaway database holding two tenants and the system user."""
    mem_engine = await make_test_engine()
    await seed_users(mem_engine, ids=())
    await seed_tenant(mem_engine)
    await seed_tenant(mem_engine, _OTHER_TENANT_ID)
    try:
        yield mem_engine
    finally:
        await mem_engine.dispose()


@pytest_asyncio.fixture()
async def sync_job() -> AsyncMock:
    """Stand-in for the background clone job, so no repository is cloned."""
    return AsyncMock()


@pytest_asyncio.fixture()
async def client(
    engine: AsyncEngine, sync_job: AsyncMock
) -> AsyncGenerator[AsyncClient, None]:
    """Client bound to :func:`engine`, with the clone job replaced."""
    from dependencies.service import get_skill_sync_job
    from infrastructure.database import get_session
    from main import app

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_skill_sync_job] = lambda: sync_job
    _install_auth_overrides(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-Id": SYSTEM_USER_ID},
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


async def test_load_then_clear(client: AsyncClient, sync_job: AsyncMock) -> None:
    assert assert_ok(await client.get(_PATH, headers=_as())) == {
        "loaded": False,
        "keptCount": 0,
    }

    assert assert_ok(await client.post(_PATH, headers=_as()))["loaded"] is True
    assert sync_job.await_count == 3
    assert assert_ok(await client.get(_PATH, headers=_as()))["loaded"] is True

    assert assert_ok(await client.delete(_PATH, headers=_as())) == {
        "loaded": False,
        "keptCount": 0,
    }


async def test_loading_again_clones_nothing_new(
    client: AsyncClient, sync_job: AsyncMock
) -> None:
    assert_ok(await client.post(_PATH, headers=_as()))
    sync_job.reset_mock()
    assert_ok(await client.post(_PATH, headers=_as()))
    sync_job.assert_not_awaited()


async def test_routes_act_on_the_callers_tenant_only(client: AsyncClient) -> None:
    assert_ok(await client.post(_PATH, headers=_as()))

    other = _as(_OTHER_TENANT_ID)
    assert assert_ok(await client.get(_PATH, headers=other))["loaded"] is False
    assert_ok(await client.delete(_PATH, headers=other))
    assert assert_ok(await client.get(_PATH, headers=_as()))["loaded"] is True


async def test_non_admins_are_refused(client: AsyncClient) -> None:
    developer = _as(roles="developer")
    assert_err(await client.get(_PATH, headers=developer), "FORBIDDEN", 403)
    assert_err(await client.post(_PATH, headers=developer), "FORBIDDEN", 403)
    assert_err(await client.delete(_PATH, headers=developer), "FORBIDDEN", 403)
