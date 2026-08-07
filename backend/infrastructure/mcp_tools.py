"""ADK agent proxy tools for invoking MCP tools bound to WorkflowTasks.

The workflow agent never talks to MCP servers directly. Instead it gets two
generic tools:

* :func:`list_mcp_tools` — discover the tools advertised by every MCP server
  registered in A2Flow, so the agent can bind the ones a task needs. It is
  available in every phase: the design agents call it before registering the task templates
  (binding through the ``tools`` entries of ``register_design_tasks`` or the
  ``tool_bindings`` argument of ``create_design_task`` /
  ``update_design_task``), and the execution agent calls it when adjusting a
  run's tasks (``create_workflow_task`` / ``update_workflow_task``).
* :func:`call_mcp_tool` — invoke one tool on one registered server. The call is
  validated server-side: it must target a tool bound to a task that is currently
  ``in_progress`` in the session, otherwise it is rejected. This enforces the
  per-task tool scoping that a shared, skill-cached agent cannot express through
  its static toolset.

Because of that difference the two tools resolve the current run differently.
``list_mcp_tools`` only needs the tenant, so it accepts both an execution run
(keyed on a WorkflowExecution) and a design run (keyed on a DesignSession).
``call_mcp_tool`` has to check the run's in-progress tasks, so it still requires
a WorkflowExecution and is unavailable while merely designing — a task template
may bind tools, but only a run may invoke them.

Like :mod:`infrastructure.workflow_task_tools`, these callables run during the
AG-UI SSE stream outside FastAPI's request scope, so they open their own
``AsyncSession`` on the module-level engine and return plain JSON-serializable
dicts, mapping every failure to an ``{"error": ...}`` payload the LLM can react
to instead of raising.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from google.adk.tools.tool_context import ToolContext
from mcp import types
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure import database, mcp_client
from infrastructure.mcp_client import McpConnection
from infrastructure.secret_cipher import get_secret_cipher
from infrastructure.secret_resolver import SecretResolver
from infrastructure.vault_client import get_vault_client
from infrastructure.workflow_task_tools import _resolve_scope
from models.workflow_task import WorkflowTaskRead, WorkflowTaskStatus
from repositories import (
    SqlMCPServerRepository,
    SqlSecretRepository,
    SqlWorkflowExecutionRepository,
    SqlWorkflowTaskRepository,
)
from repositories.exceptions import McpConnectionError, SecretResolutionError
from repositories.tenant_bootstrap import (
    NoTenantSessionError,
    resolve_agent_run_tenant,
)

logger = logging.getLogger(__name__)


def _build_resolver(db: AsyncSession, tenant_id: str) -> SecretResolver:
    """Build a SecretResolver on the given session and the process singletons.

    The agent tools run outside FastAPI's request scope, so they cannot use the
    ``SecretResolverDep`` dependency; they compose the resolver from the same
    factory functions the dependency wiring uses.

    Args:
        db: The open database session.
        tenant_id: Tenant the resolved secrets must belong to.

    Returns:
        A resolver backed by the session's secret repository.
    """
    return SecretResolver(
        SqlSecretRepository(db, tenant_id=tenant_id),
        get_secret_cipher(),
        get_vault_client(),
    )


async def _resolve_tenant(tool_context: ToolContext, db: AsyncSession) -> str:
    """Resolve the tenant owning the current run, design or execution alike.

    ``list_mcp_tools`` only needs to know which tenant's registry to read, so
    unlike :func:`infrastructure.workflow_task_tools._resolve_scope` it accepts
    a run keyed on either a WorkflowExecution or a DesignSession. Resolving
    through WorkflowExecution alone would make the tool fail for the whole
    design phase — exactly where the templates' tool bindings are decided.

    Args:
        tool_context: The ADK tool context for the current invocation.
        db: The database session to resolve against.

    Returns:
        The tenant id owning the run.

    Raises:
        NoTenantSessionError: If the session id is missing or matches neither a
            WorkflowExecution nor a DesignSession.
    """
    session = getattr(tool_context, "session", None)
    session_id = getattr(session, "id", None)
    tenant_id = await resolve_agent_run_tenant(db, session_id) if session_id else None
    if tenant_id is None:
        raise NoTenantSessionError()
    return tenant_id


_NO_SESSION = "no workflow execution is bound to the current run; cannot use MCP tools"
_NO_TENANT = (
    "the current run is not bound to a workflow or design session; "
    "cannot list MCP tools"
)
_NO_TASK_IN_PROGRESS = (
    "no task is in_progress; mark a task in_progress with "
    "`update_workflow_task` before calling MCP tools"
)


@asynccontextmanager
async def _db_session() -> AsyncIterator[AsyncSession]:
    """Open a database session on the module-level engine.

    The engine is referenced through the ``database`` module so tests can
    monkeypatch ``database.engine``.

    Yields:
        A fresh ``AsyncSession``.
    """
    async with AsyncSession(database.engine) as db:
        yield db


async def _in_progress_tasks(
    db: AsyncSession, execution_id: str, tenant_id: str
) -> list[WorkflowTaskRead]:
    """Return the session's tasks currently in the ``in_progress`` status."""
    execution_repo = SqlWorkflowExecutionRepository(db, tenant_id=tenant_id)
    task_repo = SqlWorkflowTaskRepository(
        db,
        execution_repo,
        SqlMCPServerRepository(db, tenant_id=tenant_id),
        tenant_id=tenant_id,
    )
    tasks = await task_repo.list(
        limit=1000, offset=0, workflow_execution_id=execution_id
    )
    return [t for t in tasks if t.status == WorkflowTaskStatus.in_progress]


