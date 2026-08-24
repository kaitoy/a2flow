"""Tests for issuing the certificate that carries a granted approval's authority.

The load-bearing case is `test_certificate_grant_is_frozen_at_decision_time`:
the execution agent can rewrite a task's ``tool_bindings`` mid-run, and the
whole point of signing the granted tools into the certificate is that doing so
cannot widen what the task may call.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure.mcp_ca import certificate_from_pem
from infrastructure.mcp_certificate import extract_claims
from infrastructure.secret_cipher import get_secret_cipher
from models.approval import Approval, ApprovalStatus
from models.approval_certificate import ApprovalCertificate, RevocationReason
from models.mcp_server import MCPServer, McpTransport
from models.workflow_execution import WorkflowExecution
from models.workflow_task import (
    WorkflowTask,
    WorkflowTaskStatus,
    WorkflowTaskToolBinding,
)
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users
from tests.conftest import _install_auth_overrides


@pytest_asyncio.fixture()
async def cert_env() -> AsyncGenerator[tuple[AsyncClient, AsyncEngine], None]:
    """Yield an API client and the engine backing it, with users seeded."""
    from infrastructure.database import get_session
    from main import app

    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(mem_engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await seed_users(mem_engine)
    await seed_tenant(mem_engine)

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


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


async def _seed_execution(eng: AsyncEngine, *, user_id: str = "owner") -> str:
    """Insert a WorkflowExecution and return its id."""
    async with AsyncSession(eng) as db:
        execution = WorkflowExecution(
            session_id="sess-cert",
            name="wf",
            workflow_prompt="do it",
            agent_skill_id="skill-1",
            agent_skill_name="skill",
            agent_skill_repo_url="https://example.com/repo",
            agent_skill_repo_path=".",
            skill_dir="/tmp/skill",
            initiator_id=user_id,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)
        return execution.id


async def _seed_mcp_server(eng: AsyncEngine, *, name: str = "files") -> str:
    """Insert an MCPServer and return its id."""
    async with AsyncSession(eng) as db:
        server = MCPServer(
            name=name,
            transport=McpTransport.streamable_http,
            url="https://example.com/mcp",
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by="owner",
            updated_by="owner",
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server.id


async def _seed_task(
    eng: AsyncEngine,
    execution_id: str,
    *,
    bindings: list[tuple[str, str]],
    status: WorkflowTaskStatus = WorkflowTaskStatus.in_progress,
) -> str:
    """Insert a WorkflowTask with the given ``(server_id, tool_name)`` bindings."""
    async with AsyncSession(eng) as db:
        task = WorkflowTask(
            workflow_execution_id=execution_id,
            title="Do the thing",
            status=status,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by="owner",
            updated_by="owner",
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        # Captured before the second commit: that commit expires ``task``, and
        # reading an expired attribute outside a greenlet context raises
        # MissingGreenlet on an async session.
        task_id = task.id
        for server_id, tool_name in bindings:
            db.add(
                WorkflowTaskToolBinding(
                    task_id=task_id, mcp_server_id=server_id, tool_name=tool_name
                )
            )
        await db.commit()
        return task_id


async def _bind_tool(eng: AsyncEngine, task_id: str, server_id: str, tool: str) -> None:
    """Add one more tool binding to an existing task."""
    async with AsyncSession(eng) as db:
        db.add(
            WorkflowTaskToolBinding(
                task_id=task_id, mcp_server_id=server_id, tool_name=tool
            )
        )
        await db.commit()


async def _insert_approval(
    eng: AsyncEngine,
    *,
    execution_id: str,
    task_id: str | None,
    approver: str = "alice",
    status: ApprovalStatus = ApprovalStatus.pending,
) -> str:
    """Insert a pending Approval addressed to ``approver`` and return its id."""
    async with AsyncSession(eng) as db:
        approval = Approval(
            workflow_execution_id=execution_id,
            workflow_task_id=task_id,
            title="Approve me",
            status=status,
            approver=approver,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by="owner",
            updated_by="owner",
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        return approval.id


async def _certificates(
    eng: AsyncEngine, approval_id: str
) -> list[ApprovalCertificate]:
    """Return every certificate row issued for an approval."""
    async with AsyncSession(eng) as db:
        result = await db.exec(
            select(ApprovalCertificate).where(
                ApprovalCertificate.approval_id == approval_id
            )
        )
        return list(result.all())


async def _decide(
    client: AsyncClient, approval_id: str, status: str, *, comment: str | None = None
) -> Any:
    """PATCH an approval as ``alice`` and return the unwrapped envelope data."""
    body: dict[str, Any] = {"status": status}
    if comment is not None:
        body["response"] = comment
    response = await client.patch(
        f"/api/v1/approvals/{approval_id}", json=body, headers={"X-User-Id": "alice"}
    )
    return assert_ok(response)


# ---------------------------------------------------------------------------
# Issuance
# ---------------------------------------------------------------------------


async def test_approving_a_task_approval_issues_a_certificate(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )

    await _decide(client, approval_id, "approved")

    certificates = await _certificates(eng, approval_id)
    assert len(certificates) == 1
    certificate = certificates[0]
    assert certificate.workflow_task_id == task_id
    assert certificate.revoked_at is None

    claims = extract_claims(certificate_from_pem(certificate.certificate_pem))
    assert claims.binding.task_id == task_id
    assert claims.binding.approval_id == approval_id
    assert claims.binding.execution_id == execution_id
    assert claims.binding.tenant_id == DEFAULT_TEST_TENANT_ID
    assert claims.allowed_tools == frozenset({(server_id, "read_file")})


async def test_rejecting_issues_nothing(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )

    await _decide(client, approval_id, "rejected")

    assert await _certificates(eng, approval_id) == []


async def test_returning_issues_nothing(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )

    await _decide(client, approval_id, "returned")

    assert await _certificates(eng, approval_id) == []


async def test_approval_without_a_task_issues_nothing(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """An approval that names no task grants no tool authority."""
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    approval_id = await _insert_approval(eng, execution_id=execution_id, task_id=None)

    await _decide(client, approval_id, "approved")

    assert await _certificates(eng, approval_id) == []


async def test_multiple_bound_tools_all_land_in_the_certificate(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_a = await _seed_mcp_server(eng, name="files")
    server_b = await _seed_mcp_server(eng, name="search")
    task_id = await _seed_task(
        eng,
        execution_id,
        bindings=[
            (server_a, "read_file"),
            (server_a, "write_file"),
            (server_b, "query"),
        ],
    )
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )

    await _decide(client, approval_id, "approved")

    certificate = (await _certificates(eng, approval_id))[0]
    claims = extract_claims(certificate_from_pem(certificate.certificate_pem))
    assert claims.allowed_tools == frozenset(
        {
            (server_a, "read_file"),
            (server_a, "write_file"),
            (server_b, "query"),
        }
    )


async def test_a_task_with_no_bindings_gets_a_certificate_granting_nothing(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """The binding URN alone is a valid certificate; it just grants no tool."""
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[])
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )

    await _decide(client, approval_id, "approved")

    certificate = (await _certificates(eng, approval_id))[0]
    claims = extract_claims(certificate_from_pem(certificate.certificate_pem))
    assert claims.allowed_tools == frozenset()
    assert claims.binding.task_id == task_id


# ---------------------------------------------------------------------------
# The frozen grant
# ---------------------------------------------------------------------------


async def test_certificate_grant_is_frozen_at_decision_time(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Widening a task's bindings after approval must not widen the grant.

    This is the escalation path the certificate exists to close: the execution
    agent can call ``update_workflow_task(tool_bindings=[...])`` on its own
    task, so a rule that reads the bindings at call time is a rule the agent
    can rewrite. The certificate is signed once and cannot be.
    """
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )

    await _decide(client, approval_id, "approved")

    # The agent binds a far more dangerous tool to its own task afterwards.
    await _bind_tool(eng, task_id, server_id, "delete_everything")

    certificate = (await _certificates(eng, approval_id))[0]
    claims = extract_claims(certificate_from_pem(certificate.certificate_pem))
    assert claims.allowed_tools == frozenset({(server_id, "read_file")})
    assert not claims.grants(server_id, "delete_everything")


