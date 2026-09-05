"""End-to-end tests of the certificate gate on MCP tool calls.

Drives the real presenter (:mod:`infrastructure.mcp_credentials`) and the real
verifier (:class:`infrastructure.mcp_gateway.McpGateway` with the default policy
chain) against a throwaway database, faking only the remote MCP traffic. That
is the combination the enforcement claim actually rests on, so the cases here
are the ones worth reading first:

* `test_a_task_with_no_grant_at_all_cannot_call` -- the rule itself: every call
  needs a certificate, with no exemption.
* `test_task_without_an_approval_calls_on_its_initiators_grant` -- how a task
  nobody approved satisfies that rule.
* `test_widening_bindings_after_approval_does_not_widen_the_grant` and
  `test_widening_bindings_after_the_grant_does_not_widen_it` -- the escalation
  path the plain tool-binding policy cannot close, on both grant kinds.
* `test_a_grant_is_not_issued_for_a_task_that_has_an_approval` and
  `test_an_approval_arriving_later_stands_the_initiator_grant_down` -- the two
  orderings in which a run must not talk its way past an approval.
* `test_a_recorded_call_can_be_verified_from_the_audit_row_alone` -- the
  non-repudiation claim, checked the way an auditor would.

Every call here runs through the real SQL audit sink too, so the audit path is
covered by every case rather than only by the ones that assert on it.
"""

import base64
from collections.abc import AsyncGenerator
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ec
from mcp import types
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.mcp_audit import SqlMcpAuditSink
from infrastructure.mcp_ca import (
    HASH_ALGORITHM,
    certificate_from_pem,
    load_or_create_root_ca,
)
from infrastructure.mcp_certificate import (
    McpClientCredential,
    extract_claims,
    pop_digest_from_parts,
    verify_certificate,
)
from infrastructure.mcp_certificate import (
    arguments_digest as hash_arguments,
)
from infrastructure.mcp_client import McpConnection
from infrastructure.mcp_credentials import ApprovalCredentialProvider
from infrastructure.mcp_gateway import (
    CallToolRequest,
    ListToolsRequest,
    McpGateway,
    McpPolicyDeniedError,
    McpPrincipal,
    PrincipalKind,
)
from infrastructure.mcp_policies import default_policies
from models.approval import Approval, ApprovalStatus
from models.mcp_server import MCPServer, McpTransport
from models.mcp_tool_certificate import (
    CertificateGrant,
    McpToolCertificate,
    RevocationReason,
)
from models.mcp_tool_invocation import McpAuditDecision, MCPToolInvocation
from models.user import SYSTEM_USER_ID
from models.workflow_execution import WorkflowExecution
from models.workflow_task import (
    WorkflowTask,
    WorkflowTaskDependency,
    WorkflowTaskStatus,
    WorkflowTaskToolBinding,
)
from repositories.mcp_ca import SqlMcpCertificateAuthorityRepository
from repositories.mcp_server import SqlMCPServerRepository
from repositories.mcp_tool_certificate import SqlMcpToolCertificateRepository
from repositories.workflow_execution import SqlWorkflowExecutionRepository
from repositories.workflow_task import SqlWorkflowTaskRepository
from services.mcp_tool_certificate import build_mcp_tool_certificate_service
from tests._engine import make_test_engine
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users

SESSION_ID = "sess-approval"
TOOL = "read_file"