def _coerce_arguments(arguments: object) -> dict[str, Any] | None:
    """Coerce the model-supplied arguments into a dict, or ``None`` if impossible.

    Some models emit the arguments object as a JSON string; tolerate that by
    parsing it.

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
    # Resolve ${secret:NAME/KEY} placeholders while the session is open (the
    # resolver needs the secrets table); the network/process fan-out happens
    # after.
    prepared: list[tuple[dict[str, Any], McpConnection | None, str | None]] = []
    async with _db_session() as db:
        try:
            tenant_id = await _resolve_tenant(tool_context, db)
        except NoTenantSessionError:
            return {"error": _NO_TENANT}
        servers = await SqlMCPServerRepository(db, tenant_id=tenant_id).list(
            limit=1000, offset=0
        )
        resolver = _build_resolver(db, tenant_id)
        for server in servers:
            base = {"server_id": server.id, "server_name": server.name}
            try:
                connection = await mcp_client.resolve_connection(server, resolver)
            except SecretResolutionError as exc:
                logger.warning(
                    "Secret %s resolution failed for MCP server %s: %s",
                    exc.secret_name,
                    server.name,
                    exc.reason,
                )
                error = f"cannot resolve secret {exc.secret_name!r} in headers"
                prepared.append((base, None, error))
                continue
            except McpConnectionError as exc:
                logger.warning(
                    "MCP server %s is not usable: %s", server.name, exc.reason
                )
                prepared.append((base, None, exc.reason))
                continue
            prepared.append((base, connection, None))

    async def _query(base: dict[str, Any], connection: McpConnection) -> dict[str, Any]:
        try:
            tools = await mcp_client.list_server_tools(connection)
        except McpConnectionError as exc:
            logger.warning(
                "MCP server %s unreachable: %s", base["server_name"], exc.reason
            )
            return {**base, "error": f"unreachable: {exc.reason}"}
        return {
            **base,
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                }
                for tool in tools
            ],
        }

    async def _entry(
        base: dict[str, Any],
        connection: McpConnection | None,
        error: str | None,
    ) -> dict[str, Any]:
        if connection is None:
            return {**base, "error": error or "secret resolution failed"}
        return await _query(base, connection)

    return {"servers": list(await asyncio.gather(*(_entry(*p) for p in prepared)))}


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
    async with _db_session() as db:
        try:
            execution_id, tenant_id = await _resolve_scope(tool_context, db)
        except NoTenantSessionError:
            return {"error": _NO_SESSION}
        tasks = await _in_progress_tasks(db, execution_id, tenant_id)
        if not tasks:
            return {"error": _NO_TASK_IN_PROGRESS}
        allowed = {
            (b.mcp_server_id, b.tool_name) for t in tasks for b in t.tool_bindings
        }
        if (server_id, tool_name) not in allowed:
            bound = [{"server_id": s, "tool_name": n} for s, n in sorted(allowed)]
            return {
                "error": (
                    f"tool {tool_name!r} on server {server_id!r} is not bound to "
                    f"the current in-progress task. Bound tools: {bound}"
                )
            }
        server = await SqlMCPServerRepository(db, tenant_id=tenant_id).get(server_id)
        if server is None:
            return {"error": f"MCP server {server_id!r} is not registered"}
        try:
            connection = await mcp_client.resolve_connection(
                server, _build_resolver(db, tenant_id)
            )
        except SecretResolutionError as exc:
            logger.warning(
                "Secret %s resolution failed for MCP server %s: %s",
                exc.secret_name,
                server.name,
                exc.reason,
            )
            return {
                "error": (
                    f"cannot resolve secret {exc.secret_name!r} in the headers "
                    f"of MCP server {server.name!r}"
                )
            }
        except McpConnectionError as exc:
            logger.warning("MCP server %s is not usable: %s", server.name, exc.reason)
            return {"error": f"MCP server {server.name!r} is not usable: {exc.reason}"}
        server_name = server.name
    try:
        result = await mcp_client.call_server_tool(connection, tool_name, args)
    except McpConnectionError as exc:
        logger.warning("MCP server %s unreachable: %s", server_name, exc.reason)
        return {"error": f"MCP server {server_name!r} unreachable: {exc.reason}"}
    return _result_to_dict(result)
