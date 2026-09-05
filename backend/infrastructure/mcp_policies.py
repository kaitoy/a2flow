"""Access-control policies the MCP gateway consults before every operation.

Kept apart from :mod:`infrastructure.mcp_gateway` on purpose. A policy queries
the database, so this module depends on :mod:`repositories`; the gateway itself
does not need those imports and would turn back into the same god-module the
gateway was extracted from if it carried them. Adding a rule means adding a class
here and a line to :func:`default_policies` -- never an edit to the gateway.

A policy never re-resolves the caller: everything it needs about who is calling
arrives on :class:`infrastructure.mcp_gateway.McpCallContext`, already
authenticated.
"""

from datetime import UTC, datetime, timedelta

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure.approval_scope import active_approval_by_task, governing_approvals
from infrastructure.approved_calls import match_call
from infrastructure.mcp_ca import McpCaError, certificate_from_pem
from infrastructure.mcp_certificate import (
    CertificateBinding,
    CertificateVerificationError,
    pop_digest,
    verify_pop_signature,
)
from infrastructure.mcp_gateway import (
    McpCallContext,
    McpOperation,
    McpPolicy,
    McpPolicyDeniedError,
)
from models.approval import Approval, ApprovalStatus, ApprovedCall
from models.workflow_execution import WorkflowExecution
from models.workflow_task import WorkflowTaskRead, WorkflowTaskStatus
from repositories import (
    SqlMCPServerRepository,
    SqlWorkflowExecutionRepository,
    SqlWorkflowTaskRepository,
)
from repositories.mcp_tool_certificate import SqlMcpToolCertificateRepository

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

#: Denial message when the caller presented no certificate at all. Every call
#: needs one, so this is what an agent sees when the task it is working on never
#: got a grant: it is not ``in_progress``, it bound its tools only after it
#: started, or it is waiting on an approval nobody has granted yet.
_NO_CREDENTIAL = (
    "no tool certificate was presented for this task, so it may not call MCP "
    "tools. A task is granted one when it is marked in_progress, over exactly "
    "the tools bound to it at that moment -- bind a task's tools before or in "
    "the same call that starts it. A task covered by an approval -- its own, or "
    "one requested on a task it descends from -- is granted nothing until that "
    "approval is granted."
)


async def _in_progress_tasks(
    db: AsyncSession, execution_id: str, tenant_id: str
) -> list[WorkflowTaskRead]:
    """Return the run's tasks currently in the ``in_progress`` status.

    Args:
        db: The gateway's open database session.
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
            db: The gateway's open database session.
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
            db: The gateway's open database session.

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


async def _run_approvals(
    db: AsyncSession, execution_id: str, tenant_id: str
) -> list[Approval]:
    """Return every Approval of the run, in one query.

    Args:
        db: The gateway's open database session.
        execution_id: The WorkflowExecution driving the run.
        tenant_id: Tenant the run belongs to.

    Returns:
        The run's approvals.
    """
    result = await db.exec(
        select(Approval).where(
            Approval.workflow_execution_id == execution_id,
            Approval.tenant_id == tenant_id,
        )
    )
    return list(result.all())


async def _governing_approvals(
    db: AsyncSession, execution_id: str, tenant_id: str, task_id: str
) -> list[Approval]:
    """Return the approvals that govern one task of a run.

    "Govern" is the nearest-approval rule of
    :mod:`infrastructure.approval_scope`: the task's own approval when it has
    one, otherwise whatever governs the tasks it depends on, collected across
    every branch of a merge.

    Args:
        db: The gateway's open database session.
        execution_id: The WorkflowExecution driving the run.
        tenant_id: Tenant the run belongs to.
        task_id: The task to resolve.

    Returns:
        The governing approvals, empty when none governs the task.
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
    approvals = await _run_approvals(db, execution_id, tenant_id)
    governing = governing_approvals(tasks, active_approval_by_task(approvals))
    approval_ids = governing.get(task_id, frozenset())
    return [approval for approval in approvals if approval.id in approval_ids]


async def _execution_initiator(
    db: AsyncSession, execution_id: str, tenant_id: str
) -> str | None:
    """Return who started the run, or ``None`` when it cannot be resolved.

    Read straight off the row rather than trusted from the certificate: an
    initiator grant claims a user id, and this is what that claim is checked
    against.

    Args:
        db: The gateway's open database session.
        execution_id: The WorkflowExecution driving the run.
        tenant_id: Tenant the run belongs to.

    Returns:
        The run's ``initiator_id``, or ``None`` when no such run exists in this
        tenant.
    """
    result = await db.exec(
        select(WorkflowExecution.initiator_id).where(
            WorkflowExecution.id == execution_id,
            WorkflowExecution.tenant_id == tenant_id,
        )
    )
    return result.first()


