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

from datetime import UTC, datetime, timedelta

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure.mcp_ca import McpCaError, certificate_from_pem
from infrastructure.mcp_certificate import (
    CertificateVerificationError,
    pop_digest,
    verify_pop_signature,
)
from infrastructure.mcp_proxy import (
    McpCallContext,
    McpOperation,
    McpPolicy,
    McpPolicyDeniedError,
)
from models.approval import Approval, ApprovalStatus
from models.workflow_task import WorkflowTaskRead, WorkflowTaskStatus
from repositories import (
    SqlMCPServerRepository,
    SqlWorkflowExecutionRepository,
    SqlWorkflowTaskRepository,
)
from repositories.approval_certificate import SqlApprovalCertificateRepository

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

#: Denial message when every task binding the target tool needs an approval
#: certificate and the caller presented none.
_NO_CREDENTIAL = (
    "this task requires an approval before its MCP tools can be used, and no "
    "approval certificate was presented; wait for the approval to be granted"
)


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


async def _tasks_with_an_approval(
    db: AsyncSession, task_ids: list[str], tenant_id: str
) -> set[str]:
    """Return which of the given tasks have an Approval attached, in one query.

    Status is deliberately not filtered. A task whose approval is still
    ``pending`` has asked for authority it has not been granted, so it must be
    just as unable to call its tools as one whose approval was rejected --
    treating "an approval exists" as the trigger is what makes the gate
    fail-closed.

    Args:
        db: The proxy's open database session.
        task_ids: Tasks to check.
        tenant_id: Tenant the run belongs to.

    Returns:
        The subset of ``task_ids`` that have at least one Approval.
    """
    if not task_ids:
        return set()
    result = await db.exec(
        select(Approval.workflow_task_id).where(
            col(Approval.workflow_task_id).in_(task_ids),
            Approval.tenant_id == tenant_id,
        )
    )
    return {task_id for task_id in result.all() if task_id is not None}


async def _approval(
    db: AsyncSession, approval_id: str, tenant_id: str
) -> Approval | None:
    """Return one Approval within the tenant, or ``None``.

    Args:
        db: The proxy's open database session.
        approval_id: The approval to load.
        tenant_id: Tenant the run belongs to.

    Returns:
        The approval, or ``None`` when it does not exist in this tenant.
    """
    result = await db.exec(
        select(Approval).where(
            Approval.id == approval_id, Approval.tenant_id == tenant_id
        )
    )
    return result.first()