@pytest_asyncio.fixture()
async def engine(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[AsyncEngine, None]:
    """Yield a throwaway engine and point the module-level engine at it."""
    eng = await make_test_engine()
    await seed_users(eng)
    await seed_tenant(eng)

    monkeypatch.setattr("infrastructure.database.engine", eng)
    yield eng
    await eng.dispose()


@pytest.fixture(autouse=True)
def _fake_upstream(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every proxied call succeed without touching a real MCP server."""

    async def fake_call_server_tool(
        connection: McpConnection, tool_name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="ok")], isError=False
        )

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


async def _seed_server(eng: AsyncEngine, *, name: str = "srv") -> str:
    """Insert a streamable-HTTP MCPServer and return its id."""
    async with AsyncSession(eng) as db:
        server = MCPServer(
            name=name,
            transport=McpTransport.streamable_http,
            url="https://mcp.example.com/mcp",
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server.id


async def _seed_execution(eng: AsyncEngine, *, session_id: str = SESSION_ID) -> str:
    """Insert a WorkflowExecution with the given ADK session id."""
    async with AsyncSession(eng) as db:
        execution = WorkflowExecution(
            session_id=session_id,
            name="wf",
            workflow_prompt="do it",
            agent_skill_id="skill-1",
            agent_skill_name="skill",
            agent_skill_repo_url="https://example.com/repo",
            agent_skill_repo_path=".",
            skill_dir="/tmp/skill",
            initiator_id="owner",
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)
        return execution.id


async def _seed_task(
    eng: AsyncEngine,
    execution_id: str,
    *,
    bindings: list[tuple[str, str]],
    title: str = "Step",
    status: WorkflowTaskStatus = WorkflowTaskStatus.in_progress,
    depends_on: str | None = None,
) -> str:
    """Insert a WorkflowTask with the given tool bindings, in progress by default."""
    async with AsyncSession(eng) as db:
        task = WorkflowTask(
            workflow_execution_id=execution_id,
            title=title,
            status=status,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        task_id = task.id
        for server_id, tool_name in bindings:
            db.add(
                WorkflowTaskToolBinding(
                    task_id=task_id, mcp_server_id=server_id, tool_name=tool_name
                )
            )
        if depends_on is not None:
            db.add(WorkflowTaskDependency(task_id=task_id, depends_on_id=depends_on))
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


async def _seed_approval(
    eng: AsyncEngine,
    *,
    execution_id: str,
    task_id: str,
    status: ApprovalStatus = ApprovalStatus.approved,
    approved_calls: list[dict[str, Any]] | None = None,
) -> str:
    """Insert an Approval on a task, decided when ``status`` is not pending.

    ``approved_calls`` defaults to empty, which is what an approval recorded
    before argument constraints existed looks like -- the state most of this
    file's tests want, since they are about the certificate gate rather than
    what a call carries.
    """
    async with AsyncSession(eng) as db:
        approval = Approval(
            workflow_execution_id=execution_id,
            workflow_task_id=task_id,
            title="Approve me",
            status=status,
            approved_calls=approved_calls or [],
            approver="alice",
            decided_at=(
                datetime.now(UTC) if status != ApprovalStatus.pending else None
            ),
            decided_by="alice" if status != ApprovalStatus.pending else None,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by="owner",
            updated_by="owner",
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        return approval.id


async def _approve(eng: AsyncEngine, approval_id: str) -> None:
    """Move a pending approval to ``approved``, as its approver's PATCH does."""
    async with AsyncSession(eng) as db:
        approval = await db.get(Approval, approval_id)
        assert approval is not None
        approval.status = ApprovalStatus.approved
        approval.decided_at = datetime.now(UTC)
        approval.decided_by = "alice"
        db.add(approval)
        await db.commit()


async def _issue(eng: AsyncEngine, approval_id: str) -> None:
    """Issue the certificate for an approval, as ``ApprovalService.resolve`` does.

    ``expire_on_commit=False`` mirrors the application's own ``get_session``:
    the service reads ``approval`` after the certificate insert commits, which
    on an expiring session would be lazy IO outside the async greenlet.
    """
    async with AsyncSession(eng, expire_on_commit=False) as db:
        approval = await db.get(Approval, approval_id)
        assert approval is not None
        service = build_mcp_tool_certificate_service(
            db, tenant_id=DEFAULT_TEST_TENANT_ID
        )
        await service.issue(approval, user_id=SYSTEM_USER_ID)


async def _grant(eng: AsyncEngine, execution_id: str, task_id: str) -> None:
    """Take out the run initiator's own grant, as starting the task does.

    Stands in for the ``_settle_certificate`` call both task-write paths make;
    the tests here seed tasks straight into the table, so nothing would
    otherwise issue the certificate a started task normally carries.
    """
    async with AsyncSession(eng, expire_on_commit=False) as db:
        service = build_mcp_tool_certificate_service(
            db, tenant_id=DEFAULT_TEST_TENANT_ID
        )
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
        await service.issue_for_started_task(task, execution, user_id=SYSTEM_USER_ID)


async def _revoke(eng: AsyncEngine, approval_id: str) -> None:
    """Revoke the certificate issued for an approval."""
    async with AsyncSession(eng, expire_on_commit=False) as db:
        result = await db.exec(
            select(McpToolCertificate).where(
                McpToolCertificate.approval_id == approval_id
            )
        )
        certificate = result.first()
        assert certificate is not None
        await SqlMcpToolCertificateRepository(
            db, tenant_id=DEFAULT_TEST_TENANT_ID
        ).revoke(certificate.id, RevocationReason.task_finished, user_id=SYSTEM_USER_ID)


# ---------------------------------------------------------------------------
# Driving a call
# ---------------------------------------------------------------------------


def _principal(credential: McpClientCredential | None = None) -> McpPrincipal:
    """Build an agent-run principal carrying the given credential."""
    return McpPrincipal(
        kind=PrincipalKind.agent_run,
        session_id=SESSION_ID,
        user_id="tester",
        credential=credential,
    )


async def _call(
    server_id: str,
    *,
    tool: str = TOOL,
    arguments: dict[str, Any] | None = None,
    present_credential: bool = True,
    mangle: bool = False,
) -> types.CallToolResult:
    """Present a credential (unless told not to) and make the proxied call.

    Args:
        server_id: The registered MCP server to call.
        tool: The tool to call.
        arguments: Call arguments, also covered by the signature.
        present_credential: When false, call with no credential at all.
        mangle: When true, present a credential whose signature was tampered
            with after being made.

    Returns:
        The tool result, when the call is allowed.
    """
    args = arguments if arguments is not None else {"path": "/etc/hosts"}
    credential = None
    if present_credential:
        credential = await ApprovalCredentialProvider().credential_for(
            session_id=SESSION_ID,
            mcp_server_id=server_id,
            tool_name=tool,
            arguments=args,
        )
        if mangle and credential is not None:
            flipped = bytearray(credential.signature)
            flipped[-1] ^= 0xFF
            credential = replace(credential, signature=bytes(flipped))
    return await McpGateway(
        policies=default_policies(), audit=SqlMcpAuditSink()
    ).call_tool(CallToolRequest(_principal(credential), server_id, tool, args))


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


async def test_approved_task_can_call_its_granted_tool(engine: AsyncEngine) -> None:
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    approval_id = await _seed_approval(
        engine, execution_id=execution_id, task_id=task_id
    )
    await _issue(engine, approval_id)

    result = await _call(server_id)

    assert result.isError is False


async def test_call_is_denied_without_a_certificate_once_an_approval_exists(
    engine: AsyncEngine,
) -> None:
    """The gate itself: an approval-gated task with no certificate cannot call."""
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    await _seed_approval(engine, execution_id=execution_id, task_id=task_id)
    # Deliberately not issued.

    with pytest.raises(McpPolicyDeniedError, match="no tool certificate"):
        await _call(server_id)


async def test_call_is_denied_while_the_approval_is_still_pending(
    engine: AsyncEngine,
) -> None:
    """Requesting an approval closes the gate immediately, before any decision."""
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    await _seed_approval(
        engine,
        execution_id=execution_id,
        task_id=task_id,
        status=ApprovalStatus.pending,
    )

    with pytest.raises(McpPolicyDeniedError, match="no tool certificate"):
        await _call(server_id)


async def test_call_is_denied_after_the_approval_is_reversed(
    engine: AsyncEngine,
) -> None:
    """A certificate is not the only stop: the approval's status is re-read."""
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    approval_id = await _seed_approval(
        engine, execution_id=execution_id, task_id=task_id
    )
    await _issue(engine, approval_id)

    async with AsyncSession(engine) as db:
        approval = await db.get(Approval, approval_id)
        assert approval is not None
        approval.status = ApprovalStatus.rejected
        db.add(approval)
        await db.commit()

    with pytest.raises(McpPolicyDeniedError, match="no longer granted"):
        await _call(server_id)


async def test_call_is_denied_once_the_certificate_is_revoked(
    engine: AsyncEngine,
) -> None:
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    approval_id = await _seed_approval(
        engine, execution_id=execution_id, task_id=task_id
    )
    await _issue(engine, approval_id)
    await _revoke(engine, approval_id)

    # With the certificate revoked the presenter finds none, so the caller gets
    # the "no certificate" denial rather than a revocation-specific one.
    with pytest.raises(McpPolicyDeniedError, match="no tool certificate"):
        await _call(server_id)


async def test_an_asking_step_in_front_of_the_acting_task_still_gates_it(
    engine: AsyncEngine,
) -> None:
    """The DAG shape a design agent produces, with the acting task named.

    "Request approval" is a step of its own and binds no tools; the work runs in
    a later task that does. Naming that later task gates it directly -- the
    narrowest case, and still the one to hold onto while the scope rule below
    widens what else a decision can reach.
    """
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    asking = await _seed_task(
        engine,
        execution_id,
        bindings=[],
        title="Request approval",
        status=WorkflowTaskStatus.completed,
    )
    acting = await _seed_task(
        engine,
        execution_id,
        bindings=[(server_id, TOOL)],
        title="Launch",
        depends_on=asking,
    )
    approval_id = await _seed_approval(
        engine,
        execution_id=execution_id,
        task_id=acting,
        status=ApprovalStatus.pending,
    )

    with pytest.raises(McpPolicyDeniedError, match="no tool certificate"):
        await _call(server_id)

    await _approve(engine, approval_id)
    await _issue(engine, approval_id)

    assert (await _call(server_id)).isError is False
    async with AsyncSession(engine) as db:
        certificate = await SqlMcpToolCertificateRepository(
            db, tenant_id=DEFAULT_TEST_TENANT_ID
        ).get_live_for_task(acting)
    assert certificate is not None
    claims = extract_claims(certificate_from_pem(certificate.certificate_pem))
    assert claims.allowed_tools == frozenset({(server_id, TOOL)})


async def test_an_approval_on_the_asking_step_gates_the_task_after_it(
    engine: AsyncEngine,
) -> None:
    """The scope rule end to end: the decision reaches the step that acts.

    The approval names the step whose only job is to ask. Before the decision
    the downstream task can call nothing even though nobody asked to approve
    *it*; after the decision it calls on the approver's authority, not on the
    run initiator's.
    """
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    asking = await _seed_task(
        engine,
        execution_id,
        bindings=[],
        title="Request approval",
        status=WorkflowTaskStatus.completed,
    )
    acting = await _seed_task(
        engine,
        execution_id,
        bindings=[(server_id, TOOL)],
        title="Launch",
        depends_on=asking,
    )
    approval_id = await _seed_approval(
        engine,
        execution_id=execution_id,
        task_id=asking,
        status=ApprovalStatus.pending,
    )

    # The initiator cannot grant it to itself either: the approval covers it.
    await _grant(engine, execution_id, acting)
    with pytest.raises(McpPolicyDeniedError, match="no tool certificate"):
        await _call(server_id)

    await _approve(engine, approval_id)
    await _issue(engine, approval_id)

    assert (await _call(server_id)).isError is False
    async with AsyncSession(engine) as db:
        certificate = await SqlMcpToolCertificateRepository(
            db, tenant_id=DEFAULT_TEST_TENANT_ID
        ).get_live_for_task(acting)
    assert certificate is not None
    assert certificate.approval_id == approval_id
    assert certificate.grant_kind is CertificateGrant.approval


async def test_a_nearer_approval_invalidates_the_outer_ones_certificate(
    engine: AsyncEngine,
) -> None:
    """A task claimed by a later request stops counting as the outer one's.

    The certificate is real, un-revoked and issued by this deployment; what
    changed is the graph. The governing approval is re-derived on every call, so
    the outer grant is refused the moment a nearer request takes the task over.
    """
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    asking = await _seed_task(
        engine,
        execution_id,
        bindings=[],
        title="Request approval",
        status=WorkflowTaskStatus.completed,
    )
    acting = await _seed_task(
        engine,
        execution_id,
        bindings=[(server_id, TOOL)],
        title="Launch",
        depends_on=asking,
    )
    outer = await _seed_approval(
        engine, execution_id=execution_id, task_id=asking, status=ApprovalStatus.pending
    )
    await _approve(engine, outer)
    await _issue(engine, outer)
    assert (await _call(server_id)).isError is False

    # A second request lands on the acting task itself, after the fact.
    await _seed_approval(
        engine, execution_id=execution_id, task_id=acting, status=ApprovalStatus.pending
    )

    with pytest.raises(McpPolicyDeniedError, match="no longer governs this task"):
        await _call(server_id)


async def test_a_merge_waits_for_every_governing_approval(
    engine: AsyncEngine,
) -> None:
    """One approver clearing their branch does not speak for the other's."""
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    left = await _seed_task(
        engine,
        execution_id,
        bindings=[],
        title="Ask left",
        status=WorkflowTaskStatus.completed,
    )
    right = await _seed_task(
        engine,
        execution_id,
        bindings=[],
        title="Ask right",
        status=WorkflowTaskStatus.completed,
    )
    merge = await _seed_task(
        engine, execution_id, bindings=[(server_id, TOOL)], title="Publish"
    )
    async with AsyncSession(engine) as db:
        db.add(WorkflowTaskDependency(task_id=merge, depends_on_id=left))
        db.add(WorkflowTaskDependency(task_id=merge, depends_on_id=right))
        await db.commit()
    left_approval = await _seed_approval(
        engine, execution_id=execution_id, task_id=left, status=ApprovalStatus.pending
    )
    right_approval = await _seed_approval(
        engine, execution_id=execution_id, task_id=right, status=ApprovalStatus.pending
    )

    await _approve(engine, left_approval)
    await _issue(engine, left_approval)
    with pytest.raises(McpPolicyDeniedError, match="no tool certificate"):
        await _call(server_id)

    await _approve(engine, right_approval)
    await _issue(engine, right_approval)
    assert (await _call(server_id)).isError is False


# ---------------------------------------------------------------------------
# The frozen grant
# ---------------------------------------------------------------------------


async def test_widening_bindings_after_approval_does_not_widen_the_grant(
    engine: AsyncEngine,
) -> None:
    """The escalation the plain tool-binding policy cannot close.

    ``update_workflow_task`` lets the execution agent rewrite its own task's
    bindings, so a rule reading bindings at call time would now allow the new
    tool. The certificate's grant was signed at decision time and still does
    not cover it.
    """
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    approval_id = await _seed_approval(
        engine, execution_id=execution_id, task_id=task_id
    )
    await _issue(engine, approval_id)

    await _bind_tool(engine, task_id, server_id, "delete_everything")

    with pytest.raises(McpPolicyDeniedError, match="was not granted"):
        await _call(server_id, tool="delete_everything")

    # The originally granted tool still works.
    assert (await _call(server_id)).isError is False


# ---------------------------------------------------------------------------
# Proof of possession
# ---------------------------------------------------------------------------


async def test_call_is_denied_when_the_signature_is_tampered_with(
    engine: AsyncEngine,
) -> None:
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    approval_id = await _seed_approval(
        engine, execution_id=execution_id, task_id=task_id
    )
    await _issue(engine, approval_id)

    with pytest.raises(McpPolicyDeniedError, match="not proven to belong"):
        await _call(server_id, mangle=True)


async def test_a_signature_does_not_transfer_to_a_different_call(
    engine: AsyncEngine,
) -> None:
    """A credential minted for one argument set must not authorize another."""
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    approval_id = await _seed_approval(
        engine, execution_id=execution_id, task_id=task_id
    )
    await _issue(engine, approval_id)

    credential = await ApprovalCredentialProvider().credential_for(
        session_id=SESSION_ID,
        mcp_server_id=server_id,
        tool_name=TOOL,
        arguments={"path": "/etc/hosts"},
    )
    assert credential is not None

    with pytest.raises(McpPolicyDeniedError, match="not proven to belong"):
        await McpGateway(
            policies=default_policies(), audit=SqlMcpAuditSink()
        ).call_tool(
            CallToolRequest(
                _principal(credential), server_id, TOOL, {"path": "/etc/shadow"}
            )
        )


async def test_a_certificate_from_another_run_is_refused(
    engine: AsyncEngine,
) -> None:
    """The binding URN is compared against the run the gateway resolved itself."""
    server_id = await _seed_server(engine)

    other_execution = await _seed_execution(engine, session_id="sess-other")
    other_task = await _seed_task(engine, other_execution, bindings=[(server_id, TOOL)])
    other_approval = await _seed_approval(
        engine, execution_id=other_execution, task_id=other_task
    )
    await _issue(engine, other_approval)

    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    await _seed_approval(engine, execution_id=execution_id, task_id=task_id)

    # Present the *other* run's credential against this run.
    stolen = await ApprovalCredentialProvider().credential_for(
        session_id="sess-other",
        mcp_server_id=server_id,
        tool_name=TOOL,
        arguments={"path": "/etc/hosts"},
    )
    assert stolen is not None

    with pytest.raises(McpPolicyDeniedError, match="different run"):
        await McpGateway(
            policies=default_policies(), audit=SqlMcpAuditSink()
        ).call_tool(
            CallToolRequest(_principal(stolen), server_id, TOOL, {"path": "/etc/hosts"})
        )


# ---------------------------------------------------------------------------
# The initiator's own grant
# ---------------------------------------------------------------------------


async def test_task_without_an_approval_calls_on_its_initiators_grant(
    engine: AsyncEngine,
) -> None:
    """A task nobody approved still calls -- on the run initiator's authority."""
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    await _grant(engine, execution_id, task_id)

    result = await _call(server_id)

    assert result.isError is False
    async with AsyncSession(engine) as db:
        certificate = await SqlMcpToolCertificateRepository(
            db, tenant_id=DEFAULT_TEST_TENANT_ID
        ).get_live_for_task(task_id)
    assert certificate is not None
    assert certificate.grant_kind is CertificateGrant.initiator
    assert certificate.approval_id is None
    assert certificate.granted_by == "owner"


async def test_a_task_with_no_grant_at_all_cannot_call(engine: AsyncEngine) -> None:
    """The rule with no exemption: a bound tool alone authorizes nothing.

    This is the case that used to be allowed -- an in-progress task binding the
    tool, with no approval anywhere near it -- and closing it is the point of
    requiring a certificate on every call.
    """
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])

    with pytest.raises(McpPolicyDeniedError, match="no tool certificate"):
        await _call(server_id)


