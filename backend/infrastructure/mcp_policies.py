"""Access-control policies the MCP proxy consults before every operation.

Kept apart from :mod:`infrastructure.mcp_proxy` on purpose. A policy queries
the database, so this module depends on :mod:`repositories`; the proxy itself
does not need those imports and would turn back into the same god-module the
proxy was extracted from if it carried them. Adding a rule means adding a class
here and a line to :func:`default_policies` -- never an edit to the proxy.

A policy never re-resolves the caller: everything it needs about who is calling
arrives on :class:`infrastructure.mcp_proxy.McpCallContext`, already
authenticated.
"""

from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.mcp_proxy import (
    McpCallContext,
    McpOperation,
    McpPolicy,
    McpPolicyDeniedError,
)
from models.workflow_task import WorkflowTaskRead, WorkflowTaskStatus
from repositories import (
    SqlMCPServerRepository,
    SqlWorkflowExecutionRepository,
    SqlWorkflowTaskRepository,
)

#: Denial message when the run has no WorkflowExecution to take bindings from.
_NO_EXECUTION = (
    "no workflow execution is bound to the current run; cannot use MCP tools"
)

#: Denial message when the run has a WorkflowExecution but no task underway.
_NO_TASK_IN_PROGRESS = (
    "no task is in_progress; mark a task in_progress with "
    "`update_workflow_task` before calling MCP tools"
)

#: Upper bound on how many of a run's tasks one authorization check reads.
_MAX_TASKS = 1000


async def _in_progress_tasks(
    db: AsyncSession, execution_id: str, tenant_id: str
) -> list[WorkflowTaskRead]:
    """Return the run's tasks currently in the ``in_progress`` status.

    Args:
        db: The proxy's open database session.
        execution_id: The WorkflowExecution driving the run.
        tenant_id: Tenant the run belongs to.

    Returns:
        The run's ``in_progress`` tasks, each with its tool bindings resolved.
    """
    execution_repo = SqlWorkflowExecutionRepository(db, tenant_id=tenant_id)
    task_repo = SqlWorkflowTaskRepository(
        db,
        execution_repo,
        SqlMCPServerRepository(db, tenant_id=tenant_id),
        tenant_id=tenant_id,
    )
    tasks = await task_repo.list(
        limit=_MAX_TASKS, offset=0, workflow_execution_id=execution_id
    )
    return [t for t in tasks if t.status == WorkflowTaskStatus.in_progress]


class PassThroughPolicy:
    """Allows everything.

    The base for a policy that guards only some operations, and the thing to
    register when a chain must exist but decide nothing.
    """

    async def authorize(self, ctx: McpCallContext, db: AsyncSession) -> None:
        """Allow the operation unconditionally.

        Args:
            ctx: The operation being attempted.
            db: The proxy's open database session.
        """


class InProgressToolBindingPolicy:
    """Restricts a run to the MCP tools bound to a task it is currently working on.

    A single ``ADKAgent`` is cached per skill and serves every session using it,
    so the agent's static toolset cannot express per-task tool scoping -- the
    only place that scoping can be enforced is here, at the moment of the call.
    The union of the bindings of every ``in_progress`` task in the run is
    allowed; anything else is refused with the allowed list, so the model can
    correct itself.

    Listing is deliberately unrestricted: the design agents call
    ``list_mcp_tools`` precisely to decide what to bind.
    """

    async def authorize(self, ctx: McpCallContext, db: AsyncSession) -> None:
        """Allow the call only if the target tool is bound to a task underway.

        Args:
            ctx: The operation being attempted.
            db: The proxy's open database session.

        Raises:
            McpPolicyDeniedError: If the run has no WorkflowExecution, no task
                is ``in_progress``, or the target tool is not among the bindings
                of the tasks that are.
        """
        if ctx.operation is not McpOperation.call_tool:
            return
        if ctx.identity.execution_id is None:
            raise McpPolicyDeniedError(_NO_EXECUTION)
        tasks = await _in_progress_tasks(
            db, ctx.identity.execution_id, ctx.identity.tenant_id
        )
        if not tasks:
            raise McpPolicyDeniedError(_NO_TASK_IN_PROGRESS)
        allowed = {
            (b.mcp_server_id, b.tool_name) for t in tasks for b in t.tool_bindings
        }
        if (ctx.server_id, ctx.tool_name) not in allowed:
            bound = [{"server_id": s, "tool_name": n} for s, n in sorted(allowed)]
            raise McpPolicyDeniedError(
                f"tool {ctx.tool_name!r} on server {ctx.server_id!r} is not bound to "
                f"the current in-progress task. Bound tools: {bound}"
            )


def default_policies() -> list[McpPolicy]:
    """Return the policy chain the process-wide proxy is built with.

    Exactly one rule is enforced today: an agent may invoke only the MCP tools
    bound to a task currently in progress in its run. Further policies
    (per-caller authorization, rate limits) are appended here, cheapest first --
    the chain short-circuits on the first denial.

    Returns:
        The ordered policy chain.
    """
    return [InProgressToolBindingPolicy()]
