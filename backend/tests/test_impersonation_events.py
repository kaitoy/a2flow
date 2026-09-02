"""Tests for the admin-only ``/impersonation-events`` List/Get API.

Rows are written by the impersonation flow, so every record here is inserted
directly through
:class:`repositories.impersonation_event.SqlImpersonationEventRepository`.

The load-bearing case is
``test_a_platform_scoped_actor_is_visible_to_the_targets_tenant_admin``: this
table has no ``tenant_id`` of its own, so rows are scoped by the *impersonated*
user's tenant. Scoping on the actor instead would hide exactly the sessions a
tenant most needs to see -- a platform-scoped super_admin carries no tenant at
all.
"""

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from dependencies.auth import ALL_TENANTS_SENTINEL, TENANT_HEADER_NAME
from models.user import SYSTEM_USER_ID, Role
from repositories.impersonation_event import SqlImpersonationEventRepository
from tests._engine import make_test_engine
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users
from tests.conftest import _install_auth_overrides

_PATH = "/api/v1/impersonation-events"

#: A second tenant used by the isolation tests.
OTHER_TENANT_ID = "tenant-other"

#: Headers selecting a plain (non-super-admin) admin in the default tenant.
ADMIN: dict[str, str] = {"X-User-Id": "alice", "X-User-Roles": "admin"}

#: Headers selecting a role-less user.
NOBODY: dict[str, str] = {"X-User-Id": "bob", "X-User-Roles": ""}

#: Headers selecting a platform-scoped super_admin browsing every tenant.
ALL_TENANTS: dict[str, str] = {
    "X-User-Id": "carol",
    "X-User-Roles": "super_admin",
    "X-User-Tenant-Id": "",
    TENANT_HEADER_NAME: ALL_TENANTS_SENTINEL,
}

#: Impersonation target belonging to the default tenant.
TARGET_HERE = "alice"

#: Impersonation target belonging to ``OTHER_TENANT_ID``.
TARGET_THERE = "dave"

#: A platform-scoped super_admin acting as someone. Carries no ``tenant_id``,
#: which is why rows are scoped by the target rather than by the actor.
PLATFORM_ACTOR = "root"


@pytest_asyncio.fixture()
async def event_env() -> AsyncGenerator[tuple[AsyncClient, AsyncEngine], None]:
    """Yield an API client (default caller: super_admin in the default tenant) plus its engine."""
    from infrastructure.database import get_session
    from main import app

    mem_engine = await make_test_engine()
    await seed_users(mem_engine)
    await seed_tenant(mem_engine, OTHER_TENANT_ID)
    await seed_users(mem_engine, [TARGET_THERE], tenant_id=OTHER_TENANT_ID)
    await seed_users(mem_engine, [PLATFORM_ACTOR], roles=[Role.super_admin])

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    _install_auth_overrides(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-Id": SYSTEM_USER_ID},
        ) as ac:
            yield ac, mem_engine
    finally:
        app.dependency_overrides.clear()
        await mem_engine.dispose()


async def _record(
    engine: AsyncEngine,
    *,
    impersonator_id: str = "owner",
    target_user_id: str = TARGET_HERE,
    closed: bool = False,
) -> str:
    """Insert one impersonation event directly and return its id."""
    async with AsyncSession(engine) as session:
        repo = SqlImpersonationEventRepository(session)
        event = await repo.create(
            impersonator_id=impersonator_id, target_user_id=target_user_id
        )
        event_id = str(event.id)
        if closed:
            await repo.close_open_for_actor(impersonator_id)
        return event_id


# ---------- authorization ----------