async def test_widening_bindings_after_the_grant_does_not_widen_it(
    engine: AsyncEngine,
) -> None:
    """The freeze applies to an initiator grant exactly as to an approved one.

    The agent starts a task, then binds another tool to it and tries to call
    that. The grant was signed over the bindings the task had when it started.
    """
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    await _grant(engine, execution_id, task_id)

    await _bind_tool(engine, task_id, server_id, "delete_everything")

    with pytest.raises(McpPolicyDeniedError, match="was not granted"):
        await _call(server_id, tool="delete_everything")

    assert (await _call(server_id)).isError is False


async def test_a_grant_is_not_issued_for_a_task_that_has_an_approval(
    engine: AsyncEngine,
) -> None:
    """A task with an approval is the approver's to authorize, not the initiator's.

    Otherwise a run could start a task, pocket its initiator grant, and only
    then request the approval it was supposed to be waiting for.
    """
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    await _seed_approval(
        engine,
        execution_id=execution_id,
        task_id=task_id,
        status=ApprovalStatus.pending,
    )

    await _grant(engine, execution_id, task_id)

    async with AsyncSession(engine) as db:
        certificate = await SqlMcpToolCertificateRepository(
            db, tenant_id=DEFAULT_TEST_TENANT_ID
        ).get_live_for_task(task_id)
    assert certificate is None
    with pytest.raises(McpPolicyDeniedError, match="no tool certificate"):
        await _call(server_id)