async def test_editing_the_comment_does_not_rotate_the_certificate(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A later comment edit re-enters ``resolve`` and must reuse the certificate."""
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )

    await _decide(client, approval_id, "approved")
    first = (await _certificates(eng, approval_id))[0]

    await _decide(client, approval_id, "approved", comment="on reflection, fine")

    after = await _certificates(eng, approval_id)
    assert len(after) == 1
    assert after[0].serial_number == first.serial_number
    assert after[0].revoked_at is None


# ---------------------------------------------------------------------------
# Validity window and key custody
# ---------------------------------------------------------------------------


async def test_validity_window_is_anchored_on_the_decision(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )

    before = datetime.now(UTC)
    await _decide(client, approval_id, "approved")

    certificate = (await _certificates(eng, approval_id))[0]
    ttl = timedelta(seconds=get_settings().mcp_approval_cert_ttl_seconds)

    # The certificate itself is what verification reads, so assert on it first.
    parsed = certificate_from_pem(certificate.certificate_pem)
    assert parsed.not_valid_after_utc - parsed.not_valid_before_utc == ttl
    # Anchored on decided_at, which was stamped moments ago.
    assert abs(parsed.not_valid_before_utc - before) < timedelta(seconds=30)

    # The stored columns mirror it. SQLite discards the offset (TZDateTime is a
    # storage no-op there), so normalize before comparing.
    stored_before = certificate.not_before.replace(tzinfo=UTC)
    stored_after = certificate.not_after.replace(tzinfo=UTC)
    assert stored_after - stored_before == ttl


async def test_private_key_is_stored_only_as_ciphertext(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )

    await _decide(client, approval_id, "approved")

    certificate = (await _certificates(eng, approval_id))[0]
    assert "PRIVATE KEY" not in certificate.private_key_encrypted
    plain = get_secret_cipher().decrypt(certificate.private_key_encrypted)
    assert "PRIVATE KEY" in plain


async def test_certificate_serial_matches_the_signed_certificate(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """The stored serial is how verification gets from a presented cert to the row."""
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )

    await _decide(client, approval_id, "approved")

    certificate = (await _certificates(eng, approval_id))[0]
    parsed = certificate_from_pem(certificate.certificate_pem)
    assert certificate.serial_number == str(parsed.serial_number)


# ---------------------------------------------------------------------------
# GET /approvals/{id}/certificate
# ---------------------------------------------------------------------------


async def test_certificate_endpoint_reports_the_granted_tools(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )
    await _decide(client, approval_id, "approved")

    response = await client.get(
        f"/api/v1/approvals/{approval_id}/certificate",
        headers={"X-User-Id": "alice"},
    )

    data = assert_ok(response)
    assert data["allowedTools"] == [{"mcpServerId": server_id, "toolName": "read_file"}]
    assert data["revokedAt"] is None
    assert data["approvalId"] == approval_id
    assert data["workflowTaskId"] == task_id


async def test_certificate_endpoint_never_returns_key_material(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Neither the private key nor the certificate body leaves the backend."""
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )
    await _decide(client, approval_id, "approved")

    response = await client.get(
        f"/api/v1/approvals/{approval_id}/certificate",
        headers={"X-User-Id": "alice"},
    )

    body = response.text
    assert "privateKeyEncrypted" not in body
    assert "private_key_encrypted" not in body
    assert "PRIVATE KEY" not in body
    assert "certificatePem" not in body


