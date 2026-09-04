"""Tests for issuing the certificate that carries a task's MCP tool authority.

Two issuance paths are covered: an approver granting an approval, and the run's
initiator granting a task's tools to themselves when it goes ``in_progress``.
The load-bearing cases are `test_certificate_grant_is_frozen_at_decision_time`
and its initiator twin `test_an_initiator_grant_is_frozen_at_start`: a task's
``tool_bindings`` can still change after a certificate is issued (a workflow
re-publish, say), and the whole point of signing the granted tools into the
certificate is that any such change cannot widen what the task may call.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure.mcp_ca import certificate_from_pem
from infrastructure.mcp_certificate import extract_claims
from infrastructure.secret_cipher import get_secret_cipher
from infrastructure.workflow_task_tools import update_workflow_task
from models.approval import Approval, ApprovalStatus
from models.mcp_server import MCPServer, McpTransport
from models.mcp_tool_certificate import (
    CertificateGrant,
    McpToolCertificate,
    RevocationReason,
)
from models.workflow_execution import WorkflowExecution
from models.workflow_task import (
    WorkflowTask,
    WorkflowTaskDependency,
    WorkflowTaskStatus,
    WorkflowTaskToolBinding,
)
from repositories.mcp_tool_certificate import SqlMcpToolCertificateRepository
from tests._engine import make_test_engine
from tests._envelope import assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users
from tests.conftest import _install_auth_overrides


@pytest_asyncio.fixture()
async def cert_env() -> AsyncGenerator[tuple[AsyncClient, AsyncEngine], None]:
    """Yield an API client and the engine backing it, with users seeded."""
    from infrastructure.database import get_session
    from main import app

    mem_engine = await make_test_engine()
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
    depends_on: list[str] | None = None,
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
        for dependency_id in depends_on or []:
            db.add(WorkflowTaskDependency(task_id=task_id, depends_on_id=dependency_id))
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


async def _certificates(eng: AsyncEngine, approval_id: str) -> list[McpToolCertificate]:
    """Return every certificate row issued for an approval."""
    async with AsyncSession(eng) as db:
        result = await db.exec(
            select(McpToolCertificate).where(
                McpToolCertificate.approval_id == approval_id
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


async def test_a_task_with_no_bindings_is_granted_nothing(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A gate step that binds no tools needs no certificate of its own.

    This is the ordinary shape now: the step that *asks* for the go-ahead binds
    nothing, and the approval's authority is carried by the certificates of the
    tasks after it. A certificate here would be a row, a keypair, and an audit
    entry authorizing nothing.
    """
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[])
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )

    await _decide(client, approval_id, "approved")

    assert await _certificates(eng, approval_id) == []


