"""Tests for the admin-only tenant-wide ``/mcp-tool-invocations`` List/Get API.

Rows are written only by the MCP proxy's audit sink, so every record here is
inserted directly through
:class:`repositories.mcp_tool_invocation.SqlMcpToolInvocationRepository` rather
than through the API. Covers the role gate (``admin``, with ``super_admin``
passing through the ``has_role`` bypass), tenant isolation, the all-tenants
read mode, and that the surface really is read-only.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from dependencies.auth import ALL_TENANTS_SENTINEL, TENANT_HEADER_NAME
from models.mcp_tool_invocation import McpAuditDecision, McpToolInvocationCreate
from models.user import SYSTEM_USER_ID
from repositories.mcp_tool_invocation import SqlMcpToolInvocationRepository
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users
from tests.conftest import _install_auth_overrides

_PATH = "/api/v1/mcp-tool-invocations"

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


@pytest_asyncio.fixture()
async def invocation_env() -> AsyncGenerator[tuple[AsyncClient, AsyncEngine], None]:
    """Yield an API client (default caller: super_admin in the default tenant) plus its engine."""
    from infrastructure.database import get_session
    from main import app

    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(mem_engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await seed_users(mem_engine)
    await seed_tenant(mem_engine, OTHER_TENANT_ID)

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
    tenant_id: str = DEFAULT_TEST_TENANT_ID,
    tool_name: str = "read_file",
    decision: McpAuditDecision = McpAuditDecision.allowed,
    denial_reason: str | None = None,
    execution_id: str | None = None,
) -> str:
    """Append one invocation record directly (no Create endpoint exists) and return its id."""
    async with AsyncSession(engine) as session:
        repo = SqlMcpToolInvocationRepository(session, tenant_id=tenant_id)
        invocation = await repo.record(
            McpToolInvocationCreate(
                session_id="sess-1",
                workflow_execution_id=execution_id,
                mcp_server_id="server-1",
                tool_name=tool_name,
                decision=decision,
                denial_reason=denial_reason,
                arguments_digest="a" * 64,
            ),
            user_id=SYSTEM_USER_ID,
        )
        return str(invocation.id)


# ---------- authorization ----------


async def test_super_admin_can_list(
    invocation_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = invocation_env
    invocation_id = await _record(engine)
    rows = assert_ok(await client.get(_PATH))
    assert [row["id"] for row in rows] == [invocation_id]


async def test_plain_admin_can_list(
    invocation_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = invocation_env
    invocation_id = await _record(engine)
    rows = assert_ok(await client.get(_PATH, headers=ADMIN))
    assert [row["id"] for row in rows] == [invocation_id]


async def test_plain_admin_can_get(
    invocation_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = invocation_env
    invocation_id = await _record(
        engine, decision=McpAuditDecision.denied, denial_reason="no certificate"
    )
    body = assert_ok(await client.get(f"{_PATH}/{invocation_id}", headers=ADMIN))
    assert body["id"] == invocation_id
    assert body["toolName"] == "read_file"
    assert body["decision"] == "denied"
    assert body["denialReason"] == "no certificate"
    assert body["tenantId"] == DEFAULT_TEST_TENANT_ID


async def test_role_less_user_is_forbidden(
    invocation_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = invocation_env
    assert_err(await client.get(_PATH, headers=NOBODY), code="FORBIDDEN", status=403)


async def test_get_is_forbidden_for_a_role_less_user(
    invocation_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = invocation_env
    invocation_id = await _record(engine)
    assert_err(
        await client.get(f"{_PATH}/{invocation_id}", headers=NOBODY),
        code="FORBIDDEN",
        status=403,
    )


async def test_list_is_forbidden_for_a_platform_scoped_caller_without_a_tenant_header(
    invocation_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A tenant-less super_admin must select a tenant, same as any other
    tenant-scoped resource -- there is no implicit "see everything" fallback."""
    client, _ = invocation_env
    assert_err(
        await client.get(_PATH, headers={"X-User-Tenant-Id": ""}),
        code="FORBIDDEN",
        status=403,
    )


# ---------- read-only surface ----------


async def test_there_is_no_write_route(
    invocation_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """The trail is append-only: no route can create, alter, or remove a record."""
    client, engine = invocation_env
    invocation_id = await _record(engine)
    assert (await client.post(_PATH, json={})).status_code == 405
    assert (await client.patch(f"{_PATH}/{invocation_id}", json={})).status_code == 405
    assert (await client.delete(f"{_PATH}/{invocation_id}")).status_code == 405


# ---------- tenant isolation ----------


async def test_list_does_not_mix_tenants(
    invocation_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = invocation_env
    mine = await _record(engine, tenant_id=DEFAULT_TEST_TENANT_ID)
    await _record(engine, tenant_id=OTHER_TENANT_ID)
    rows = assert_ok(await client.get(_PATH))
    assert [row["id"] for row in rows] == [mine]


async def test_get_404s_across_tenants(
    invocation_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Another tenant's record is reported missing, not forbidden, so its
    existence is never confirmed."""
    client, engine = invocation_env
    other = await _record(engine, tenant_id=OTHER_TENANT_ID)
    assert_err(await client.get(f"{_PATH}/{other}"), code="NOT_FOUND", status=404)


async def test_get_404s_for_an_unknown_id(
    invocation_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = invocation_env
    assert_err(await client.get(f"{_PATH}/nope"), code="NOT_FOUND", status=404)


async def test_all_tenants_selection_spans_every_tenant(
    invocation_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = invocation_env
    await _record(engine, tenant_id=DEFAULT_TEST_TENANT_ID)
    await _record(engine, tenant_id=OTHER_TENANT_ID)
    rows = assert_ok(await client.get(_PATH, headers=ALL_TENANTS))
    assert {row["tenantId"] for row in rows} == {
        DEFAULT_TEST_TENANT_ID,
        OTHER_TENANT_ID,
    }


async def test_all_tenants_selection_resolves_any_tenants_record(
    invocation_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = invocation_env
    other = await _record(engine, tenant_id=OTHER_TENANT_ID)
    body = assert_ok(await client.get(f"{_PATH}/{other}", headers=ALL_TENANTS))
    assert body["tenantId"] == OTHER_TENANT_ID


# ---------- query parameters ----------


async def test_filter_by_decision(
    invocation_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = invocation_env
    await _record(engine, decision=McpAuditDecision.allowed)
    denied = await _record(engine, decision=McpAuditDecision.denied)
    rows = assert_ok(await client.get(_PATH, params={"q": "decision:eq:denied"}))
    assert [row["id"] for row in rows] == [denied]


async def test_sort_by_tool_name_ascending(
    invocation_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = invocation_env
    await _record(engine, tool_name="write_file")
    await _record(engine, tool_name="delete_file")
    rows = assert_ok(await client.get(_PATH, params={"s": "toolName"}))
    assert [row["toolName"] for row in rows] == ["delete_file", "write_file"]