async def test_certificate_endpoint_404s_when_none_was_issued(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )
    await _decide(client, approval_id, "rejected")

    response = await client.get(
        f"/api/v1/approvals/{approval_id}/certificate",
        headers={"X-User-Id": "alice"},
    )

    assert_err(response, "NOT_FOUND", 404)


# ---------------------------------------------------------------------------
# Revocation
# ---------------------------------------------------------------------------


async def _set_task_status(client: AsyncClient, task_id: str, status: str) -> None:
    """PATCH a task's status as ``alice``, the approval's designated approver."""
    response = await client.patch(
        f"/api/v1/workflow-tasks/{task_id}",
        json={"status": status},
        headers={"X-User-Id": "alice"},
    )
    assert_ok(response)


async def test_finishing_the_task_revokes_its_certificate(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A certificate's life ends with the work it authorized, not with its TTL."""
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )
    await _decide(client, approval_id, "approved")
    assert (await _certificates(eng, approval_id))[0].revoked_at is None

    await _set_task_status(client, task_id, "completed")

    certificate = (await _certificates(eng, approval_id))[0]
    assert certificate.revoked_at is not None
    assert certificate.revocation_reason == RevocationReason.task_finished


async def test_a_failed_task_also_revokes(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )
    await _decide(client, approval_id, "approved")

    await _set_task_status(client, task_id, "failed")

    assert (await _certificates(eng, approval_id))[0].revoked_at is not None


async def test_a_non_terminal_status_change_leaves_the_certificate_alone(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(
        eng,
        execution_id,
        bindings=[(server_id, "read_file")],
        status=WorkflowTaskStatus.pending,
    )
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )
    await _decide(client, approval_id, "approved")

    await _set_task_status(client, task_id, "in_progress")

    assert (await _certificates(eng, approval_id))[0].revoked_at is None
