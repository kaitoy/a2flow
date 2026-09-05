"""Tests for the MCP gateway layer and its policy chain.

Covers ``infrastructure.mcp_gateway`` (authentication, the policy chain, secret
expansion, session lifetime) and ``infrastructure.mcp_policies`` (the
in-progress tool-binding rule) directly, below the ADK tool functions that
``tests/test_mcp_tools.py`` drives.

Like those tests, each case monkeypatches the module-level database engine to
a throwaway database and fakes remote MCP traffic by
monkeypatching ``infrastructure.mcp_client``.
"""

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
import pytest_asyncio
from mcp import types
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure import database
from infrastructure.mcp_client import HttpConnection, McpConnection, StdioConnection
from infrastructure.mcp_credentials import ApprovalCredentialProvider
from infrastructure.mcp_gateway import (
    MOCKED_META_KEY,
    AgentRunAuthenticator,
    CallToolRequest,
    ListToolsRequest,
    McpAuthenticationError,
    McpCallContext,
    McpClientCredential,
    McpGateway,
    McpIdentity,
    McpOperation,
    McpPolicyDeniedError,
    McpPrincipal,
    McpServerUnknownError,
    McpServerUnusableError,
    McpUpstreamError,
    PrincipalKind,
)
from infrastructure.mcp_policies import (
    InProgressToolBindingPolicy,
    PassThroughPolicy,
    default_policies,
)
from infrastructure.secret_cipher import get_secret_cipher
from models.agent_skill import AgentSkill
from models.mcp_server import MCPServer, McpTransport
from models.mcp_tool_invocation import McpAuditDecision
from models.secret import Secret, SecretType
from models.user import SYSTEM_USER_ID
from models.workflow import Workflow
from models.workflow_execution import WorkflowExecution
from models.workflow_task import (
    WorkflowTask,
    WorkflowTaskStatus,
    WorkflowTaskToolBinding,
)
from repositories.exceptions import McpConnectionError
from tests._engine import make_test_engine
from tests._seed import (
    DEFAULT_TEST_TENANT_ID,
    grant_tool_certificate,
    seed_tenant,
    seed_users,
)


