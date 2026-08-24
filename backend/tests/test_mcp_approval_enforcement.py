"""End-to-end tests of the approval gate on MCP tool calls.

Drives the real presenter (:mod:`infrastructure.mcp_credentials`) and the real
verifier (:class:`infrastructure.mcp_proxy.McpProxy` with the default policy
chain) against an in-memory database, faking only the remote MCP traffic. That
is the combination the enforcement claim actually rests on, so the cases here
are the ones worth reading first:

* `test_call_is_denied_without_a_certificate_once_an_approval_exists` -- the
  gate itself.
* `test_widening_bindings_after_approval_does_not_widen_the_grant` -- the
  escalation path that the plain tool-binding policy cannot close.
* `test_task_without_an_approval_still_works` -- the compatibility promise:
  workflows that never request an approval are untouched.
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
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.mcp_audit import SqlMcpAuditSink
from infrastructure.mcp_ca import (
    HASH_ALGORITHM,
    certificate_from_pem,
    load_or_create_root_ca,
)
from infrastructure.mcp_certificate import (
    arguments_digest as hash_arguments,
)
from infrastructure.mcp_certificate import (
    pop_digest_from_parts,
    verify_certificate,
)
from infrastructure.mcp_client import McpConnection
from infrastructure.mcp_credentials import ApprovalCredentialProvider
from infrastructure.mcp_policies import default_policies
from infrastructure.mcp_proxy import (
    CallToolRequest,
    ListToolsRequest,
    McpClientCredential,
    McpPolicyDeniedError,
    McpPrincipal,
    McpProxy,
    PrincipalKind,
)
from infrastructure.secret_cipher import get_secret_cipher
from models.approval import Approval, ApprovalStatus
from models.approval_certificate import ApprovalCertificate, RevocationReason
from models.mcp_server import MCPServer, McpTransport
from models.mcp_tool_invocation import McpAuditDecision, MCPToolInvocation
from models.user import SYSTEM_USER_ID
from models.workflow_execution import WorkflowExecution
from models.workflow_task import (
    WorkflowTask,
    WorkflowTaskStatus,
    WorkflowTaskToolBinding,
)
from repositories.approval_certificate import SqlApprovalCertificateRepository
from repositories.mcp_ca import SqlMcpCertificateAuthorityRepository
from repositories.mcp_server import SqlMCPServerRepository
from repositories.workflow_execution import SqlWorkflowExecutionRepository
from repositories.workflow_task import SqlWorkflowTaskRepository
from services.approval_certificate import ApprovalCertificateService
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users

SESSION_ID = "sess-approval"
TOOL = "read_file"


@pytest_asyncio.fixture()
async def engine(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[AsyncEngine, None]:
    """Yield an in-memory engine and point the module-level engine at it."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

    @sa_event.listens_for(eng.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
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
    eng: AsyncEngine, execution_id: str, *, bindings: list[tuple[str, str]]
) -> str:
    """Insert an in-progress WorkflowTask with the given tool bindings."""
    async with AsyncSession(eng) as db:
        task = WorkflowTask(
            workflow_execution_id=execution_id,
            title="Step",
            status=WorkflowTaskStatus.in_progress,
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
) -> str:
    """Insert an Approval on a task, decided when ``status`` is not pending."""
    async with AsyncSession(eng) as db:
        approval = Approval(
            workflow_execution_id=execution_id,
            workflow_task_id=task_id,
            title="Approve me",
            status=status,
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


async def _issue(eng: AsyncEngine, approval_id: str) -> None:
    """Issue the certificate for an approval, as ``ApprovalService.resolve`` does.

    ``expire_on_commit=False`` mirrors the application's own ``get_session``:
    the service reads ``approval`` after the certificate insert commits, which
    on an expiring session would be lazy IO outside the async greenlet.
    """
    async with AsyncSession(eng, expire_on_commit=False) as db:
        approval = await db.get(Approval, approval_id)
        assert approval is not None
        execution_repo = SqlWorkflowExecutionRepository(
            db, tenant_id=DEFAULT_TEST_TENANT_ID
        )
        service = ApprovalCertificateService(
            SqlApprovalCertificateRepository(db, tenant_id=DEFAULT_TEST_TENANT_ID),
            SqlWorkflowTaskRepository(
                db,
                execution_repo,
                SqlMCPServerRepository(db, tenant_id=DEFAULT_TEST_TENANT_ID),
                tenant_id=DEFAULT_TEST_TENANT_ID,
            ),
            SqlMcpCertificateAuthorityRepository(db),
            get_secret_cipher(),
        )
        await service.issue(approval, user_id=SYSTEM_USER_ID)


async def _revoke(eng: AsyncEngine, approval_id: str) -> None:
    """Revoke the certificate issued for an approval."""
    async with AsyncSession(eng, expire_on_commit=False) as db:
        result = await db.exec(
            select(ApprovalCertificate).where(
                ApprovalCertificate.approval_id == approval_id
            )
        )
        certificate = result.first()
        assert certificate is not None
        await SqlApprovalCertificateRepository(
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
    return await McpProxy(
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

    with pytest.raises(McpPolicyDeniedError, match="requires an approval"):
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

    with pytest.raises(McpPolicyDeniedError, match="requires an approval"):
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
    # the "needs an approval" denial rather than a revocation-specific one.
    with pytest.raises(McpPolicyDeniedError, match="requires an approval"):
        await _call(server_id)


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
        await McpProxy(policies=default_policies(), audit=SqlMcpAuditSink()).call_tool(
            CallToolRequest(
                _principal(credential), server_id, TOOL, {"path": "/etc/shadow"}
            )
        )


async def test_a_certificate_from_another_run_is_refused(
    engine: AsyncEngine,
) -> None:
    """The binding URN is compared against the run the proxy resolved itself."""
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
        await McpProxy(policies=default_policies(), audit=SqlMcpAuditSink()).call_tool(
            CallToolRequest(_principal(stolen), server_id, TOOL, {"path": "/etc/hosts"})
        )


# ---------------------------------------------------------------------------
# Compatibility
# ---------------------------------------------------------------------------


async def test_task_without_an_approval_still_works(engine: AsyncEngine) -> None:
    """Workflows that never request an approval are untouched by the gate."""
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])

    result = await _call(server_id, present_credential=False)

    assert result.isError is False


async def test_an_unapproved_task_binding_the_same_tool_keeps_it_callable(
    engine: AsyncEngine,
) -> None:
    """The gate is per-tool, not per-run.

    Two tasks are underway and both bind this tool; only one needs an approval.
    The other legitimately authorizes the call under the plain binding rule, so
    demanding a certificate would break a workflow that never asked for one.
    """
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    gated_task = await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])
    await _seed_approval(engine, execution_id=execution_id, task_id=gated_task)

    result = await _call(server_id, present_credential=False)

    assert result.isError is False


