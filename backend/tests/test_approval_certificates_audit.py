"""Tests for the admin-only tenant-wide ``/approval-certificates`` List/Get API.

Certificates are minted only by
:class:`services.approval_certificate.ApprovalCertificateService` when an
approval is granted, so every row here is created by driving a real approval
decision through the API rather than by inserting one -- which is also what
makes the parsed ``allowedTools`` assertions meaningful: they come back out of a
genuinely signed certificate.

Distinct from ``tests/test_approval_certificate.py``, which covers issuance,
revocation, and the per-approval ``GET /approvals/{id}/certificate``. This file
covers only the audit surface: its role gate, tenant scoping, and that key
material stays out of both the payload and the query surface.
"""

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from dependencies.auth import ALL_TENANTS_SENTINEL, TENANT_HEADER_NAME
from models.approval import Approval, ApprovalStatus
from models.mcp_server import MCPServer, McpTransport
from models.workflow_execution import WorkflowExecution
from models.workflow_task import (
    WorkflowTask,
    WorkflowTaskStatus,
    WorkflowTaskToolBinding,
)
from tests._engine import make_test_engine
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users
from tests.conftest import _install_auth_overrides

_PATH = "/api/v1/approval-certificates"

#: A second tenant used by the isolation tests.
OTHER_TENANT_ID = "tenant-other"

#: Headers selecting a plain (non-super-admin) admin in the default tenant.
ADMIN: dict[str, str] = {"X-User-Id": "bob", "X-User-Roles": "admin"}

#: Headers selecting a role-less user.
NOBODY: dict[str, str] = {"X-User-Id": "carol", "X-User-Roles": ""}

#: Headers selecting a platform-scoped super_admin browsing every tenant.
ALL_TENANTS: dict[str, str] = {
    "X-User-Id": "tester",
    "X-User-Roles": "super_admin",
    "X-User-Tenant-Id": "",
    TENANT_HEADER_NAME: ALL_TENANTS_SENTINEL,
}


@pytest_asyncio.fixture()
async def audit_env() -> AsyncGenerator[tuple[AsyncClient, AsyncEngine], None]:
    """Yield an API client (default caller: super_admin in the default tenant) plus its engine."""
    from infrastructure.database import get_session
    from main import app

    mem_engine = await make_test_engine()
    await seed_users(mem_engine)
    await seed_tenant(mem_engine, OTHER_TENANT_ID)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    _install_auth_overrides(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac, mem_engine
    finally:
        app.dependency_overrides.clear()
        await mem_engine.dispose()


async def _issue_certificate(
    client: AsyncClient,
    engine: AsyncEngine,
    *,
    tenant_id: str = DEFAULT_TEST_TENANT_ID,
    tool_name: str = "read_file",
) -> str:
    """Drive one approval to ``approved`` so a real certificate is signed.

    Returns:
        The id of the approval the certificate was issued for. Its certificate
        is then found through the audit list or ``GET /approvals/{id}/certificate``.
    """
    # ``expire_on_commit=False``: this helper reads ids back after each commit,
    # and an expired attribute would trigger IO outside a greenlet context.
    async with AsyncSession(engine, expire_on_commit=False) as db:
        execution = WorkflowExecution(
            session_id="sess-audit",
            name="wf",
            workflow_prompt="do it",
            agent_skill_id="skill-1",
            agent_skill_name="skill",
            agent_skill_repo_url="https://example.com/repo",
            agent_skill_repo_path=".",
            skill_dir="/tmp/skill",
            initiator_id="owner",
            tenant_id=tenant_id,
            created_by="owner",
            updated_by="owner",
        )
        server = MCPServer(
            name=f"files-{tenant_id}-{tool_name}",
            transport=McpTransport.streamable_http,
            url="https://example.com/mcp",
            tenant_id=tenant_id,
            created_by="owner",
            updated_by="owner",
        )
        db.add(execution)
        db.add(server)
        await db.commit()
        execution_id, server_id = execution.id, server.id

        task = WorkflowTask(
            workflow_execution_id=execution_id,
            title="Do the thing",
            status=WorkflowTaskStatus.in_progress,
            tenant_id=tenant_id,
            created_by="owner",
            updated_by="owner",
        )
        db.add(task)
        await db.commit()
        task_id = task.id
        db.add(
            WorkflowTaskToolBinding(
                task_id=task_id, mcp_server_id=server_id, tool_name=tool_name
            )
        )
        approval = Approval(
            workflow_execution_id=execution_id,
            workflow_task_id=task_id,
            title="Approve me",
            status=ApprovalStatus.pending,
            approver="alice",
            tenant_id=tenant_id,
            created_by="owner",
            updated_by="owner",
        )
        db.add(approval)
        await db.commit()
        approval_id = approval.id

    response = await client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"status": "approved"},
        headers={"X-User-Id": "alice", "X-User-Tenant-Id": tenant_id},
    )
    assert_ok(response)
    return str(approval_id)