async def test_an_approval_arriving_later_stands_the_initiator_grant_down(
    engine: AsyncEngine,
) -> None:
    """The other order: the task starts first, the approval is requested after.

    The policy refuses the standing initiator grant on its own -- this asserts
    that, not merely that ``supersede_initiator_grant`` stamped the row.
    """
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    await _grant(engine, execution_id, task_id)
    assert (await _call(server_id)).isError is False

    await _seed_approval(
        engine,
        execution_id=execution_id,
        task_id=task_id,
        status=ApprovalStatus.pending,
    )

    with pytest.raises(McpPolicyDeniedError, match="now needs an approval"):
        await _call(server_id)


async def test_an_initiator_grant_naming_the_wrong_user_is_refused(
    engine: AsyncEngine,
) -> None:
    """The claimed initiator is compared against the run's own ``initiator_id``."""
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    await _grant(engine, execution_id, task_id)

    async with AsyncSession(engine) as db:
        execution = await db.get(WorkflowExecution, execution_id)
        assert execution is not None
        execution.initiator_id = "alice"
        db.add(execution)
        await db.commit()

    with pytest.raises(McpPolicyDeniedError, match="not granted by this run"):
        await _call(server_id)


async def test_a_second_task_binding_the_same_tool_supplies_its_own_grant(
    engine: AsyncEngine,
) -> None:
    """The gate is per-tool, not per-run.

    Two tasks are underway and both bind this tool; only one needs an approval.
    The other carries its initiator's grant, which legitimately authorizes the
    call -- so a workflow that never asked for an approval keeps working, and
    the certificate it presents is that task's, not the gated one's.
    """
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    gated_task = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    open_task = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    await _seed_approval(engine, execution_id=execution_id, task_id=gated_task)
    await _grant(engine, execution_id, open_task)

    result = await _call(server_id)

    assert result.isError is False
    row = (await _invocations(engine))[0]
    assert row.workflow_task_id == open_task
    assert row.approval_id is None