@pytest_asyncio.fixture()
async def engine(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[AsyncEngine, None]:
    """Yield a throwaway engine and point the gateway's module-level engine at it."""
    eng = await make_test_engine()
    await seed_users(eng)
    await seed_tenant(eng)

    monkeypatch.setattr("infrastructure.database.engine", eng)
    yield eng
    await eng.dispose()


def _principal(
    session_id: str = "sess-abc",
    user_id: str = "tester",
    *,
    credential: McpClientCredential | None = None,
) -> McpPrincipal:
    """Build an agent-run principal for the given ADK session id."""
    return McpPrincipal(
        kind=PrincipalKind.agent_run,
        session_id=session_id,
        user_id=user_id,
        credential=credential,
    )


async def _seed_server(
    eng: AsyncEngine,
    *,
    name: str = "srv",
    url: str = "https://mcp.example.com/mcp",
    headers: dict[str, str] | None = None,
    tenant_id: str = DEFAULT_TEST_TENANT_ID,
) -> str:
    """Insert a streamable-HTTP MCPServer and return its id."""
    async with AsyncSession(eng) as db:
        server = MCPServer(
            name=name,
            transport=McpTransport.streamable_http,
            url=url,
            headers=headers or {},
            tenant_id=tenant_id,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server.id


async def _seed_stdio_server(
    eng: AsyncEngine,
    *,
    name: str = "stdio-srv",
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Insert a stdio MCPServer and return its id."""
    async with AsyncSession(eng) as db:
        server = MCPServer(
            name=name,
            transport=McpTransport.stdio,
            command="npx",
            args=args if args is not None else ["-y", "pkg"],
            env=env or {},
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server.id


async def _seed_session(eng: AsyncEngine, *, session_id: str = "sess-abc") -> str:
    """Insert a WorkflowExecution with the given ADK session id and return its PK."""
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
            initiator_id=SYSTEM_USER_ID,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)
        return execution.id


async def _seed_design_session(
    eng: AsyncEngine, *, session_id: str = "design-abc"
) -> str:
    """Insert a skill + workflow whose design session is ``session_id``."""
    async with AsyncSession(eng) as db:
        skill = AgentSkill(
            name=f"skill-{session_id}",
            repo_url="https://example.com/repo",
            repo_path="",
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(skill)
        await db.commit()
        await db.refresh(skill)

        workflow = Workflow(
            name=f"wf-{session_id}",
            agent_skill_id=skill.id,
            session_id=session_id,
            agent_skill_commit_sha="a" * 40,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)
        return workflow.id


async def _seed_task(
    eng: AsyncEngine,
    execution_id: str,
    *,
    status: WorkflowTaskStatus = WorkflowTaskStatus.in_progress,
    bindings: list[tuple[str, str]] | None = None,
) -> str:
    """Insert a WorkflowTask with optional ``(server_id, tool_name)`` bindings."""
    async with AsyncSession(eng) as db:
        task = WorkflowTask(
            workflow_execution_id=execution_id,
            title="Step",
            status=status,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        task_id = task.id
        for server_id, tool_name in bindings or []:
            db.add(
                WorkflowTaskToolBinding(
                    task_id=task_id, mcp_server_id=server_id, tool_name=tool_name
                )
            )
        await db.commit()
    # Seeding a task skips the service that would have granted it a certificate,
    # without which the default policy chain refuses every call it makes.
    await grant_tool_certificate(eng, execution_id, task_id)
    return task_id


async def _seed_local_secret(eng: AsyncEngine, name: str, value: str) -> None:
    """Insert a local Secret holding one ``k`` entry encrypted with the cipher."""
    async with AsyncSession(eng) as db:
        db.add(
            Secret(
                name=name,
                type=SecretType.local,
                entries={"k": get_secret_cipher().encrypt(value)},
                tenant_id=DEFAULT_TEST_TENANT_ID,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await db.commit()


def _tool_result(text: str = "ok", *, is_error: bool = False) -> types.CallToolResult:
    """Build a CallToolResult with a single text block."""
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)], isError=is_error
    )


class _RecordingPolicy:
    """Test policy that records every context it sees, optionally denying."""

    def __init__(self, log: list[str], label: str, *, deny: bool = False) -> None:
        """Initialize the policy.

        Args:
            log: Shared list every consultation appends this policy's label to.
            label: How this policy identifies itself in ``log``.
            deny: Whether to veto every operation it is consulted about.
        """
        self.log = log
        self.label = label
        self.deny = deny
        self.contexts: list[McpCallContext] = []

    async def authorize(self, ctx: McpCallContext, db: AsyncSession) -> None:
        """Record the consultation and deny when configured to."""
        self.log.append(self.label)
        self.contexts.append(ctx)
        if self.deny:
            raise McpPolicyDeniedError(f"denied by {self.label}")


# ---------- authentication ----------


async def test_authenticator_resolves_an_execution_run(engine: AsyncEngine) -> None:
    execution_id = await _seed_session(engine)
    async with AsyncSession(engine) as db:
        identity = await AgentRunAuthenticator().authenticate(_principal(), db)
    assert identity == McpIdentity(
        tenant_id=DEFAULT_TEST_TENANT_ID, execution_id=execution_id, user_id="tester"
    )


async def test_authenticator_resolves_a_design_session_without_an_execution(
    engine: AsyncEngine,
) -> None:
    await _seed_design_session(engine, session_id="design-1")
    async with AsyncSession(engine) as db:
        identity = await AgentRunAuthenticator().authenticate(
            _principal("design-1"), db
        )
    assert identity.tenant_id == DEFAULT_TEST_TENANT_ID
    assert identity.execution_id is None


async def test_authenticator_rejects_an_unknown_session(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as db:
        with pytest.raises(McpAuthenticationError):
            await AgentRunAuthenticator().authenticate(_principal("nope"), db)


async def test_authenticator_rejects_a_missing_session_id(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as db:
        with pytest.raises(McpAuthenticationError):
            await AgentRunAuthenticator().authenticate(_principal(""), db)


async def test_call_tool_restates_an_auth_failure_for_its_operation(
    engine: AsyncEngine,
) -> None:
    with pytest.raises(McpAuthenticationError) as excinfo:
        await McpGateway().call_tool(
            CallToolRequest(_principal("nope"), "srv", "search", {})
        )
    assert "cannot use MCP tools" in excinfo.value.message


async def test_list_tools_restates_an_auth_failure_for_its_operation(
    engine: AsyncEngine,
) -> None:
    with pytest.raises(McpAuthenticationError) as excinfo:
        await McpGateway().list_tools(ListToolsRequest(_principal("nope")))
    assert "cannot list MCP tools" in excinfo.value.message


# ---------- policy chain mechanics ----------


async def test_empty_chain_allows_an_unbound_tool(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The binding rule is genuinely a policy, not something baked into the gateway."""
    server_id = await _seed_server(engine)
    await _seed_session(engine)

    async def fake_call_server_tool(
        connection: McpConnection, tool_name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        return _tool_result()

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    result = await McpGateway(policies=[]).call_tool(
        CallToolRequest(_principal(), server_id, "anything", {})
    )
    assert result.isError is False


async def test_policies_run_in_order_and_the_first_denial_short_circuits(
    engine: AsyncEngine,
) -> None:
    server_id = await _seed_server(engine)
    await _seed_session(engine)
    log: list[str] = []
    first = _RecordingPolicy(log, "first")
    denier = _RecordingPolicy(log, "denier", deny=True)
    last = _RecordingPolicy(log, "last")

    with pytest.raises(McpPolicyDeniedError) as excinfo:
        await McpGateway(policies=[first, denier, last]).call_tool(
            CallToolRequest(_principal(), server_id, "search", {})
        )
    assert excinfo.value.message == "denied by denier"
    assert log == ["first", "denier"]


async def test_a_denial_never_opens_a_connection(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_id = await _seed_server(engine)
    await _seed_session(engine)
    called: list[str] = []

    async def fake_call_server_tool(
        connection: McpConnection, tool_name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        called.append(connection.label)
        return _tool_result()

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    with pytest.raises(McpPolicyDeniedError):
        await McpGateway(policies=[_RecordingPolicy([], "no", deny=True)]).call_tool(
            CallToolRequest(_principal(), server_id, "search", {})
        )
    assert called == []


async def test_call_context_carries_the_whole_operation(engine: AsyncEngine) -> None:
    server_id = await _seed_server(engine)
    execution_id = await _seed_session(engine)
    spy = _RecordingPolicy([], "spy", deny=True)

    with pytest.raises(McpPolicyDeniedError):
        await McpGateway(policies=[spy]).call_tool(
            CallToolRequest(_principal(), server_id, "search", {"q": "a2flow"})
        )
    ctx = spy.contexts[0]
    assert ctx.operation is McpOperation.call_tool
    assert ctx.identity.tenant_id == DEFAULT_TEST_TENANT_ID
    assert ctx.identity.execution_id == execution_id
    assert ctx.server_id == server_id
    assert ctx.tool_name == "search"
    assert ctx.arguments == {"q": "a2flow"}
    # The server row is loaded only after the chain allows the call.
    assert ctx.server_name is None


async def test_listing_consults_the_chain_with_its_own_operation(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_session(engine)
    server_id = await _seed_server(engine, name="visible")
    spy = _RecordingPolicy([], "spy")

    async def fake_list_server_tools(connection: McpConnection) -> list[types.Tool]:
        return []

    monkeypatch.setattr(
        "infrastructure.mcp_client.list_server_tools", fake_list_server_tools
    )
    await McpGateway(policies=[spy]).list_tools(ListToolsRequest(_principal()))
    assert [c.operation for c in spy.contexts] == [McpOperation.list_tools]
    assert spy.contexts[0].server_id == server_id
    assert spy.contexts[0].server_name == "visible"


async def test_pass_through_policy_allows_everything(engine: AsyncEngine) -> None:
    identity = McpIdentity(tenant_id="t", execution_id=None)
    ctx = McpCallContext(
        operation=McpOperation.call_tool,
        principal=_principal(),
        identity=identity,
        server_id="srv",
        tool_name="anything",
    )
    async with AsyncSession(engine) as db:
        await PassThroughPolicy().authorize(ctx, db)


def test_default_policies_start_with_the_binding_rule() -> None:
    assert isinstance(default_policies()[0], InProgressToolBindingPolicy)


# ---------- InProgressToolBindingPolicy ----------


async def test_binding_policy_denies_a_design_run(engine: AsyncEngine) -> None:
    await _seed_design_session(engine, session_id="design-only")
    server_id = await _seed_server(engine)
    with pytest.raises(McpPolicyDeniedError) as excinfo:
        await McpGateway(policies=default_policies()).call_tool(
            CallToolRequest(_principal("design-only"), server_id, "search", {})
        )
    assert "no workflow execution" in excinfo.value.message


async def test_binding_policy_denies_when_no_task_is_in_progress(
    engine: AsyncEngine,
) -> None:
    server_id = await _seed_server(engine)
    execution_id = await _seed_session(engine)
    await _seed_task(
        engine,
        execution_id,
        status=WorkflowTaskStatus.pending,
        bindings=[(server_id, "search")],
    )
    with pytest.raises(McpPolicyDeniedError) as excinfo:
        await McpGateway(policies=default_policies()).call_tool(
            CallToolRequest(_principal(), server_id, "search", {})
        )
    assert "in_progress" in excinfo.value.message


async def test_binding_policy_denies_an_unbound_tool_and_lists_the_bound_ones(
    engine: AsyncEngine,
) -> None:
    server_id = await _seed_server(engine)
    execution_id = await _seed_session(engine)
    await _seed_task(engine, execution_id, bindings=[(server_id, "search")])
    with pytest.raises(McpPolicyDeniedError) as excinfo:
        await McpGateway(policies=default_policies()).call_tool(
            CallToolRequest(_principal(), server_id, "delete_everything", {})
        )
    assert "not bound" in excinfo.value.message
    assert "search" in excinfo.value.message


async def test_binding_policy_allows_the_union_of_in_progress_tasks(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_id = await _seed_server(engine)
    execution_id = await _seed_session(engine)
    await _seed_task(engine, execution_id, bindings=[(server_id, "alpha")])
    await _seed_task(engine, execution_id, bindings=[(server_id, "beta")])

    async def fake_call_server_tool(
        connection: McpConnection, tool_name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        return _tool_result()

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    gateway = McpGateway(policies=default_policies())
    for tool_name in ("alpha", "beta"):
        # The full chain runs here, so each call presents its own task's
        # certificate the way the real agent-side caller does.
        credential = await ApprovalCredentialProvider().credential_for(
            session_id="sess-abc",
            mcp_server_id=server_id,
            tool_name=tool_name,
            arguments={},
        )
        result = await gateway.call_tool(
            CallToolRequest(_principal(credential=credential), server_id, tool_name, {})
        )
        assert result.isError is False


async def test_binding_policy_ignores_listings(engine: AsyncEngine) -> None:
    """A listing is allowed with no execution at all: design is where binding happens."""
    identity = McpIdentity(tenant_id=DEFAULT_TEST_TENANT_ID, execution_id=None)
    ctx = McpCallContext(
        operation=McpOperation.list_tools,
        principal=_principal(),
        identity=identity,
        server_id="srv",
        server_name="srv",
    )
    async with AsyncSession(engine) as db:
        await InProgressToolBindingPolicy().authorize(ctx, db)


# ---------- call_tool ----------


async def test_call_tool_rejects_an_unregistered_server(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    with pytest.raises(McpServerUnknownError) as excinfo:
        await McpGateway(policies=[]).call_tool(
            CallToolRequest(_principal(), "srv-missing", "search", {})
        )
    assert "is not registered" in excinfo.value.message


async def test_call_tool_cannot_reach_another_tenants_server(
    engine: AsyncEngine,
) -> None:
    await seed_tenant(engine, "tenant-other")
    theirs = await _seed_server(engine, name="theirs", tenant_id="tenant-other")
    await _seed_session(engine)
    with pytest.raises(McpServerUnknownError):
        await McpGateway(policies=[]).call_tool(
            CallToolRequest(_principal(), theirs, "search", {})
        )


async def test_call_tool_reports_an_unresolvable_secret_without_connecting(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_id = await _seed_server(
        engine, headers={"Authorization": "Bearer ${secret:nope/k}"}
    )
    await _seed_session(engine)
    called: list[str] = []

    async def fake_call_server_tool(
        connection: McpConnection, tool_name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        called.append(connection.label)
        return _tool_result()

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    with pytest.raises(McpServerUnusableError) as excinfo:
        await McpGateway(policies=[]).call_tool(
            CallToolRequest(_principal(), server_id, "search", {})
        )
    assert "cannot resolve secret 'nope'" in excinfo.value.message
    assert called == []


async def test_call_tool_wraps_an_unreachable_server_naming_it(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_id = await _seed_server(engine, name="flaky")
    await _seed_session(engine)

    async def fake_call_server_tool(
        connection: McpConnection, tool_name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        raise McpConnectionError(connection.label, "connection refused")

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    with pytest.raises(McpUpstreamError) as excinfo:
        await McpGateway(policies=[]).call_tool(
            CallToolRequest(_principal(), server_id, "search", {})
        )
    assert "'flaky'" in excinfo.value.message
    assert isinstance(excinfo.value.__cause__, McpConnectionError)


async def test_call_tool_returns_a_tool_level_error_untouched(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A server reporting a failure is a successful gateway operation."""
    server_id = await _seed_server(engine)
    await _seed_session(engine)

    async def fake_call_server_tool(
        connection: McpConnection, tool_name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        return _tool_result("boom", is_error=True)

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    result = await McpGateway(policies=[]).call_tool(
        CallToolRequest(_principal(), server_id, "search", {})
    )
    assert result.isError is True


async def test_call_tool_expands_secrets_and_env_placeholders_for_stdio(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_local_secret(engine, "files-key", "tok-stdio")
    server_id = await _seed_stdio_server(
        engine,
        args=["-y", "files-mcp@0.3.0", "--key=${env:API_KEY}"],
        env={"API_KEY": "${secret:files-key/k}"},
    )
    await _seed_session(engine)
    seen: dict[str, Any] = {}

    async def fake_call_server_tool(
        connection: McpConnection, tool_name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        seen["connection"] = connection
        return _tool_result()

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    await McpGateway(policies=[]).call_tool(
        CallToolRequest(_principal(), server_id, "read_file", {})
    )
    assert seen["connection"] == StdioConnection(
        command="npx",
        args=["-y", "files-mcp@0.3.0", "--key=tok-stdio"],
        env={"API_KEY": "tok-stdio"},
    )


async def test_call_tool_closes_the_session_before_the_outbound_call(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stdio spawn can take two minutes; it must not pin a database connection."""
    server_id = await _seed_server(engine)
    await _seed_session(engine)
    closed: list[bool] = []

    @asynccontextmanager
    async def tracking_session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(database.engine) as db:
            yield db
        closed.append(True)

    async def fake_call_server_tool(
        connection: McpConnection, tool_name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        assert closed == [True]
        return _tool_result()

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    await McpGateway(policies=[], session_factory=tracking_session).call_tool(
        CallToolRequest(_principal(), server_id, "search", {})
    )
    assert closed == [True]


# ---------- the tool stub ----------


class _RecordingStub:
    """Test stub that answers when configured to, recording what it was asked."""

    def __init__(self, *, stubbed: bool) -> None:
        """Initialize the stub.

        Args:
            stubbed: What :meth:`stubs` reports for every call.
        """
        self.stubbed = stubbed
        self.asked: list[McpCallContext] = []
        self.answered: list[McpCallContext] = []

    async def stubs(self, ctx: McpCallContext, db: AsyncSession) -> bool:
        """Record the question and report the configured answer."""
        self.asked.append(ctx)
        return self.stubbed

    async def answer(
        self, ctx: McpCallContext, db: AsyncSession
    ) -> types.CallToolResult:
        """Record the call and return a marked result."""
        self.answered.append(ctx)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="stubbed")],
            _meta={MOCKED_META_KEY: True},
        )


class _CountingAuditSink:
    """Test audit sink that keeps every decision it is handed."""

    def __init__(self) -> None:
        """Start with no recorded decisions."""
        self.records: list[tuple[McpAuditDecision, str | None]] = []

    async def record(
        self,
        ctx: McpCallContext,
        db: AsyncSession,
        *,
        decision: McpAuditDecision,
        reason: str | None,
    ) -> None:
        """Keep the decision."""
        self.records.append((decision, reason))


async def test_call_tool_reaches_the_server_when_nothing_is_stubbed(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default NullToolStub must not divert anything."""
    server_id = await _seed_server(engine)
    await _seed_session(engine)
    called: list[str] = []

    async def fake_call_server_tool(
        connection: McpConnection, tool_name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        called.append(tool_name)
        return _tool_result()

    monkeypatch.setattr(
        "infrastructure.mcp_client.call_server_tool", fake_call_server_tool
    )
    audit = _CountingAuditSink()
    result = await McpGateway(policies=[], audit=audit).call_tool(
        CallToolRequest(_principal(), server_id, "search", {})
    )
    assert called == ["search"]
    assert result.meta is None
    assert audit.records == [(McpAuditDecision.allowed, None)]


async def test_a_stubbed_call_skips_the_server_and_the_audit(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An allowed but stubbed call reaches no server and earns no audit row."""
    server_id = await _seed_server(engine)
    await _seed_session(engine)

    async def _explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a stubbed call must not reach the MCP client")

    monkeypatch.setattr("infrastructure.mcp_client.call_server_tool", _explode)
    stub = _RecordingStub(stubbed=True)
    audit = _CountingAuditSink()
    result = await McpGateway(policies=[], audit=audit, stub=stub).call_tool(
        CallToolRequest(_principal(), server_id, "search", {})
    )
    assert (result.meta or {}).get(MOCKED_META_KEY) is True
    assert len(stub.answered) == 1
    assert audit.records == []


async def test_a_stubbed_call_is_still_run_through_the_policy_chain(
    engine: AsyncEngine,
) -> None:
    """The whole point of the placement: a stub does not buy past authorization."""
    server_id = await _seed_server(engine)
    await _seed_session(engine)
    stub = _RecordingStub(stubbed=True)
    log: list[str] = []
    policy = _RecordingPolicy(log, "gate", deny=True)
    with pytest.raises(McpPolicyDeniedError):
        await McpGateway(policies=[policy], stub=stub).call_tool(
            CallToolRequest(_principal(), server_id, "search", {})
        )
    assert log == ["gate"]
    # Asked, so the gateway could tell the refusal was of a stubbed call, but
    # never asked to answer -- which is what keeps a response unconsumed.
    assert len(stub.asked) == 1
    assert stub.answered == []


async def test_a_refused_stubbed_call_is_not_audited(
    engine: AsyncEngine,
) -> None:
    """No row either way: the table describes calls that reached a server."""
    server_id = await _seed_server(engine)
    await _seed_session(engine)
    audit = _CountingAuditSink()
    with pytest.raises(McpPolicyDeniedError):
        await McpGateway(
            policies=[_RecordingPolicy([], "gate", deny=True)],
            audit=audit,
            stub=_RecordingStub(stubbed=True),
        ).call_tool(CallToolRequest(_principal(), server_id, "search", {}))
    assert audit.records == []


async def test_a_refused_unstubbed_call_is_still_audited(
    engine: AsyncEngine,
) -> None:
    """The counterpart: an ordinary refusal keeps its ``denied`` row."""
    server_id = await _seed_server(engine)
    await _seed_session(engine)
    audit = _CountingAuditSink()
    with pytest.raises(McpPolicyDeniedError):
        await McpGateway(
            policies=[_RecordingPolicy([], "gate", deny=True)],
            audit=audit,
            stub=_RecordingStub(stubbed=False),
        ).call_tool(CallToolRequest(_principal(), server_id, "search", {}))
    assert audit.records == [(McpAuditDecision.denied, "denied by gate")]


async def test_the_stub_is_not_consulted_for_a_listing(engine: AsyncEngine) -> None:
    """Stubbing is a ``call_tool`` concern; a listing has no side effect to skip."""
    await _seed_server(engine)
    await _seed_session(engine)
    stub = _RecordingStub(stubbed=True)
    await McpGateway(policies=[], stub=stub).list_tools(ListToolsRequest(_principal()))
    assert stub.asked == []


# ---------- list_tools ----------


async def test_list_tools_on_an_empty_registry(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    assert await McpGateway().list_tools(ListToolsRequest(_principal())) == []


async def test_list_tools_isolates_an_unreachable_server(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_session(engine)
    good_id = await _seed_server(engine, name="good", url="https://good/mcp")
    bad_id = await _seed_server(engine, name="bad", url="https://bad/mcp")

    async def fake_list_server_tools(connection: McpConnection) -> list[types.Tool]:
        if "bad" in connection.label:
            raise McpConnectionError(connection.label, "connection refused")
        return [types.Tool(name="search", inputSchema={"type": "object"})]

    monkeypatch.setattr(
        "infrastructure.mcp_client.list_server_tools", fake_list_server_tools
    )
    by_id = {
        entry.server_id: entry
        for entry in await McpGateway().list_tools(ListToolsRequest(_principal()))
    }
    assert [tool.name for tool in by_id[good_id].tools] == ["search"]
    assert by_id[good_id].error is None
    assert by_id[bad_id].tools == []
    assert "unreachable" in (by_id[bad_id].error or "")


async def test_list_tools_isolates_a_secret_failure_without_connecting(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_session(engine)
    await _seed_local_secret(engine, "good-token", "tok-1")
    good_id = await _seed_server(
        engine,
        name="good",
        url="https://good/mcp",
        headers={"Authorization": "Bearer ${secret:good-token/k}"},
    )
    bad_id = await _seed_server(
        engine,
        name="bad",
        url="https://bad/mcp",
        headers={"Authorization": "Bearer ${secret:missing/k}"},
    )
    seen: dict[str, McpConnection] = {}

    async def fake_list_server_tools(connection: McpConnection) -> list[types.Tool]:
        seen[connection.label] = connection
        return []

    monkeypatch.setattr(
        "infrastructure.mcp_client.list_server_tools", fake_list_server_tools
    )
    by_id = {
        entry.server_id: entry
        for entry in await McpGateway().list_tools(ListToolsRequest(_principal()))
    }
    assert by_id[good_id].error is None
    assert "cannot resolve secret 'missing'" in (by_id[bad_id].error or "")
    assert seen == {
        "https://good/mcp": HttpConnection(
            url="https://good/mcp", headers={"Authorization": "Bearer tok-1"}
        )
    }


async def test_list_tools_stays_tenant_scoped(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await seed_tenant(engine, "tenant-other")
    await _seed_session(engine)
    mine = await _seed_server(engine, name="mine")
    await _seed_server(engine, name="theirs", tenant_id="tenant-other")

    async def fake_list_server_tools(connection: McpConnection) -> list[types.Tool]:
        return []

    monkeypatch.setattr(
        "infrastructure.mcp_client.list_server_tools", fake_list_server_tools
    )
    listings = await McpGateway().list_tools(ListToolsRequest(_principal()))
    assert [entry.server_id for entry in listings] == [mine]