# ---------- authorization ----------


async def test_super_admin_can_list(
    audit_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = audit_env
    approval_id = await _issue_certificate(client, engine)
    rows = assert_ok(await client.get(_PATH))
    assert [row["approvalId"] for row in rows] == [approval_id]


async def test_plain_admin_can_list(audit_env: tuple[AsyncClient, AsyncEngine]) -> None:
    client, engine = audit_env
    approval_id = await _issue_certificate(client, engine)
    rows = assert_ok(await client.get(_PATH, headers=ADMIN))
    assert [row["approvalId"] for row in rows] == [approval_id]


async def test_plain_admin_can_get(audit_env: tuple[AsyncClient, AsyncEngine]) -> None:
    client, engine = audit_env
    await _issue_certificate(client, engine)
    certificate_id = assert_ok(await client.get(_PATH))[0]["id"]
    body = assert_ok(await client.get(f"{_PATH}/{certificate_id}", headers=ADMIN))
    assert body["id"] == certificate_id
    assert body["serialNumber"]
    assert body["revokedAt"] is None


async def test_role_less_user_is_forbidden(
    audit_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = audit_env
    assert_err(await client.get(_PATH, headers=NOBODY), code="FORBIDDEN", status=403)


async def test_list_is_forbidden_for_a_platform_scoped_caller_without_a_tenant_header(
    audit_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = audit_env
    assert_err(
        await client.get(_PATH, headers={"X-User-Tenant-Id": ""}),
        code="FORBIDDEN",
        status=403,
    )


# ---------- what the payload discloses ----------


async def test_granted_tools_come_back_out_of_the_signed_certificate(
    audit_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Parsed from the PEM rather than read from a column, so the list can never
    disagree with what was actually signed."""
    client, engine = audit_env
    await _issue_certificate(client, engine, tool_name="write_file")
    row = assert_ok(await client.get(_PATH))[0]
    assert [tool["toolName"] for tool in row["allowedTools"]] == ["write_file"]


async def test_key_material_is_never_returned(
    audit_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = audit_env
    await _issue_certificate(client, engine)
    row = assert_ok(await client.get(_PATH))[0]
    assert "privateKeyEncrypted" not in row
    assert "certificatePem" not in row


async def test_key_material_is_not_filterable(
    audit_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A hidden field is reported unknown, so a client cannot use "which rows
    match" as a blind oracle on a value it never receives."""
    client, _ = audit_env
    for field in ("privateKeyEncrypted", "certificatePem"):
        assert_err(
            await client.get(_PATH, params={"q": f"{field}:like:x"}),
            code="INVALID_QUERY",
            status=400,
        )


# ---------- read-only surface ----------


async def test_there_is_no_write_route(
    audit_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A certificate's contents are signed; only whether it still counts can
    change, and that happens in the service, not through a route."""
    client, engine = audit_env
    await _issue_certificate(client, engine)
    certificate_id = assert_ok(await client.get(_PATH))[0]["id"]
    assert (await client.post(_PATH, json={})).status_code == 405
    assert (await client.patch(f"{_PATH}/{certificate_id}", json={})).status_code == 405
    assert (await client.delete(f"{_PATH}/{certificate_id}")).status_code == 405


# ---------- tenant isolation ----------


async def test_list_does_not_mix_tenants(
    audit_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = audit_env
    mine = await _issue_certificate(client, engine, tenant_id=DEFAULT_TEST_TENANT_ID)
    await _issue_certificate(client, engine, tenant_id=OTHER_TENANT_ID)
    rows = assert_ok(await client.get(_PATH))
    assert [row["approvalId"] for row in rows] == [mine]


async def test_get_404s_across_tenants(
    audit_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = audit_env
    await _issue_certificate(client, engine, tenant_id=OTHER_TENANT_ID)
    other_id = assert_ok(await client.get(_PATH, headers=ALL_TENANTS))[0]["id"]
    assert_err(await client.get(f"{_PATH}/{other_id}"), code="NOT_FOUND", status=404)


async def test_get_404s_for_an_unknown_id(
    audit_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = audit_env
    assert_err(await client.get(f"{_PATH}/nope"), code="NOT_FOUND", status=404)


async def test_all_tenants_selection_spans_every_tenant(
    audit_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = audit_env
    await _issue_certificate(client, engine, tenant_id=DEFAULT_TEST_TENANT_ID)
    await _issue_certificate(client, engine, tenant_id=OTHER_TENANT_ID)
    rows = assert_ok(await client.get(_PATH, headers=ALL_TENANTS))
    assert {row["tenantId"] for row in rows} == {
        DEFAULT_TEST_TENANT_ID,
        OTHER_TENANT_ID,
    }
