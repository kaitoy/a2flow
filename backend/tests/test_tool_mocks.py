"""Tests for tool mocking: ``infrastructure.tool_mocks`` and its two call sites.

Three things are worth proving here. A mocked call produces the configured
result; it never reaches the machinery behind the tool (no MCP client traffic,
no ``mcp_tool_invocations`` row, no ``approvals`` row, no notifications); and --
for MCP tools, whose stub sits *inside* the proxy behind its policy chain -- it
is still subject to the same authorization a real call faces. That last part is
why the MCP cases here seed an ``in_progress`` WorkflowTask binding the target
tool: without one the call is refused before the stub is ever asked to answer.

Like the other agent-tool tests, each test points the module-level database
engine at a throwaway database and drives the tools with a
lightweight fake ToolContext.
"""

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.approval_tools import request_approval
from infrastructure.mcp_tools import call_mcp_tool
from infrastructure.tool_mocks import mock_key, resolve_mock, snapshot_mock
from models.approval import Approval, ApprovalStatus
from models.mcp_server import MCPServer, McpTransport
from models.mcp_tool_invocation import McpAuditDecision, MCPToolInvocation
from models.mcp_tool_mock import (
    REQUEST_APPROVAL_TOOL,
    MCPToolMock,
    MockResponse,
    MockResponseKind,
)
from models.notification import Notification
from models.user import SYSTEM_USER_ID
from models.workflow_execution import WorkflowExecution
from models.workflow_task import (
    WorkflowTask,
    WorkflowTaskStatus,
    WorkflowTaskToolBinding,
)
from tests._engine import make_test_engine
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users


@pytest_asyncio.fixture()
async def engine(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[AsyncEngine, None]:
    """Yield a throwaway engine and point the tools' module-level engine at it."""
    eng = await make_test_engine()
    await seed_users(eng, ids=())  # system user only; Tenant FKs to it
    await seed_tenant(eng)
    await seed_users(eng, tenant_id=DEFAULT_TEST_TENANT_ID)

    monkeypatch.setattr("infrastructure.database.engine", eng)
    yield eng
    await eng.dispose()


def _ctx(session_id: str = "sess-abc", user_id: str = "owner") -> Any:
    """Build a fake ToolContext exposing ``session.id``, ``user_id``, and ``state``."""
    return SimpleNamespace(
        session=SimpleNamespace(id=session_id), user_id=user_id, state=None
    )


async def _seed_execution(
    eng: AsyncEngine,
    *,
    session_id: str = "sess-abc",
    tool_mocks: list[dict[str, Any]] | None = None,
) -> str:
    """Insert a WorkflowExecution carrying the given mock snapshots, returning its PK."""
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
            is_draft=True,
            tool_mocks=tool_mocks or [],
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by="owner",
            updated_by="owner",
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)
        return execution.id


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