async def _assert_grantor_still_authorizes(
    ctx: McpCallContext, db: AsyncSession, binding: CertificateBinding
) -> None:
    """Re-check, at call time, that the grantor named in the binding still stands.

    A certificate is signed once and lives for its whole TTL, so everything that
    could have changed since has to be read fresh here. What "changed" means
    differs per grantor, which is why the two forms are checked separately
    rather than through one shared rule.

    Args:
        ctx: The operation being attempted.
        db: The gateway's open database session.
        binding: The presented certificate's binding, already matched against
            the run and the task.

    Raises:
        McpPolicyDeniedError: If an approval grant names an approval that no
            longer governs the task, or any approval that does govern it is not
            ``approved``, or an initiator grant names someone other than the
            run's initiator or belongs to a task an approval has since claimed.
    """
    governing = await _governing_approvals(
        db,
        ctx.identity.execution_id or "",
        ctx.identity.tenant_id,
        binding.task_id,
    )

    if binding.approval_id is not None:
        # Which approval governs the task is re-derived here rather than trusted
        # from the certificate: a request made *after* this one was issued can
        # take the task over, and the outer approval's grant must stop counting
        # the moment it does.
        if binding.approval_id not in {approval.id for approval in governing}:
            raise McpPolicyDeniedError(
                "the approval this tool certificate carries no longer governs this task"
            )
        # Every governing approval, not just the one named: a task where two
        # gated branches merge is authorized by both approvers or by neither.
        if any(approval.status != ApprovalStatus.approved for approval in governing):
            raise McpPolicyDeniedError(
                "the approval backing this task is no longer granted"
            )
        return

    initiator_id = await _execution_initiator(
        db, ctx.identity.execution_id or "", ctx.identity.tenant_id
    )
    if initiator_id is None or binding.initiator_id != initiator_id:
        raise McpPolicyDeniedError(
            "the presented tool certificate was not granted by this run's initiator"
        )
    if governing:
        raise McpPolicyDeniedError(
            "this task now needs an approval, so the initiator's own grant no "
            "longer authorizes it; wait for the approval to be granted"
        )