async def test_unbound_tool_is_still_refused_by_the_binding_policy(
    engine: AsyncEngine,
) -> None:
    """The cheaper rule still runs first and still produces its own message."""
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    await _grant(engine, execution_id, task_id)

    with pytest.raises(McpPolicyDeniedError, match="is not bound to"):
        await _call(server_id, tool="something_else")


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


async def _invocations(eng: AsyncEngine) -> list[MCPToolInvocation]:
    """Return every recorded tool-call decision, oldest first."""
    async with AsyncSession(eng) as db:
        result = await db.exec(
            select(MCPToolInvocation).order_by(col(MCPToolInvocation.created_at))
        )
        return list(result.all())


async def test_an_allowed_call_is_recorded_with_its_certificate(
    engine: AsyncEngine,
) -> None:
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    approval_id = await _seed_approval(
        engine, execution_id=execution_id, task_id=task_id
    )
    await _issue(engine, approval_id)

    await _call(server_id)

    rows = await _invocations(engine)
    assert len(rows) == 1
    row = rows[0]
    assert row.decision is McpAuditDecision.allowed
    assert row.denial_reason is None
    assert row.workflow_execution_id == execution_id
    assert row.workflow_task_id == task_id
    assert row.approval_id == approval_id
    assert row.certificate_serial is not None
    assert row.signature is not None
    assert row.nonce is not None
    assert row.signed_at is not None


