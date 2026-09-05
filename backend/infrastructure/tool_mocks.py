"""Resolution of the tool mocks a draft workflow run applies.

A run carries a snapshot of the :class:`~models.mcp_tool_mock.MCPToolMock`
records selected when it started (see
:attr:`models.workflow_execution.WorkflowExecution.tool_mocks`). Every tool that
can be mocked asks this module, before doing anything with a side effect,
whether the current run stubs it. There are two askers, and they sit at
different depths for a reason.

**MCP tools ask from inside the gateway.**
:class:`WorkflowExecutionToolStub` implements
:class:`infrastructure.mcp_gateway.McpToolStub`, which
:class:`~infrastructure.mcp_gateway.McpGateway` consults *after* its policy chain
has allowed the call. So a stubbed run rehearses the real one: the tool must
still be bound to a task the run has in progress, and a task with an approval
attached must still present its certificate. What the stub skips is only what
has an effect outside A2Flow -- the upstream call itself.

**A stubbed call still leaves no ``mcp_tool_invocations`` row**, allowed or
refused. That table records the calls that reached (or were stopped on their way
to) a real MCP server, and a row for a call that was always going to be answered
from a snapshot would make it lie in either direction. This is why the stub
protocol has two methods: the gateway has to know whether a call is stubbed
*before* it decides whether to audit a refusal, and finding that out must not
consume one of the run's responses.

**The built-in approval tool asks directly.**
:func:`infrastructure.approval_tools.request_approval` never goes through the
gateway -- it writes to ``approvals`` rather than calling a server -- so it calls
:func:`resolve_mock` itself, after validating its destination.

Which response a call receives depends on how many times the run has already
called that tool: the counter lives on the run
(:meth:`repositories.workflow_execution.SqlWorkflowExecutionRepository.next_tool_mock_ordinal`)
so it survives the many HTTP requests and possible replicas one agent run spans.
Past the end of the list the last response repeats.
"""

import logging
from typing import Any

from mcp import types
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.mcp_gateway import MOCKED_META_KEY, McpCallContext
from models.mcp_tool_mock import MCPToolMock, MockResponse, MockResponseKind
from repositories.workflow_execution import SqlWorkflowExecutionRepository

logger = logging.getLogger(__name__)

#: Stands in for the server id of a built-in agent tool, which belongs to
#: A2Flow rather than to a registered MCP server, so one key format covers both.
_BUILTIN = "builtin"


def mock_key(server_id: str | None, tool_name: str) -> str:
    """Build the per-run counter key identifying one mocked tool.

    Args:
        server_id: The registered MCP server, or ``None`` for a built-in tool.
        tool_name: The tool being mocked.

    Returns:
        ``"<server_id or 'builtin'>:<tool_name>"``.
    """
    return f"{server_id or _BUILTIN}:{tool_name}"


def snapshot_mock(mock: MCPToolMock) -> dict[str, Any]:
    """Project a stored mock into the shape a run records on itself.

    Only what the run needs at call time is copied -- not the mock's id, so a
    reader cannot mistake the snapshot for a live reference to a record that may
    since have changed or been deleted.

    Args:
        mock: The stored mock selected for a run.

    Returns:
        ``{"mcpServerId", "toolName", "responses"}``, camelCase to match the
        wire shape of every other JSON column.
    """
    return {
        "mcpServerId": mock.mcp_server_id,
        "toolName": mock.tool_name,
        "responses": list(mock.responses),
    }


def _find(
    snapshots: list[dict[str, Any]], server_id: str | None, tool_name: str
) -> dict[str, Any] | None:
    """Return the run's snapshot for one tool, or ``None`` when it is not mocked.

    Args:
        snapshots: The run's recorded mock snapshots.
        server_id: The registered MCP server, or ``None`` for a built-in tool.
        tool_name: The tool being called.

    Returns:
        The matching snapshot, or ``None``.
    """
    for snapshot in snapshots:
        if (
            snapshot.get("mcpServerId") == server_id
            and snapshot.get("toolName") == tool_name
        ):
            return snapshot
    return None