async def _seed_task(
    eng: AsyncEngine, execution_id: str, *, bindings: list[tuple[str, str]]
) -> str:
    """Insert an ``in_progress`` WorkflowTask binding the given tools.

    A mocked MCP call is authorized before it is answered, so without one of
    these the binding policy refuses it and the stub is never asked.
    """
    async with AsyncSession(eng) as db:
        task = WorkflowTask(
            workflow_execution_id=execution_id,
            title="Step",
            status=WorkflowTaskStatus.in_progress,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by="owner",
            updated_by="owner",
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


def _snapshot(
    server_id: str | None, tool_name: str, responses: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build a mock snapshot of the shape a run records on itself."""
    return {"mcpServerId": server_id, "toolName": tool_name, "responses": responses}


async def _invocations(eng: AsyncEngine) -> list[MCPToolInvocation]:
    """Return every recorded MCP tool-call decision."""
    async with AsyncSession(eng) as db:
        return list((await db.exec(select(MCPToolInvocation))).all())


# ---------- snapshot_mock ----------


async def test_snapshot_copies_the_target_and_responses(engine: AsyncEngine) -> None:
    server_id = await _seed_server(engine)
    responses = [{"kind": "text", "value": "hi"}]
    async with AsyncSession(engine) as db:
        mock = MCPToolMock(
            name="m",
            mcp_server_id=server_id,
            tool_name="search",
            responses=responses,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(mock)
        await db.commit()
        await db.refresh(mock)
        snapshot = snapshot_mock(mock)
    assert snapshot == _snapshot(server_id, "search", responses)
    # Deliberately no id: the run must not be able to follow the reference back
    # to a record that may since have changed.
    assert "id" not in snapshot


# ---------- resolve_mock ----------


async def test_resolve_returns_none_for_a_run_without_mocks(
    engine: AsyncEngine,
) -> None:
    execution_id = await _seed_execution(engine)
    async with AsyncSession(engine) as db:
        result = await resolve_mock(
            db,
            execution_id,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            server_id="srv-1",
            tool_name="search",
        )
    assert result is None


async def test_resolve_returns_none_for_an_unmocked_tool(engine: AsyncEngine) -> None:
    execution_id = await _seed_execution(
        engine,
        tool_mocks=[_snapshot("srv-1", "write", [{"kind": "text", "value": "x"}])],
    )
    async with AsyncSession(engine) as db:
        result = await resolve_mock(
            db,
            execution_id,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            server_id="srv-1",
            tool_name="search",
        )
    assert result is None


async def test_resolve_walks_the_responses_in_order(engine: AsyncEngine) -> None:
    execution_id = await _seed_execution(
        engine,
        tool_mocks=[
            _snapshot(
                "srv-1",
                "search",
                [
                    {"kind": "text", "value": "first"},
                    {"kind": "text", "value": "second"},
                ],
            )
        ],
    )
    seen = []
    for _ in range(2):
        async with AsyncSession(engine) as db:
            response = await resolve_mock(
                db,
                execution_id,
                tenant_id=DEFAULT_TEST_TENANT_ID,
                server_id="srv-1",
                tool_name="search",
            )
        assert response is not None
        seen.append(response.value)
    assert seen == ["first", "second"]


async def test_resolve_repeats_the_last_response_past_the_end(
    engine: AsyncEngine,
) -> None:
    execution_id = await _seed_execution(
        engine,
        tool_mocks=[
            _snapshot(
                "srv-1",
                "search",
                [{"kind": "text", "value": "one"}, {"kind": "text", "value": "two"}],
            )
        ],
    )
    seen = []
    for _ in range(4):
        async with AsyncSession(engine) as db:
            response = await resolve_mock(
                db,
                execution_id,
                tenant_id=DEFAULT_TEST_TENANT_ID,
                server_id="srv-1",
                tool_name="search",
            )
        assert response is not None
        seen.append(response.value)
    assert seen == ["one", "two", "two", "two"]


async def test_resolve_counts_each_tool_separately(engine: AsyncEngine) -> None:
    execution_id = await _seed_execution(
        engine,
        tool_mocks=[
            _snapshot(
                "srv-1",
                "a",
                [{"kind": "text", "value": "a1"}, {"kind": "text", "value": "a2"}],
            ),
            _snapshot(
                "srv-1",
                "b",
                [{"kind": "text", "value": "b1"}, {"kind": "text", "value": "b2"}],
            ),
        ],
    )
    async with AsyncSession(engine) as db:
        first_a = await resolve_mock(
            db,
            execution_id,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            server_id="srv-1",
            tool_name="a",
        )
        first_b = await resolve_mock(
            db,
            execution_id,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            server_id="srv-1",
            tool_name="b",
        )
    assert first_a is not None and first_a.value == "a1"
    assert first_b is not None and first_b.value == "b1"


async def test_resolve_records_the_counter_on_the_run(engine: AsyncEngine) -> None:
    execution_id = await _seed_execution(
        engine,
        tool_mocks=[
            _snapshot(
                None, REQUEST_APPROVAL_TOOL, [{"kind": "text", "value": "approved"}]
            )
        ],
    )
    async with AsyncSession(engine) as db:
        await resolve_mock(
            db,
            execution_id,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            server_id=None,
            tool_name=REQUEST_APPROVAL_TOOL,
        )
    async with AsyncSession(engine) as db:
        execution = await db.get(WorkflowExecution, execution_id)
    assert execution is not None
    assert execution.tool_mock_calls == {mock_key(None, REQUEST_APPROVAL_TOOL): 1}


async def test_resolve_refuses_rather_than_falling_through_on_an_empty_mock(
    engine: AsyncEngine,
) -> None:
    """A stub with no responses must not let the real tool run."""
    execution_id = await _seed_execution(
        engine, tool_mocks=[_snapshot("srv-1", "search", [])]
    )
    async with AsyncSession(engine) as db:
        response = await resolve_mock(
            db,
            execution_id,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            server_id="srv-1",
            tool_name="search",
        )
    assert response is not None
    assert response.kind is MockResponseKind.error


# ---------- call_mcp_tool ----------


async def _seed_mocked_run(
    engine: AsyncEngine, server_id: str, responses: list[dict[str, Any]]
) -> str:
    """Seed a run that mocks ``search`` on ``server_id`` and may legitimately call it."""
    execution_id = await _seed_execution(
        engine, tool_mocks=[_snapshot(server_id, "search", responses)]
    )
    await _seed_task(engine, execution_id, bindings=[(server_id, "search")])
    return execution_id


async def test_mocked_mcp_call_returns_the_structured_response(
    engine: AsyncEngine,
) -> None:
    server_id = await _seed_server(engine)
    await _seed_mocked_run(
        engine, server_id, [{"kind": "structured", "value": {"hits": 0}}]
    )
    result = await call_mcp_tool(server_id, "search", {"q": "x"}, _ctx())
    assert result["mocked"] is True
    assert result["result"] == {"content": [], "structured": {"hits": 0}}


async def test_mocked_mcp_call_returns_the_text_response(engine: AsyncEngine) -> None:
    server_id = await _seed_server(engine)
    await _seed_mocked_run(engine, server_id, [{"kind": "text", "value": "none"}])
    result = await call_mcp_tool(server_id, "search", {}, _ctx())
    assert result["result"] == {"content": ["none"], "structured": None}


async def test_mocked_mcp_call_can_report_an_error(engine: AsyncEngine) -> None:
    server_id = await _seed_server(engine)
    await _seed_mocked_run(
        engine, server_id, [{"kind": "error", "value": "upstream down"}]
    )
    result = await call_mcp_tool(server_id, "search", {}, _ctx())
    assert result == {"error": "upstream down", "mocked": True}


async def test_mocked_mcp_call_reaches_no_server_and_leaves_no_audit_row(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It goes through the proxy, but stops at the stub inside it."""
    server_id = await _seed_server(engine)
    await _seed_mocked_run(engine, server_id, [{"kind": "text", "value": "ok"}])

    async def _explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the MCP client must not be reached for a mocked call")

    monkeypatch.setattr("infrastructure.mcp_client.call_server_tool", _explode)
    result = await call_mcp_tool(server_id, "search", {}, _ctx())
    assert result["mocked"] is True
    assert await _invocations(engine) == []


async def test_mocked_mcp_call_still_needs_an_in_progress_task_binding(
    engine: AsyncEngine,
) -> None:
    """A mock buys past the side effect, not past authorization.

    The run stubs the tool, and has a task in progress, but that task binds a
    different tool. The binding policy refuses the call exactly as it would a
    real one -- and, because the call was always going to be stubbed, the
    refusal leaves no audit row either.
    """
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(
        engine,
        tool_mocks=[_snapshot(server_id, "search", [{"kind": "text", "value": "ok"}])],
    )
    await _seed_task(engine, execution_id, bindings=[(server_id, "write")])
    result = await call_mcp_tool(server_id, "search", {}, _ctx())
    assert "error" in result
    assert "not bound to the current in-progress task" in result["error"]
    assert "mocked" not in result
    assert await _invocations(engine) == []


async def test_a_refused_mocked_call_does_not_consume_a_response(
    engine: AsyncEngine,
) -> None:
    """Finding out a call is stubbed must not spend one of the run's responses."""
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(
        engine,
        tool_mocks=[
            _snapshot(
                server_id,
                "search",
                [
                    {"kind": "text", "value": "first"},
                    {"kind": "text", "value": "second"},
                ],
            )
        ],
    )
    refused = await call_mcp_tool(server_id, "search", {}, _ctx())
    assert "error" in refused
    # Now make the same call legitimate. It must still get the *first* response.
    await _seed_task(engine, execution_id, bindings=[(server_id, "search")])
    allowed = await call_mcp_tool(server_id, "search", {}, _ctx())
    assert allowed["result"] == {"content": ["first"], "structured": None}


async def test_unmocked_tool_on_a_mocked_run_still_goes_through_the_proxy(
    engine: AsyncEngine,
) -> None:
    """Mocking one tool must not stub the read-only one next to it."""
    server_id = await _seed_server(engine)
    await _seed_execution(
        engine,
        tool_mocks=[_snapshot(server_id, "write", [{"kind": "text", "value": "ok"}])],
    )
    result = await call_mcp_tool(server_id, "search", {}, _ctx())
    # Denied by the binding policy, which is exactly the proxy being consulted.
    assert "error" in result
    assert "mocked" not in result
    # And, unlike a refused *mocked* call, this one is audited: nothing about it
    # was ever going to be answered from a snapshot.
    invocations = await _invocations(engine)
    assert [i.decision for i in invocations] == [McpAuditDecision.denied]


async def test_mocked_call_on_an_approved_task_still_needs_the_certificate(
    engine: AsyncEngine,
) -> None:
    """The certificate policy applies to a stubbed call too.

    A draft run that mocks the tool but *not* ``request_approval`` records a
    real Approval, and the call must then carry that approval's certificate.
    None was issued here, so the call is refused rather than quietly stubbed.
    """
    server_id = await _seed_server(engine)
    execution_id = await _seed_mocked_run(
        engine, server_id, [{"kind": "text", "value": "ok"}]
    )
    async with AsyncSession(engine) as db:
        task = (await db.exec(select(WorkflowTask))).one()
        db.add(
            Approval(
                workflow_execution_id=execution_id,
                workflow_task_id=task.id,
                title="Approve me",
                status=ApprovalStatus.approved,
                approver="alice",
                tenant_id=DEFAULT_TEST_TENANT_ID,
                created_by="owner",
                updated_by="owner",
            )
        )
        await db.commit()
    result = await call_mcp_tool(server_id, "search", {}, _ctx())
    assert "error" in result
    assert "approval certificate" in result["error"]
    assert "mocked" not in result


# ---------- request_approval ----------


def _approval_mock(*statuses: str) -> dict[str, Any]:
    """Build a snapshot mocking ``request_approval`` with the given statuses."""
    return _snapshot(
        None,
        REQUEST_APPROVAL_TOOL,
        [{"kind": "structured", "value": {"status": s}} for s in statuses],
    )


async def _seed_approval_task(
    eng: AsyncEngine,
    execution_id: str,
    *,
    title: str = "Act",
    depends_on: str | None = None,
    binds: tuple[str, str] | None = None,
) -> str:
    """Insert a task for ``request_approval`` to name, returning its id.

    ``request_approval`` requires the id of the task the approval authorizes,
    so every mocked request needs one even when the mock is what is under test.
    """
    from models.workflow_task import WorkflowTaskDependency, WorkflowTaskToolBinding

    async with AsyncSession(eng) as db:
        task = WorkflowTask(
            workflow_execution_id=execution_id,
            title=title,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by="owner",
            updated_by="owner",
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        task_id = task.id
        if depends_on is not None:
            db.add(WorkflowTaskDependency(task_id=task_id, depends_on_id=depends_on))
        if binds is not None:
            db.add(
                WorkflowTaskToolBinding(
                    task_id=task_id, mcp_server_id=binds[0], tool_name=binds[1]
                )
            )
        await db.commit()
        return task_id


async def test_mocked_approval_returns_approved_without_recording_anything(
    engine: AsyncEngine,
) -> None:
    execution_id = await _seed_execution(
        engine, tool_mocks=[_approval_mock("approved")]
    )
    task_id = await _seed_approval_task(engine, execution_id)
    result = await request_approval("Deploy", _ctx(), task_id, approver="alice")
    assert result["status"] == "approved"
    assert result["mocked"] is True
    assert "render_approval" in result["note"]
    assert result["approval_id"].startswith("mock-")
    async with AsyncSession(engine) as db:
        assert list((await db.exec(select(Approval))).all()) == []
        assert list((await db.exec(select(Notification))).all()) == []


async def test_mocked_approval_walks_successive_decisions(
    engine: AsyncEngine,
) -> None:
    execution_id = await _seed_execution(
        engine, tool_mocks=[_approval_mock("approved", "rejected")]
    )
    task_id = await _seed_approval_task(engine, execution_id)
    first = await request_approval("One", _ctx(), task_id, approver="alice")
    second = await request_approval("Two", _ctx(), task_id, approver="alice")
    assert first["status"] == "approved"
    assert second["status"] == "rejected"


async def test_mocked_approval_still_validates_the_destination(
    engine: AsyncEngine,
) -> None:
    """A mock skips the side effects, not the checks."""
    execution_id = await _seed_execution(
        engine, tool_mocks=[_approval_mock("approved")]
    )
    task_id = await _seed_approval_task(engine, execution_id)
    both = await request_approval(
        "Deploy", _ctx(), task_id, approver="alice", approver_group_id="g1"
    )
    assert "error" in both
    unknown = await request_approval("Deploy", _ctx(), task_id, approver="nobody")
    assert "error" in unknown


async def test_mocked_approval_still_validates_the_named_task(
    engine: AsyncEngine,
) -> None:
    """Naming the asking step instead of the acting task is refused when mocked too.

    Same reason as the destination check above: a mock skips the side effects,
    not the checks, so a workflow that would issue a certificate granting
    nothing fails in a dry run exactly as it would for real.
    """
    server_id = await _seed_server(engine)
    execution_id = await _seed_execution(
        engine, tool_mocks=[_approval_mock("approved")]
    )
    asking = await _seed_approval_task(engine, execution_id, title="Request approval")
    await _seed_approval_task(
        engine,
        execution_id,
        title="Launch instance",
        depends_on=asking,
        binds=(server_id, "search"),
    )
    result = await request_approval("Deploy", _ctx(), asking, approver="alice")
    assert "error" in result
    assert "binds no MCP tools" in result["error"]
    assert "mocked" not in result


async def test_mocked_approval_accepts_a_text_response(engine: AsyncEngine) -> None:
    execution_id = await _seed_execution(
        engine,
        tool_mocks=[
            _snapshot(
                None, REQUEST_APPROVAL_TOOL, [{"kind": "text", "value": "rejected"}]
            )
        ],
    )
    task_id = await _seed_approval_task(engine, execution_id)
    result = await request_approval("Deploy", _ctx(), task_id, approver="alice")
    assert result["status"] == "rejected"
    assert result["mocked"] is True


async def test_mocked_approval_can_report_an_error(engine: AsyncEngine) -> None:
    execution_id = await _seed_execution(
        engine,
        tool_mocks=[
            _snapshot(None, REQUEST_APPROVAL_TOOL, [{"kind": "error", "value": "nope"}])
        ],
    )
    task_id = await _seed_approval_task(engine, execution_id)
    result = await request_approval("Deploy", _ctx(), task_id, approver="alice")
    assert result == {"error": "nope"}


async def test_unmocked_approval_still_records_a_pending_request(
    engine: AsyncEngine,
) -> None:
    execution_id = await _seed_execution(engine)
    task_id = await _seed_approval_task(engine, execution_id)
    result = await request_approval("Deploy", _ctx(), task_id, approver="alice")
    assert result["status"] == "pending"
    assert "mocked" not in result
    async with AsyncSession(engine) as db:
        assert len(list((await db.exec(select(Approval))).all())) == 1


# ---------- mock_result_to_dict ----------


def test_mock_key_labels_a_builtin_tool() -> None:
    assert mock_key(None, "request_approval") == "builtin:request_approval"
    assert mock_key("srv-1", "search") == "srv-1:search"


def test_mock_response_rejects_a_non_object_structured_value() -> None:
    with pytest.raises(ValueError):
        MockResponse(kind=MockResponseKind.structured, value="not an object")