async def test_a_denied_call_is_recorded_with_the_reason(engine: AsyncEngine) -> None:
    """A refusal is the case an audit trail most needs to keep."""
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    await _seed_approval(engine, execution_id=execution_id, task_id=task_id)

    with pytest.raises(McpPolicyDeniedError):
        await _call(server_id)

    rows = await _invocations(engine)
    assert len(rows) == 1
    assert rows[0].decision is McpAuditDecision.denied
    assert "no tool certificate" in (rows[0].denial_reason or "")
    assert rows[0].certificate_serial is None


async def test_a_call_without_a_certificate_is_still_recorded(
    engine: AsyncEngine,
) -> None:
    """A call presenting nothing is refused, and still tied to what it asked for.

    The row is what makes the refusal investigable: it names the tool and the
    arguments digest even though no certificate identified the caller.
    """
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])

    with pytest.raises(McpPolicyDeniedError):
        await _call(server_id, present_credential=False)

    rows = await _invocations(engine)
    assert len(rows) == 1
    assert rows[0].decision is McpAuditDecision.denied
    assert rows[0].certificate_serial is None
    assert rows[0].signature is None
    assert rows[0].arguments_digest


async def test_arguments_are_recorded_only_as_a_digest(engine: AsyncEngine) -> None:
    """Tool arguments carry the very data the approval was needed for."""
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    await _grant(engine, execution_id, task_id)

    await _call(server_id, arguments={"secret": "hunter2"})

    row = (await _invocations(engine))[0]
    assert "hunter2" not in row.model_dump_json()
    assert row.arguments_digest == hash_arguments({"secret": "hunter2"})


async def test_listings_are_not_recorded(engine: AsyncEngine) -> None:
    """Listings have no side effect; recording them would bury the calls."""
    await _seed_server(engine)
    await _seed_execution(engine)

    await McpGateway(policies=default_policies(), audit=SqlMcpAuditSink()).list_tools(
        ListToolsRequest(_principal())
    )

    assert await _invocations(engine) == []


async def test_a_recorded_call_can_be_verified_from_the_audit_row_alone(
    engine: AsyncEngine,
) -> None:
    """The non-repudiation claim, checked the way an auditor would.

    Nothing here trusts the audit table: the digest is rebuilt from its columns,
    the signature is checked against the certificate's public key, and the
    certificate is checked against the root. Tamper with any recorded field and
    the signature stops verifying.
    """
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    approval_id = await _seed_approval(
        engine, execution_id=execution_id, task_id=task_id
    )
    await _issue(engine, approval_id)

    await _call(server_id, arguments={"path": "/etc/hosts"})

    row = (await _invocations(engine))[0]
    assert row.signature is not None
    assert row.nonce is not None
    assert row.signed_at is not None
    assert row.certificate_serial is not None

    async with AsyncSession(engine) as db:
        certificates = SqlMcpToolCertificateRepository(
            db, tenant_id=DEFAULT_TEST_TENANT_ID
        )
        stored = await certificates.get_by_serial(row.certificate_serial)
        ca = await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(db))
    assert stored is not None

    leaf = certificate_from_pem(stored.certificate_pem)
    # The certificate really was issued by this deployment.
    verify_certificate(
        leaf, ca_certificate=ca.certificate, now=leaf.not_valid_before_utc
    )

    # SQLite discards the offset; the signer used UTC.
    digest = pop_digest_from_parts(
        session_id=row.session_id,
        mcp_server_id=row.mcp_server_id,
        tool_name=row.tool_name,
        arguments_hash=row.arguments_digest,
        nonce=row.nonce,
        timestamp=row.signed_at.replace(tzinfo=UTC),
    )
    public_key = leaf.public_key()
    assert isinstance(public_key, ec.EllipticCurvePublicKey)
    public_key.verify(base64.b64decode(row.signature), digest, ec.ECDSA(HASH_ALGORITHM))

    # And a tampered record does not verify.
    tampered = pop_digest_from_parts(
        session_id=row.session_id,
        mcp_server_id=row.mcp_server_id,
        tool_name="delete_everything",
        arguments_hash=row.arguments_digest,
        nonce=row.nonce,
        timestamp=row.signed_at.replace(tzinfo=UTC),
    )
    with pytest.raises(InvalidSignature):
        public_key.verify(
            base64.b64decode(row.signature), tampered, ec.ECDSA(HASH_ALGORITHM)
        )