async def test_unbound_tool_is_still_refused_by_the_binding_policy(
    engine: AsyncEngine,
) -> None:
    """The cheaper rule still runs first and still produces its own message."""
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])

    with pytest.raises(McpPolicyDeniedError, match="is not bound to"):
        await _call(server_id, tool="something_else", present_credential=False)


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
    assert "requires an approval" in (rows[0].denial_reason or "")
    assert rows[0].certificate_serial is None


async def test_a_call_without_a_certificate_is_still_recorded(
    engine: AsyncEngine,
) -> None:
    """An unauthenticated call is still tied to what it asked for."""
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])

    await _call(server_id, present_credential=False)

    rows = await _invocations(engine)
    assert len(rows) == 1
    assert rows[0].decision is McpAuditDecision.allowed
    assert rows[0].certificate_serial is None
    assert rows[0].signature is None
    assert rows[0].arguments_digest


async def test_arguments_are_recorded_only_as_a_digest(engine: AsyncEngine) -> None:
    """Tool arguments carry the very data the approval was needed for."""
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(engine)
    await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])

    await _call(server_id, arguments={"secret": "hunter2"}, present_credential=False)

    row = (await _invocations(engine))[0]
    assert "hunter2" not in row.model_dump_json()
    assert row.arguments_digest == hash_arguments({"secret": "hunter2"})


async def test_listings_are_not_recorded(engine: AsyncEngine) -> None:
    """Listings have no side effect; recording them would bury the calls."""
    await _seed_server(engine)
    await _seed_execution(engine)

    await McpProxy(policies=default_policies(), audit=SqlMcpAuditSink()).list_tools(
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
        certificates = SqlApprovalCertificateRepository(
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
    await _seed_task(engine, execution_id, bindings=[(server_id, TOOL)])

    async def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("audit backend is down")

    monkeypatch.setattr(SqlMcpAuditSink, "record", boom)

    result = await _call(server_id, present_credential=False)

    assert result.isError is False