class TaskCertificatePolicy:
    """Requires a valid tool certificate on every call, whoever granted it.

    The rule in one sentence: the call must present a certificate issued by this
    deployment for one of the ``in_progress`` tasks that bind the target tool,
    prove it holds that certificate's key, and the certificate's own signed
    grant must cover the tool.

    There is no exemption. A task an approver cleared -- directly, or by
    clearing an approval it descends from -- presents that approval's
    certificate; a task no approval governs presents the one the run's
    initiator took out for themselves when it started (see
    :meth:`services.mcp_tool_certificate.McpToolCertificateService.issue_for_started_task`).
    Either way something signed authorized the call, and the audit row records
    which.

    What the certificate adds over the binding policy is that its grant was
    **signed at issuance**. A run's ``tool_bindings`` come from the workflow's
    published templates copied at execute time and the execution agent cannot
    edit them, but a rule that re-read bindings at call time would still trust
    whatever the row says now -- a later edit to the workflow, say. The signed
    grant does not: it cannot be re-signed after issuance.

    The two grantors are not interchangeable, and this is where that is
    enforced: an initiator grant is refused for any task an approval governs,
    whatever the approval's status. Without that, a run could start a task,
    pocket the initiator's certificate, and only then request the approval it
    was supposed to be waiting for.

    Which approval governs a task is derived from the run's dependency graph on
    every call (:mod:`infrastructure.approval_scope`) rather than read off the
    certificate, so an approval requested *after* a certificate was issued takes
    the task over immediately and the older grant stops counting.

    Registered after :class:`InProgressToolBindingPolicy` so the cheap
    binding-scope denial short-circuits before this one's extra queries and
    signature verification.
    """

    async def authorize(self, ctx: McpCallContext, db: AsyncSession) -> None:
        """Allow the call only if a signed grant still backs it.

        Args:
            ctx: The operation being attempted.
            db: The gateway's open database session.

        Raises:
            McpPolicyDeniedError: If the call presents no certificate, presents
                one bound to a different tenant, run, task, or approval,
                presents one this deployment did not issue or has revoked,
                presents an approval grant whose approval no longer governs the
                task or is no longer granted, presents an initiator grant that
                names the wrong user or belongs to a task an approval has since
                claimed, fails proof of possession, or targets a tool the
                certificate does not grant.
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
                "the presented tool certificate belongs to a different run"
            )
        if binding.task_id not in {task.id for task in binding_tasks}:
            raise McpPolicyDeniedError(
                "the presented tool certificate authorizes a different task"
            )

        certificates = SqlMcpToolCertificateRepository(
            db, tenant_id=ctx.identity.tenant_id
        )
        row = await certificates.get_by_serial(verified.claims.serial_number)
        if row is None:
            raise McpPolicyDeniedError(
                "the presented tool certificate is not one this deployment issued"
            )
        if row.revoked_at is not None:
            raise McpPolicyDeniedError(
                "the tool certificate for this task has been revoked"
            )
        if row.approval_id != binding.approval_id:
            # Both are ``None`` for an initiator grant, so this one comparison
            # also catches a certificate claiming a grantor its row disagrees
            # with -- an approval URN on an initiator row, or the reverse.
            raise McpPolicyDeniedError(
                "the presented tool certificate does not match its recorded grant"
            )

        await _assert_grantor_still_authorizes(ctx, db, binding)

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
                    seconds=settings.mcp_tool_cert_signature_window_seconds
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


class ApprovedArgumentsPolicy:
    """Holds a call to the arguments the approver actually approved.

    :class:`TaskCertificatePolicy` establishes that *something* signed
    authorized this tool for this task. It says nothing about what the call
    carries -- the certificate's grant is a set of ``(server, tool)`` pairs, and
    a decision made on "terminate instance i-123" would equally authorize
    ``terminate_instances(["i-456"])``. This policy closes that gap: the
    approval's own ``approved_calls`` declaration, recorded when the request was
    made and shown to the approver before they decided, is matched against the
    call's arguments by :mod:`infrastructure.approved_calls`.

    **Every** governing approval must permit the call, not merely one, matching
    the rule :func:`_assert_grantor_still_authorizes` already applies to their
    statuses: a task where two gated branches merge is authorized by both
    approvers or by neither, and the laxer declaration must not speak for the
    stricter one.

    **An initiator grant is untouched.** A task no approval governs has no
    declaration, and no approver to have deviated from; what bounds it is
    unchanged. The two grantors cannot be confused here because
    :class:`TaskCertificatePolicy` has already refused an initiator grant for
    any approval-governed task.

    **A tool the workflow's design exempted from input approval is skipped
    too**, but not by this policy resolving anything: the request path already
    recorded it in the declaration as an entry permitting any arguments, and
    :func:`infrastructure.approved_calls.match_call` reads it there. So this
    rule needs no notion of a binding's flag, and the declaration on the row
    stays the only thing it consults. The approval itself still applies to such
    a tool -- :class:`TaskCertificatePolicy` above has already required a
    granted approval's certificate for it.

    **An approval with an empty declaration is skipped**, which is what makes
    this safe to deploy over a running system: a request recorded before this
    field existed has nothing to match, and there is no path by which an
    approver could supply one after the fact. Nothing new can reach that state
    -- :func:`infrastructure.approval_tools.request_approval` now requires a
    declaration covering every tool the covered tasks bind, and no other writer
    can reach the column.

    Registered last. It is the most expensive rule in the chain, and it is the
    only one that needs a task id it can trust: the binding policy allows the
    *union* of every in-progress task's bindings, so only after
    :class:`TaskCertificatePolicy` has checked the presented certificate against
    the run, the task, the certificate row and the proof of possession is
    ``binding.task_id`` something to resolve an approval from. Running it last
    also keeps a caller with no authority at all from learning what a
    declaration says.
    """

    async def authorize(self, ctx: McpCallContext, db: AsyncSession) -> None:
        """Allow the call only if it fits every governing approval's declaration.

        Args:
            ctx: The operation being attempted.
            db: The gateway's open database session.

        Raises:
            McpPolicyDeniedError: If any approval governing the task declares a
                set of calls this one falls outside -- a tool it does not name,
                an argument it does not mention, an argument it requires but the
                call omits, or a value outside the declared bounds.
        """
        if ctx.operation is not McpOperation.call_tool:
            return
        if ctx.identity.execution_id is None:
            # InProgressToolBindingPolicy already denied this; nothing to add.
            return
        verified = ctx.identity.credential
        if verified is None:
            # TaskCertificatePolicy already denied this; leave it its message.
            return
        binding = verified.claims.binding
        if binding.approval_id is None:
            return

        governing = await _governing_approvals(
            db,
            ctx.identity.execution_id,
            ctx.identity.tenant_id,
            binding.task_id,
        )
        for approval in governing:
            if not approval.approved_calls:
                continue
            declaration = [
                ApprovedCall.model_validate(entry) for entry in approval.approved_calls
            ]
            reason = match_call(
                declaration,
                server_id=ctx.server_id or "",
                tool_name=ctx.tool_name or "",
                arguments=ctx.arguments or {},
            )
            if reason is not None:
                raise McpPolicyDeniedError(reason)


def default_policies() -> list[McpPolicy]:
    """Return the policy chain the process-wide gateway is built with.

    Three rules are enforced. First, an agent may invoke only the MCP tools
    bound to a task currently in progress in its run. Second, every call must
    present a valid certificate for that task -- an approver's, or the run
    initiator's own -- whose signed grant covers the tool. Third, a call made
    under an approver's authority must carry the arguments that approver
    approved.

    Ordered cheapest first -- the chain short-circuits on the first denial, and
    each check is a subset of what the next would otherwise have to establish:
    the binding check narrows what the certificate check must consider, and the
    certificate check is what makes the task id the argument check resolves from
    trustworthy. Further policies (rate limits, per-caller authorization) are
    appended here.

    Returns:
        The ordered policy chain.
    """
    return [
        InProgressToolBindingPolicy(),
        TaskCertificatePolicy(),
        ApprovedArgumentsPolicy(),
    ]