async def test_an_audit_failure_does_not_break_the_call(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken sink must not turn an allowed call into a refused one."""
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    await _grant(engine, execution_id, task_id)

    async def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("audit backend is down")

    monkeypatch.setattr(SqlMcpAuditSink, "record", boom)

    result = await _call(server_id)

    assert result.isError is False


# ---------------------------------------------------------------------------
# The approved arguments
# ---------------------------------------------------------------------------


def _declaration(server_id: str, **arguments: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a declaration over ``TOOL`` on one server.

    Args:
        server_id: The MCP server the declared call targets.
        **arguments: Argument name to its constraint object.

    Returns:
        The ``approved_calls`` payload an Approval row carries.
    """
    return [{"mcp_server_id": server_id, "tool_name": TOOL, "arguments": arguments}]


async def test_a_conforming_call_passes_the_argument_gate(
    engine: AsyncEngine,
) -> None:
    """The whole point: the arguments the approver approved go through."""
    srv = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(srv, TOOL)])
    approval_id = await _seed_approval(
        engine,
        execution_id=execution_id,
        task_id=task_id,
        approved_calls=_declaration(srv, path={"eq": "/etc/hosts"}),
    )
    await _issue(engine, approval_id)

    assert (await _call(srv, arguments={"path": "/etc/hosts"})).isError is False


async def test_a_deviating_argument_value_is_denied(engine: AsyncEngine) -> None:
    """The gap this closes: the tool is granted, this argument is not."""
    srv = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(srv, TOOL)])
    approval_id = await _seed_approval(
        engine,
        execution_id=execution_id,
        task_id=task_id,
        approved_calls=_declaration(srv, path={"eq": "/etc/hosts"}),
    )
    await _issue(engine, approval_id)

    with pytest.raises(McpPolicyDeniedError, match="outside what the approver"):
        await _call(srv, arguments={"path": "/etc/shadow"})


async def test_an_undeclared_argument_is_denied(engine: AsyncEngine) -> None:
    """The strict allowlist, end to end."""
    srv = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(srv, TOOL)])
    approval_id = await _seed_approval(
        engine,
        execution_id=execution_id,
        task_id=task_id,
        approved_calls=_declaration(srv, path={"eq": "/etc/hosts"}),
    )
    await _issue(engine, approval_id)

    with pytest.raises(McpPolicyDeniedError, match="follow_symlinks"):
        await _call(srv, arguments={"path": "/etc/hosts", "follow_symlinks": True})


async def test_a_declared_argument_the_call_omits_is_denied(
    engine: AsyncEngine,
) -> None:
    srv = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(srv, TOOL)])
    approval_id = await _seed_approval(
        engine,
        execution_id=execution_id,
        task_id=task_id,
        approved_calls=_declaration(srv, path={"eq": "/etc/hosts"}),
    )
    await _issue(engine, approval_id)

    with pytest.raises(McpPolicyDeniedError, match="omits it"):
        await _call(srv, arguments={})


async def test_a_granted_tool_the_declaration_omits_is_denied(
    engine: AsyncEngine,
) -> None:
    """The certificate is no longer the last word once a declaration exists."""
    srv = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(srv, TOOL)])
    approval_id = await _seed_approval(
        engine,
        execution_id=execution_id,
        task_id=task_id,
        # Names a different tool than the one the task binds, and that the
        # certificate therefore grants.
        approved_calls=[
            {"mcp_server_id": srv, "tool_name": "write_file", "arguments": {}}
        ],
    )
    await _issue(engine, approval_id)

    with pytest.raises(McpPolicyDeniedError, match="does not authorize tool"):
        await _call(srv, arguments={"path": "/etc/hosts"})


async def test_an_approval_with_no_declaration_does_not_constrain_arguments(
    engine: AsyncEngine,
) -> None:
    """A request recorded before this rule existed keeps working.

    No path exists by which an approver could supply a declaration after the
    fact, so denying here would wedge every approval in flight at deploy time.
    """
    srv = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(srv, TOOL)])
    approval_id = await _seed_approval(
        engine, execution_id=execution_id, task_id=task_id
    )
    await _issue(engine, approval_id)

    assert (await _call(srv, arguments={"anything": "at all"})).isError is False


async def test_an_initiator_grant_is_not_argument_constrained(
    engine: AsyncEngine,
) -> None:
    """No approver, so nothing to have deviated from."""
    srv = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(srv, TOOL)])
    await _grant(engine, execution_id, task_id)

    assert (await _call(srv, arguments={"path": "/anything"})).isError is False