async def test_super_admin_can_list(
    event_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = event_env
    event_id = await _record(engine)
    rows = assert_ok(await client.get(_PATH))
    assert [row["id"] for row in rows] == [event_id]


async def test_plain_admin_can_list(event_env: tuple[AsyncClient, AsyncEngine]) -> None:
    client, engine = event_env
    event_id = await _record(engine)
    rows = assert_ok(await client.get(_PATH, headers=ADMIN))
    assert [row["id"] for row in rows] == [event_id]


async def test_plain_admin_can_get(event_env: tuple[AsyncClient, AsyncEngine]) -> None:
    client, engine = event_env
    event_id = await _record(engine)
    body = assert_ok(await client.get(f"{_PATH}/{event_id}", headers=ADMIN))
    assert body["id"] == event_id
    assert body["impersonatorId"] == "owner"
    assert body["targetUserId"] == TARGET_HERE
    assert body["targetTenantId"] == DEFAULT_TEST_TENANT_ID
    assert body["endedAt"] is None
    assert body["startedAt"].endswith("Z")


async def test_role_less_user_is_forbidden(
    event_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = event_env
    assert_err(await client.get(_PATH, headers=NOBODY), code="FORBIDDEN", status=403)


async def test_list_is_forbidden_for_a_platform_scoped_caller_without_a_tenant_header(
    event_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = event_env
    assert_err(
        await client.get(_PATH, headers={"X-User-Tenant-Id": ""}),
        code="FORBIDDEN",
        status=403,
    )


# ---------- read-only surface ----------


async def test_there_is_no_write_route(
    event_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """An audit record an admin could edit or delete would not be evidence."""
    client, engine = event_env
    event_id = await _record(engine)
    assert (await client.post(_PATH, json={})).status_code == 405
    assert (await client.patch(f"{_PATH}/{event_id}", json={})).status_code == 405
    assert (await client.delete(f"{_PATH}/{event_id}")).status_code == 405


# ---------- tenant scoping (by the impersonated user) ----------


async def test_list_is_scoped_by_the_targets_tenant(
    event_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = event_env
    mine = await _record(engine, target_user_id=TARGET_HERE)
    await _record(engine, impersonator_id="tester", target_user_id=TARGET_THERE)
    rows = assert_ok(await client.get(_PATH, headers=ADMIN))
    assert [row["id"] for row in rows] == [mine]


async def test_a_platform_scoped_actor_is_visible_to_the_targets_tenant_admin(
    event_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """The actor carries no tenant, so scoping on the actor would hide this row
    from every tenant -- exactly the session an admin most needs to see."""
    client, engine = event_env
    event_id = await _record(
        engine, impersonator_id=PLATFORM_ACTOR, target_user_id=TARGET_HERE
    )
    rows = assert_ok(await client.get(_PATH, headers=ADMIN))
    assert [row["id"] for row in rows] == [event_id]


async def test_get_404s_across_tenants(
    event_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = event_env
    other = await _record(engine, impersonator_id="tester", target_user_id=TARGET_THERE)
    assert_err(
        await client.get(f"{_PATH}/{other}", headers=ADMIN),
        code="NOT_FOUND",
        status=404,
    )


async def test_get_404s_for_an_unknown_id(
    event_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = event_env
    assert_err(await client.get(f"{_PATH}/nope"), code="NOT_FOUND", status=404)


async def test_all_tenants_selection_spans_every_tenant(
    event_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = event_env
    await _record(engine, target_user_id=TARGET_HERE)
    await _record(engine, impersonator_id="tester", target_user_id=TARGET_THERE)
    rows = assert_ok(await client.get(_PATH, headers=ALL_TENANTS))
    assert {row["targetTenantId"] for row in rows} == {
        DEFAULT_TEST_TENANT_ID,
        OTHER_TENANT_ID,
    }


# ---------- lifecycle and query parameters ----------


async def test_a_closed_session_reports_its_end(
    event_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = event_env
    event_id = await _record(engine, closed=True)
    body = assert_ok(await client.get(f"{_PATH}/{event_id}"))
    assert body["endedAt"] is not None
    assert body["endedAt"].endswith("Z")


async def test_default_order_is_most_recently_started_first(
    event_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """This table has no ``createdAt``, so the default order is ``startedAt``."""
    client, engine = event_env
    first = await _record(engine, impersonator_id="owner", closed=True)
    second = await _record(engine, impersonator_id="tester")
    rows = assert_ok(await client.get(_PATH))
    assert [row["id"] for row in rows] == [second, first]


async def test_filter_by_impersonator(
    event_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = event_env
    await _record(engine, impersonator_id="owner")
    wanted = await _record(engine, impersonator_id="tester")
    rows = assert_ok(await client.get(_PATH, params={"q": "impersonatorId:eq:tester"}))
    assert [row["id"] for row in rows] == [wanted]


async def test_target_tenant_id_is_not_filterable(
    event_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """It has no column behind it, so it is reported unknown like any other
    nonexistent field -- filtering and sorting stay on the real columns."""
    client, _ = event_env
    assert_err(
        await client.get(_PATH, params={"q": f"targetTenantId:eq:{OTHER_TENANT_ID}"}),
        code="INVALID_QUERY",
        status=400,
    )