async def test_an_approval_covers_the_tasks_after_the_step_it_names(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """The load-bearing case: naming the asking step authorizes what follows it.

    The gate step binds nothing, so its own certificate would grant nothing --
    the decision has to reach the step downstream that actually holds the tools.
    """
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    gate = await _seed_task(eng, execution_id, bindings=[])
    acting = await _seed_task(
        eng, execution_id, bindings=[(server_id, "launch")], depends_on=[gate]
    )
    approval_id = await _insert_approval(eng, execution_id=execution_id, task_id=gate)

    await _decide(client, approval_id, "approved")

    certificates = await _certificates(eng, approval_id)
    assert len(certificates) == 1
    claims = extract_claims(certificate_from_pem(certificates[0].certificate_pem))
    assert claims.binding.task_id == acting
    assert claims.binding.approval_id == approval_id
    assert claims.allowed_tools == frozenset({(server_id, "launch")})


async def test_an_approval_stops_at_the_next_approval(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A nearer approval takes its task over; the outer one no longer reaches it."""
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    first_gate = await _seed_task(eng, execution_id, bindings=[])
    middle = await _seed_task(
        eng, execution_id, bindings=[(server_id, "read_file")], depends_on=[first_gate]
    )
    second_gate = await _seed_task(
        eng, execution_id, bindings=[(server_id, "delete_file")], depends_on=[middle]
    )
    outer = await _insert_approval(eng, execution_id=execution_id, task_id=first_gate)
    inner = await _insert_approval(eng, execution_id=execution_id, task_id=second_gate)

    await _decide(client, outer, "approved")

    assert [c.workflow_task_id for c in await _certificates(eng, outer)] == [middle]
    assert await _certificates(eng, inner) == []

    await _decide(client, inner, "approved")

    assert [c.workflow_task_id for c in await _certificates(eng, inner)] == [
        second_gate
    ]


async def test_a_merge_needs_every_governing_approval(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Where two gated branches meet, one approver's decision is not enough."""
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    left = await _seed_task(eng, execution_id, bindings=[])
    right = await _seed_task(eng, execution_id, bindings=[])
    merge = await _seed_task(
        eng,
        execution_id,
        bindings=[(server_id, "publish")],
        depends_on=[left, right],
    )
    left_approval = await _insert_approval(eng, execution_id=execution_id, task_id=left)
    right_approval = await _insert_approval(
        eng, execution_id=execution_id, task_id=right
    )

    await _decide(client, left_approval, "approved")
    assert await _certificates(eng, left_approval) == []

    await _decide(client, right_approval, "approved")
    issued = await _certificates(eng, left_approval) + await _certificates(
        eng, right_approval
    )
    assert [certificate.workflow_task_id for certificate in issued] == [merge]


# ---------------------------------------------------------------------------
# The frozen grant
# ---------------------------------------------------------------------------


async def test_certificate_grant_is_frozen_at_decision_time(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Widening a task's bindings after approval must not widen the grant.

    This is the escalation path the certificate exists to close: a task's
    ``tool_bindings`` can change after the approval was decided -- a workflow
    re-publish, or any write outside the run -- so a rule that read the bindings
    at call time could be widened out from under the approver. The certificate
    is signed once and cannot be.
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
    ttl = timedelta(seconds=get_settings().mcp_tool_cert_ttl_seconds)

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
# GET /approvals/{id}/certificates
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
        f"/api/v1/approvals/{approval_id}/certificates",
        headers={"X-User-Id": "alice"},
    )

    data = assert_ok(response)
    assert len(data) == 1
    assert data[0]["allowedTools"] == [
        {"mcpServerId": server_id, "toolName": "read_file"}
    ]
    assert data[0]["revokedAt"] is None
    assert data[0]["approvalId"] == approval_id
    assert data[0]["workflowTaskId"] == task_id


async def test_certificate_endpoint_lists_one_row_per_covered_task(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """One approval, two covered tasks underway, two certificates."""
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    gate = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    downstream = await _seed_task(
        eng, execution_id, bindings=[(server_id, "write_file")], depends_on=[gate]
    )
    approval_id = await _insert_approval(eng, execution_id=execution_id, task_id=gate)

    await _decide(client, approval_id, "approved")

    response = await client.get(
        f"/api/v1/approvals/{approval_id}/certificates",
        headers={"X-User-Id": "alice"},
    )

    data = assert_ok(response)
    assert {row["workflowTaskId"] for row in data} == {gate, downstream}
    granted = {
        row["workflowTaskId"]: row["allowedTools"][0]["toolName"] for row in data
    }
    assert granted == {gate: "read_file", downstream: "write_file"}


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
        f"/api/v1/approvals/{approval_id}/certificates",
        headers={"X-User-Id": "alice"},
    )

    assert len(assert_ok(response)) == 1
    body = response.text
    assert "privateKeyEncrypted" not in body
    assert "private_key_encrypted" not in body
    assert "PRIVATE KEY" not in body
    assert "certificatePem" not in body


async def test_certificate_endpoint_is_empty_when_none_was_issued(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """An approval that granted nothing has no certificates, not a 404.

    Nothing being issued yet is an ordinary state now that a covered task is
    granted only when it starts, so the empty list is the honest answer.
    """
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )
    await _decide(client, approval_id, "rejected")

    response = await client.get(
        f"/api/v1/approvals/{approval_id}/certificates",
        headers={"X-User-Id": "alice"},
    )

    assert assert_ok(response) == []


# ---------------------------------------------------------------------------
# Revocation
# ---------------------------------------------------------------------------


def _tool_context() -> Any:
    """Build the fake ADK ToolContext the WorkflowTask agent tools read.

    ``session.id`` must match the seeded execution's ``session_id``: that is how
    a tool call outside FastAPI's request scope resolves which run it belongs to.
    """
    return SimpleNamespace(
        session=SimpleNamespace(id="sess-cert"), user_id="alice", state=None
    )


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


async def test_the_agent_tool_also_revokes_a_finished_task(
    cert_env: tuple[AsyncClient, AsyncEngine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real run finishes its tasks through the agent tool, not the REST route.

    ``WorkflowTaskService.update`` covers the REST path only, so revoking there
    alone would leave every agent-driven run's certificates live until their
    TTL -- which is every run.
    """
    client, eng = cert_env
    monkeypatch.setattr("infrastructure.database.engine", eng)
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )
    await _decide(client, approval_id, "approved")
    assert (await _certificates(eng, approval_id))[0].revoked_at is None

    result = await update_workflow_task(
        task_id, _tool_context(), status=WorkflowTaskStatus.completed.value
    )
    assert "error" not in result, result

    certificate = (await _certificates(eng, approval_id))[0]
    assert certificate.revoked_at is not None
    assert certificate.revocation_reason == RevocationReason.task_finished


async def test_the_agent_tool_leaves_an_unfinished_task_alone(
    cert_env: tuple[AsyncClient, AsyncEngine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only a terminal status spends the grant; a non-terminal update must not."""
    client, eng = cert_env
    monkeypatch.setattr("infrastructure.database.engine", eng)
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )
    await _decide(client, approval_id, "approved")

    result = await update_workflow_task(task_id, _tool_context(), status="in_progress")
    assert "error" not in result, result

    assert (await _certificates(eng, approval_id))[0].revoked_at is None


# ---------------------------------------------------------------------------
# The initiator's own grant
# ---------------------------------------------------------------------------


async def _initiator_grant(
    eng: AsyncEngine, execution_id: str, task_id: str
) -> McpToolCertificate | None:
    """Run the issuance path a task write takes and return what it produced."""
    from repositories.mcp_server import SqlMCPServerRepository
    from repositories.workflow_execution import SqlWorkflowExecutionRepository
    from repositories.workflow_task import SqlWorkflowTaskRepository
    from services.mcp_tool_certificate import build_mcp_tool_certificate_service

    async with AsyncSession(eng, expire_on_commit=False) as db:
        executions = SqlWorkflowExecutionRepository(
            db, tenant_id=DEFAULT_TEST_TENANT_ID
        )
        tasks = SqlWorkflowTaskRepository(
            db,
            executions,
            SqlMCPServerRepository(db, tenant_id=DEFAULT_TEST_TENANT_ID),
            tenant_id=DEFAULT_TEST_TENANT_ID,
        )
        execution = await executions.get(execution_id)
        task = await tasks.get(task_id)
        assert execution is not None and task is not None
        service = build_mcp_tool_certificate_service(
            db, tenant_id=DEFAULT_TEST_TENANT_ID
        )
        return await service.issue_for_started_task(task, execution, user_id="owner")


async def test_starting_a_task_grants_it_the_initiators_authority(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    _, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])

    certificate = await _initiator_grant(eng, execution_id, task_id)

    assert certificate is not None
    assert certificate.grant_kind is CertificateGrant.initiator
    assert certificate.approval_id is None
    # The run's initiator, not the user who happened to make the write.
    assert certificate.granted_by == "owner"
    claims = extract_claims(certificate_from_pem(certificate.certificate_pem))
    assert claims.allowed_tools == frozenset({(server_id, "read_file")})
    assert claims.binding.initiator_id == "owner"
    assert claims.binding.approval_id is None


@pytest.mark.parametrize(
    ("status", "bindings_kind"),
    [
        (WorkflowTaskStatus.pending, "some"),
        (WorkflowTaskStatus.completed, "some"),
        (WorkflowTaskStatus.in_progress, "none"),
    ],
    ids=["not started", "already finished", "binds nothing"],
)
async def test_no_grant_is_issued_when_there_is_nothing_to_authorize(
    cert_env: tuple[AsyncClient, AsyncEngine],
    status: WorkflowTaskStatus,
    bindings_kind: str,
) -> None:
    """Three of the four no-op conditions, each for its own reason.

    A task that has not started or has finished needs no tool authority, and one
    binding no tools can call nothing anyway -- so a certificate for it would be
    a row, a keypair, and an audit entry that authorize nothing.
    """
    _, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    bindings = [(server_id, "read_file")] if bindings_kind == "some" else []
    task_id = await _seed_task(eng, execution_id, bindings=bindings, status=status)

    assert await _initiator_grant(eng, execution_id, task_id) is None


async def test_starting_a_task_twice_does_not_rotate_its_grant(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """The fourth no-op: an agent re-sending ``in_progress`` must change nothing.

    Rotating would swap the key and the frozen tool set underneath a task that
    is already calling against them.
    """
    _, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])

    first = await _initiator_grant(eng, execution_id, task_id)
    assert first is not None

    assert await _initiator_grant(eng, execution_id, task_id) is None


async def test_an_initiator_grant_is_frozen_at_start(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Binding a tool after the task started does not extend its grant."""
    _, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])

    certificate = await _initiator_grant(eng, execution_id, task_id)
    assert certificate is not None
    await _bind_tool(eng, task_id, server_id, "delete_everything")

    claims = extract_claims(certificate_from_pem(certificate.certificate_pem))
    assert claims.allowed_tools == frozenset({(server_id, "read_file")})
    assert await _initiator_grant(eng, execution_id, task_id) is None


async def test_a_task_with_an_approval_gets_no_initiator_grant(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """That task's authority is the approver's to grant, whatever its status."""
    _, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    await _insert_approval(eng, execution_id=execution_id, task_id=task_id)

    assert await _initiator_grant(eng, execution_id, task_id) is None


async def test_granting_an_approval_stands_the_initiator_grant_down(
    cert_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A task started before its approval was requested ends up with one grant.

    The initiator's is revoked with a reason that says why, rather than left
    live alongside the approver's.
    """
    client, eng = cert_env
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(eng, execution_id, bindings=[(server_id, "read_file")])
    initiator = await _initiator_grant(eng, execution_id, task_id)
    assert initiator is not None

    approval_id = await _insert_approval(
        eng, execution_id=execution_id, task_id=task_id
    )
    await _decide(client, approval_id, "approved")

    async with AsyncSession(eng) as db:
        stood_down = await db.get(McpToolCertificate, initiator.id)
        assert stood_down is not None
        assert stood_down.revoked_at is not None
        assert stood_down.revocation_reason is RevocationReason.superseded_by_approval
    granted = await _certificates(eng, approval_id)
    assert len(granted) == 1
    assert granted[0].grant_kind is CertificateGrant.approval
    assert granted[0].granted_by == "alice"


async def test_the_agent_tool_grants_a_task_it_starts(
    cert_env: tuple[AsyncClient, AsyncEngine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The path a real run takes: ``update_workflow_task`` moves it to in_progress.

    ``WorkflowTaskService`` covers the REST path only, so issuing there alone
    would leave every agent-driven run -- which is every run -- unable to call
    any tool at all.
    """
    _, eng = cert_env
    monkeypatch.setattr("infrastructure.database.engine", eng)
    execution_id = await _seed_execution(eng)
    server_id = await _seed_mcp_server(eng)
    task_id = await _seed_task(
        eng,
        execution_id,
        bindings=[(server_id, "read_file")],
        status=WorkflowTaskStatus.pending,
    )

    result = await update_workflow_task(task_id, _tool_context(), status="in_progress")

    assert "error" not in result
    async with AsyncSession(eng) as db:
        certificate = await SqlMcpToolCertificateRepository(
            db, tenant_id=DEFAULT_TEST_TENANT_ID
        ).get_live_for_task(task_id)
    assert certificate is not None
    assert certificate.grant_kind is CertificateGrant.initiator
