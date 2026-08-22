"""ADK agent proxy tools for invoking MCP tools bound to WorkflowTasks.

The workflow agent never talks to MCP servers directly. Instead it gets two
generic tools:

* :func:`list_mcp_tools` -- discover the tools advertised by every MCP server
  registered in A2Flow, so the agent can bind the ones a task needs. It is
  available in every phase: the design agents call it before registering the task templates
  (binding through the ``tools`` entries of ``register_design_tasks`` or the
  ``tool_bindings`` argument of ``create_design_task`` /
  ``update_design_task``), and the execution agent calls it when adjusting a
  run's tasks (``create_workflow_task`` / ``update_workflow_task``).
* :func:`call_mcp_tool` -- invoke one tool on one registered server. The call is
  validated server-side: it must target a tool bound to a task that is currently
  ``in_progress`` in the session, otherwise it is rejected. This enforces the
  per-task tool scoping that a shared, skill-cached agent cannot express through
  its static toolset.

Neither tool reaches an MCP server itself. Both hand a request to
:class:`infrastructure.mcp_proxy.McpProxy`, which authenticates the caller, runs
the policy chain that owns the rule above (see
:mod:`infrastructure.mcp_policies`), expands the server's secrets, and only then
calls :mod:`infrastructure.mcp_client`. What is left here is the ADK boundary:
turn a ``ToolContext`` into a plain principal on the way in, and turn proxy
results and errors into the JSON-serializable dicts the LLM consumes on the way
out -- including mapping every failure to an ``{"error": ...}`` payload the
model can react to instead of raising.

The two tools differ in what the proxy demands of them. ``list_mcp_tools`` only
needs the tenant, so it works in both an execution run (keyed on a
WorkflowExecution) and a design run (keyed on a Workflow's design session).
``call_mcp_tool`` has to check the run's in-progress tasks, so it still requires
a WorkflowExecution and is unavailable while merely designing -- a task template
may bind tools, but only a run may invoke them.
"""

import json
import logging
from typing import Any

from google.adk.tools.tool_context import ToolContext
from mcp import types

from infrastructure.mcp_proxy import (
    CallToolRequest,
    ListToolsRequest,
    McpPrincipal,
    McpProxyError,
    PrincipalKind,
    ServerToolListing,
    get_mcp_proxy,
)
from infrastructure.workflow_task_tools import ACTING_USER_STATE_KEY

logger = logging.getLogger(__name__)


def _principal(tool_context: ToolContext) -> McpPrincipal:
    """Build the proxy principal from the ADK tool context.

    ADK types stop here: the proxy is handed plain scalars, which is what lets
    the same call arrive over HTTP later. The acting user is read the same way
    :func:`infrastructure.workflow_task_tools._user_id` reads it -- the
    impersonation-aware per-turn state entry first, the ADK session's fixed
    owner second -- so a future policy sees whoever is really driving the run.

    Args:
        tool_context: The ADK tool context for the current invocation.

    Returns:
        The caller's claimed identity. ``session_id`` is empty when the context
        exposes no session, which the proxy rejects.
    """
    session = getattr(tool_context, "session", None)
    state = getattr(tool_context, "state", None)
    acting = state.get(ACTING_USER_STATE_KEY) if state is not None else None
    return McpPrincipal(
        kind=PrincipalKind.agent_run,
        session_id=getattr(session, "id", None) or "",
        user_id=str(acting) if acting else getattr(tool_context, "user_id", None),
    )


def _coerce_arguments(arguments: object) -> dict[str, Any] | None:
    """Coerce the model-supplied arguments into a dict, or ``None`` if impossible.

    Some models emit the arguments object as a JSON string; tolerate that by
    parsing it. This stays at the ADK boundary rather than moving into the
    proxy: an HTTP proxy would reject a non-object at its schema.

    Args:
        arguments: The raw ``arguments`` value from the model.

    Returns:
        The arguments as a dict, or ``None`` when they are neither a dict nor a
        JSON string encoding one.
    """
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except ValueError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


def _result_to_dict(result: types.CallToolResult) -> dict[str, Any]:
    """Convert a ``tools/call`` result into a plain dict the LLM can consume.

    Args:
        result: The raw MCP call result.

    Returns:
        ``{"error": <joined text>}`` when the tool reported an error, otherwise
        ``{"result": {"content": [<text blocks>], "structured": <object|None>}}``.
    """
    texts = [
        block.text for block in result.content if isinstance(block, types.TextContent)
    ]
    if result.isError:
        return {"error": "\n".join(texts) or "MCP tool reported an error"}
    return {
        "result": {
            "content": texts,
            "structured": result.structuredContent,
        }
    }


def _listing_to_dict(listing: ServerToolListing) -> dict[str, Any]:
    """Project one server's listing into the dict shape the LLM consumes.

    Args:
        listing: One registered server's contribution to a proxied listing.

    Returns:
        ``{"server_id", "server_name", "tools": [...]}`` on success, or
        ``{"server_id", "server_name", "error"}`` when the server could not be
        queried.
    """
    base = {"server_id": listing.server_id, "server_name": listing.server_name}
    if listing.error is not None:
        return {**base, "error": listing.error}
    return {
        **base,
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
            }
            for tool in listing.tools
        ],
    }


async def list_mcp_tools(tool_context: ToolContext) -> dict[str, Any]:
    """List the tools advertised by every MCP server registered in A2Flow.

    Call this during design to discover what external tools exist before
    binding them to tasks: while designing a workflow, bind them through the
    ``tools`` entries of ``register_design_tasks`` or the ``tool_bindings``
    argument of ``create_design_task``/``update_design_task``; while
    executing a run, through ``create_workflow_task``/``update_workflow_task``.
    Each server is queried live and concurrently; a server that cannot be
    reached is reported with an ``error`` field instead of failing the whole
    listing.

    Args:
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        ``{"servers": [{"server_id", "server_name", "tools": [{"name",
        "description", "input_schema"}, ...]} | {"server_id", "server_name",
        "error"}, ...]}``. An empty registry yields ``{"servers": []}``.
    """
    try:
        listings = await get_mcp_proxy().list_tools(
            ListToolsRequest(principal=_principal(tool_context))
        )
    except McpProxyError as exc:
        return {"error": exc.message}
    return {"servers": [_listing_to_dict(listing) for listing in listings]}


async def call_mcp_tool(
    server_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Invoke an MCP tool bound to the task currently in progress.

    Only tools bound to an ``in_progress`` task of the current session may be
    invoked; calls to unbound tools are rejected with an error listing the
    allowed tools. When several tasks are in progress at once, the union of
    their bindings is allowed.

    Args:
        server_id: Id of the registered MCP server (as bound to the task).
        tool_name: Name of the tool on that server.
        arguments: Arguments matching the tool's input schema (see
            ``list_mcp_tools``).
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        ``{"result": {"content": [...], "structured": ...}}`` on success, or
        ``{"error": <message>}`` when the session/task cannot be resolved, the
        tool is not bound to the current in-progress task, the server is not
        registered or unreachable, or the tool itself reports an error.
    """
    args = _coerce_arguments(arguments)
    if args is None:
        return {"error": "arguments must be an object matching the tool's input schema"}
    try:
        result = await get_mcp_proxy().call_tool(
            CallToolRequest(
                principal=_principal(tool_context),
                server_id=server_id,
                tool_name=tool_name,
                arguments=args,
            )
        )
    except McpProxyError as exc:
        return {"error": exc.message}
    return _result_to_dict(result)