async def resolve_mock(
    db: AsyncSession,
    execution_id: str,
    *,
    tenant_id: str,
    server_id: str | None,
    tool_name: str,
) -> MockResponse | None:
    """Return the mocked response for this call, or ``None`` to call for real.

    Advances the run's call counter for the tool as a side effect, so two calls
    to the same mocked tool receive successive responses.

    An unusable snapshot -- no responses, or an entry that no longer parses --
    yields an ``error`` response rather than ``None``. Returning ``None`` would
    mean "not mocked", and the safe reading of "this stub is broken" is never
    "go ahead and perform the real side effect".

    Args:
        db: An open database session.
        execution_id: The run making the call.
        tenant_id: Tenant the run belongs to.
        server_id: The registered MCP server, or ``None`` for a built-in tool.
        tool_name: The tool being called.

    Returns:
        The response to return in place of calling the tool, or ``None`` when
        this run does not mock it.
    """
    repo = SqlWorkflowExecutionRepository(db, tenant_id=tenant_id)
    execution = await repo.get(execution_id)
    if execution is None or not execution.tool_mocks:
        return None
    snapshot = _find(execution.tool_mocks, server_id, tool_name)
    if snapshot is None:
        return None
    raw = snapshot.get("responses") or []
    if not raw:
        # Cannot happen through the API -- an empty response list is rejected at
        # write time -- but a stub with nothing to return must not fall through
        # to the real tool.
        logger.warning(
            "Tool mock for %s on run %s has no responses; refusing the call",
            mock_key(server_id, tool_name),
            execution_id,
        )
        return MockResponse(
            kind=MockResponseKind.error,
            value="this tool is mocked for the current run, but the mock defines no response",
        )
    ordinal = await repo.next_tool_mock_ordinal(
        execution_id, mock_key(server_id, tool_name)
    )
    entry = raw[min(ordinal, len(raw)) - 1]
    try:
        return MockResponse.model_validate(entry)
    except ValueError:
        logger.exception(
            "Tool mock for %s on run %s has an unreadable response at ordinal %d",
            mock_key(server_id, tool_name),
            execution_id,
            ordinal,
        )
        return MockResponse(
            kind=MockResponseKind.error,
            value="this tool is mocked for the current run, but the mocked response is unreadable",
        )


def mock_result_to_call_result(response: MockResponse) -> types.CallToolResult:
    """Convert a mocked response into the MCP result the gateway hands back.

    Building the wire type rather than the LLM-facing dict is what makes a
    stubbed call travel the same path as a real one: it flows out of
    :meth:`infrastructure.mcp_gateway.McpGateway.call_tool` and through
    :func:`infrastructure.mcp_tools._result_to_dict` like any other result, so
    the two shapes cannot drift apart. ``_meta`` carries the marker that tells
    that function to add ``"mocked": true``.

    Args:
        response: The mocked response selected for this call.

    Returns:
        The stubbed result, with :data:`~infrastructure.mcp_gateway.MOCKED_META_KEY`
        set in its ``_meta``.
    """
    meta = {MOCKED_META_KEY: True}
    if response.kind is MockResponseKind.structured:
        return types.CallToolResult(
            content=[], structuredContent=response.value, _meta=meta
        )
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=str(response.value))],
        isError=response.kind is MockResponseKind.error,
        _meta=meta,
    )


class WorkflowExecutionToolStub:
    """Answers a proxied call from the mocks its run recorded when it started.

    The gateway's :class:`~infrastructure.mcp_gateway.McpToolStub`, wired in by
    :func:`~infrastructure.mcp_gateway.get_mcp_gateway`. Kept here rather than in
    ``mcp_gateway`` for the same reason
    :class:`infrastructure.mcp_audit.SqlMcpAuditSink` is: answering means
    importing :mod:`repositories`, and the gateway stays free of those imports.
    """

    async def stubs(self, ctx: McpCallContext, db: AsyncSession) -> bool:
        """Report whether the run answers this call from a mock.

        Reads the run's snapshot only -- no counter is advanced, because the
        gateway asks this for calls that go on to be refused.

        Args:
            ctx: The operation being attempted.
            db: The gateway's open database session.

        Returns:
            ``True`` when the run stubs the target tool. ``False`` for a design
            session, which has no run to carry mocks.
        """
        if ctx.identity.execution_id is None:
            return False
        repo = SqlWorkflowExecutionRepository(db, tenant_id=ctx.identity.tenant_id)
        execution = await repo.get(ctx.identity.execution_id)
        if execution is None or not execution.tool_mocks:
            return False
        return (
            _find(execution.tool_mocks, ctx.server_id, ctx.tool_name or "") is not None
        )

    async def answer(
        self, ctx: McpCallContext, db: AsyncSession
    ) -> types.CallToolResult:
        """Return the run's next recorded response for this call.

        Args:
            ctx: The operation being attempted, already allowed by the policy
                chain and confirmed stubbed by :meth:`stubs`.
            db: The gateway's open database session.

        Returns:
            The stubbed result. A snapshot that vanished between :meth:`stubs`
            and here yields an ``error`` result rather than ``None``: the gateway
            would read ``None`` as "call it for real", and performing the real
            side effect is never the safe reading of a broken stub.
        """
        assert ctx.identity.execution_id is not None  # guaranteed by stubs()
        response = await resolve_mock(
            db,
            ctx.identity.execution_id,
            tenant_id=ctx.identity.tenant_id,
            server_id=ctx.server_id,
            tool_name=ctx.tool_name or "",
        )
        if response is None:
            logger.warning(
                "Tool mock for %s on run %s disappeared between the check and the "
                "call; refusing rather than calling the real tool",
                mock_key(ctx.server_id, ctx.tool_name or ""),
                ctx.identity.execution_id,
            )
            response = MockResponse(
                kind=MockResponseKind.error,
                value="this tool is mocked for the current run, but the mock could "
                "no longer be read",
            )
        return mock_result_to_call_result(response)