async def test_a_merge_must_satisfy_every_governing_declaration(
    engine: AsyncEngine,
) -> None:
    """The laxer approver's declaration must not speak for the stricter one's."""
    srv = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    left = await _seed_task(
        engine,
        execution_id,
        bindings=[],
        title="Ask left",
        status=WorkflowTaskStatus.completed,
    )
    right = await _seed_task(
        engine,
        execution_id,
        bindings=[],
        title="Ask right",
        status=WorkflowTaskStatus.completed,
    )
    merge = await _seed_task(
        engine, execution_id, bindings=[(srv, TOOL)], title="Publish"
    )
    async with AsyncSession(engine) as db:
        db.add(WorkflowTaskDependency(task_id=merge, depends_on_id=left))
        db.add(WorkflowTaskDependency(task_id=merge, depends_on_id=right))
        await db.commit()

    left_approval = await _seed_approval(
        engine,
        execution_id=execution_id,
        task_id=left,
        approved_calls=_declaration(srv, path={"in": ["/etc/hosts", "/etc/motd"]}),
    )
    right_approval = await _seed_approval(
        engine,
        execution_id=execution_id,
        task_id=right,
        approved_calls=_declaration(srv, path={"eq": "/etc/motd"}),
    )
    await _issue(engine, left_approval)
    await _issue(engine, right_approval)

    # Inside the left approval's set, outside the right's.
    with pytest.raises(McpPolicyDeniedError, match="outside what the approver"):
        await _call(srv, arguments={"path": "/etc/hosts"})

    # Inside both.
    assert (await _call(srv, arguments={"path": "/etc/motd"})).isError is False


async def test_a_denied_argument_is_audited_without_its_value(
    engine: AsyncEngine,
) -> None:
    """The reason is stored raw beside a digest that exists to withhold the value."""
    srv = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(srv, TOOL)])
    approval_id = await _seed_approval(
        engine,
        execution_id=execution_id,
        task_id=task_id,
        approved_calls=_declaration(srv, path={"eq": "/etc/hosts"}),
    )
    await _issue(engine, approval_id)

    secret = "/etc/very-secret-path"
    with pytest.raises(McpPolicyDeniedError):
        await _call(srv, arguments={"path": secret})

    async with AsyncSession(engine) as db:
        rows = (await db.exec(select(MCPToolInvocation))).all()
    assert len(rows) == 1
    assert rows[0].decision is McpAuditDecision.denied
    assert rows[0].denial_reason is not None
    assert "path" in rows[0].denial_reason
    assert secret not in rows[0].denial_reason


# ---------------------------------------------------------------------------
# Tools the workflow design exempted from input approval
# ---------------------------------------------------------------------------


def _unconstrained(server_id: str, tool_name: str = TOOL) -> dict[str, Any]:
    """Build the entry the request path writes for an exempt tool.

    Args:
        server_id: The MCP server the entry covers.
        tool_name: The tool the entry covers.

    Returns:
        One ``approved_calls`` entry permitting any arguments.
    """
    return {
        "mcp_server_id": server_id,
        "tool_name": tool_name,
        "arguments": {},
        "unconstrained_arguments": True,
    }


async def test_an_exempt_tool_accepts_arguments_nobody_declared(
    engine: AsyncEngine,
) -> None:
    """What the exemption buys: a read-only tool the run may explore with."""
    srv = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(srv, TOOL)])
    approval_id = await _seed_approval(
        engine,
        execution_id=execution_id,
        task_id=task_id,
        approved_calls=[_unconstrained(srv)],
    )
    await _issue(engine, approval_id)

    assert (await _call(srv, arguments={"path": "/anything/at/all"})).isError is False


async def test_an_exempt_tool_is_still_gated_by_the_approval(
    engine: AsyncEngine,
) -> None:
    """The exemption drops the argument bounds, never the decision itself.

    Nothing issues a certificate while the approval is pending, so the call has
    none to present and the certificate policy refuses it before the argument
    rule is ever reached.
    """
    srv = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(engine, execution_id, bindings=[(srv, TOOL)])
    approval_id = await _seed_approval(
        engine,
        execution_id=execution_id,
        task_id=task_id,
        status=ApprovalStatus.pending,
        approved_calls=[_unconstrained(srv)],
    )
    await _issue(engine, approval_id)

    with pytest.raises(McpPolicyDeniedError):
        await _call(srv, arguments={"path": "/anything/at/all"})


async def test_exempting_one_tool_leaves_the_others_bounded(
    engine: AsyncEngine,
) -> None:
    """The declaration is per tool, so the destructive one keeps its bounds."""
    srv = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(
        engine, execution_id, bindings=[(srv, TOOL), (srv, "write_file")]
    )
    approval_id = await _seed_approval(
        engine,
        execution_id=execution_id,
        task_id=task_id,
        approved_calls=[
            _unconstrained(srv),
            {
                "mcp_server_id": srv,
                "tool_name": "write_file",
                "arguments": {"path": {"eq": "/tmp/report"}},
            },
        ],
    )
    await _issue(engine, approval_id)

    assert (await _call(srv, arguments={"path": "/etc/shadow"})).isError is False
    with pytest.raises(McpPolicyDeniedError, match="outside what the approver"):
        await _call(srv, tool="write_file", arguments={"path": "/etc/passwd"})


async def test_an_exempt_tool_does_not_authorize_a_tool_beside_it(
    engine: AsyncEngine,
) -> None:
    """An entry permitting any arguments still permits only its own tool."""
    srv = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    task_id = await _seed_task(
        engine, execution_id, bindings=[(srv, TOOL), (srv, "write_file")]
    )
    approval_id = await _seed_approval(
        engine,
        execution_id=execution_id,
        task_id=task_id,
        approved_calls=[_unconstrained(srv)],
    )
    await _issue(engine, approval_id)

    with pytest.raises(McpPolicyDeniedError, match="does not authorize tool"):
        await _call(srv, tool="write_file", arguments={"path": "/tmp/report"})