class ApprovedTaskCertificatePolicy:
    """Requires a valid approval certificate for tasks that have an approval.

    The rule in one sentence: if every ``in_progress`` task that binds the
    target tool has an Approval attached, the call must present that approval's
    certificate, and the certificate's own signed grant must cover the tool.

    Scoped that precisely on purpose. A run may have several tasks underway; if
    any of the ones binding this tool needs no approval, the call is already
    legitimate under :class:`InProgressToolBindingPolicy`, and demanding a
    certificate would break a workflow that never asked for one.

    What the certificate adds over the binding policy is that its grant was
    **signed at decision time**. The execution agent can rewrite its own task's
    ``tool_bindings`` mid-run, so a rule that reads bindings at call time is a
    rule the agent can widen. It cannot re-sign a certificate.

    Registered after :class:`InProgressToolBindingPolicy` so the cheap
    binding-scope denial short-circuits before this one's extra queries and
    signature verification.
    """

    async def authorize(self, ctx: McpCallContext, db: AsyncSession) -> None:
        """Allow the call only if the approval it depends on backs it.

        Args:
            ctx: The operation being attempted.
            db: The proxy's open database session.

        Raises:
            McpPolicyDeniedError: If an approval-gated call presents no
                certificate, presents one bound to a different tenant, run,
                task, or approval, presents one whose approval is no longer
                granted or whose certificate was revoked, fails proof of
                possession, or targets a tool the certificate does not grant.
        """
        if ctx.operation is not McpOperation.call_tool:
            return
        if ctx.identity.execution_id is None:
            # InProgressToolBindingPolicy already denied this; nothing to add.
            return

        tasks = await _in_progress_tasks(
            db, ctx.identity.execution_id, ctx.identity.tenant_id
        )
        binding_tasks = [
            task
            for task in tasks
            if any(
                b.mcp_server_id == ctx.server_id and b.tool_name == ctx.tool_name
                for b in task.tool_bindings
            )
        ]
        if not binding_tasks:
            # Only reachable if this policy is registered without the binding
            # policy in front of it. Leave the denial to that one's message.
            return

        gated = await _tasks_with_an_approval(
            db, [task.id for task in binding_tasks], ctx.identity.tenant_id
        )
        if len(gated) < len(binding_tasks):
            # At least one task binding this tool needs no approval.
            return

        verified = ctx.identity.credential
        presented = ctx.principal.credential
        if verified is None or presented is None:
            raise McpPolicyDeniedError(_NO_CREDENTIAL)

        binding = verified.claims.binding
        if (
            binding.tenant_id != ctx.identity.tenant_id
            or binding.execution_id != ctx.identity.execution_id
        ):
            raise McpPolicyDeniedError(
                "the presented approval certificate belongs to a different run"
            )
        if binding.task_id not in {task.id for task in binding_tasks}:
            raise McpPolicyDeniedError(
                "the presented approval certificate authorizes a different task"
            )

        certificates = SqlApprovalCertificateRepository(
            db, tenant_id=ctx.identity.tenant_id
        )
        row = await certificates.get_by_serial(verified.claims.serial_number)
        if row is None:
            raise McpPolicyDeniedError(
                "the presented approval certificate is not one this deployment issued"
            )
        if row.revoked_at is not None:
            raise McpPolicyDeniedError(
                "the approval certificate for this task has been revoked"
            )
        if row.approval_id != binding.approval_id:
            raise McpPolicyDeniedError(
                "the presented approval certificate does not match its recorded approval"
            )

        approval = await _approval(db, binding.approval_id, ctx.identity.tenant_id)
        if approval is None or approval.status != ApprovalStatus.approved:
            raise McpPolicyDeniedError(
                "the approval backing this task is no longer granted"
            )

        settings = get_settings()
        digest = pop_digest(
            session_id=ctx.principal.session_id,
            mcp_server_id=ctx.server_id or "",
            tool_name=ctx.tool_name or "",
            arguments=ctx.arguments or {},
            nonce=presented.nonce,
            timestamp=presented.timestamp,
        )
        try:
            verify_pop_signature(
                certificate_from_pem(verified.certificate_pem),
                signature=presented.signature,
                digest=digest,
                timestamp=presented.timestamp,
                now=datetime.now(UTC),
                window=timedelta(
                    seconds=settings.mcp_approval_cert_signature_window_seconds
                ),
            )
        except (McpCaError, CertificateVerificationError) as exc:
            raise McpPolicyDeniedError(
                f"the approval certificate was not proven to belong to this "
                f"caller: {exc}"
            ) from exc

        if not verified.claims.grants(ctx.server_id or "", ctx.tool_name or ""):
            granted = [
                {"server_id": s, "tool_name": n}
                for s, n in sorted(verified.claims.allowed_tools)
            ]
            raise McpPolicyDeniedError(
                f"tool {ctx.tool_name!r} on server {ctx.server_id!r} was not granted "
                f"by the approval for this task. Granted tools: {granted}"
            )


def default_policies() -> list[McpPolicy]:
    """Return the policy chain the process-wide proxy is built with.

    Two rules are enforced. First, an agent may invoke only the MCP tools bound
    to a task currently in progress in its run. Second, a task that has an
    approval attached must additionally present that approval's certificate,
    whose signed grant covers the tool.

    Ordered cheapest first -- the chain short-circuits on the first denial, and
    the binding check is a subset of what the certificate check would otherwise
    have to establish. Further policies (rate limits, per-caller authorization)
    are appended here.

    Returns:
        The ordered policy chain.
    """
    return [InProgressToolBindingPolicy(), ApprovedTaskCertificatePolicy()]
