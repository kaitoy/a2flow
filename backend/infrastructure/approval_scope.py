"""Which approval governs which task, read off the run's task graph.

An approval does not authorize one task. It authorizes the task it names **and
everything downstream of that task, up to the next approval** -- so a workflow
can put the request in a step of its own ("Ask for a go-ahead") and have the
decision cover the steps that follow it ("Launch instance", "Tag instance")
without naming each one.

Stated from the other end, which is how both the gate and the grant ask the
question: a task is governed by the **nearest** approval at or above it in the
dependency graph.

    approval A                     approval B
        |                              |
        v                              v
    [ask] --> [launch] --> [tag] --> [ask] --> [delete]
     {A}        {A}         {A}       {B}        {B}

A task with no approval anywhere above it is governed by nobody, and runs on the
authority its run's initiator granted itself
(:meth:`services.mcp_tool_certificate.McpToolCertificateService.issue_for_started_task`).

Everything here is pure -- no session, no ORM query, no settings -- for the same
reason :mod:`infrastructure.mcp_certificate` is: the rule is the security-
relevant part, and it should be testable without a database. Callers load the
run's tasks and approvals themselves and pass them in.

**Merges take every path.** A task reachable from two gated branches is governed
by both approvals, and :mod:`infrastructure.mcp_policies` requires *all* of them
to be granted before it may call anything. One approver clearing their own
branch must not speak for the other's.

**One gate per task.** A task may carry several Approval rows -- a rejected
request followed by a re-request, say -- but only one of them gates it at a
time: the unresolved one if there is one, otherwise the most recent. That is the
same "active approval" rule :meth:`repositories.approval.SqlApprovalRepository.get_for_task`
applies, and keeping the two in step is what stops a task from being wedged
forever by a rejection it has already superseded.
"""

from collections.abc import Iterable, Mapping, Sequence

from models.approval import Approval, ApprovalStatus
from models.workflow_task import WorkflowTaskRead


def active_approval_by_task(approvals: Iterable[Approval]) -> dict[str, str]:
    """Return the id of the approval currently gating each task.

    Mirrors :meth:`repositories.approval.SqlApprovalRepository.get_for_task`: a
    task's ``pending`` approval is the active one, and when it has none, the
    most recently created. A task whose only approval was rejected therefore
    stays gated by that rejection -- until a fresh request supersedes it.

    Args:
        approvals: Every approval of one run, in any order.

    Returns:
        Task id to the id of the approval gating it. Approvals not linked to a
        task are ignored, since they gate nothing.
    """
    chosen: dict[str, Approval] = {}
    for approval in approvals:
        task_id = approval.workflow_task_id
        if task_id is None:
            continue
        current = chosen.get(task_id)
        if current is None or _outranks(approval, current):
            chosen[task_id] = approval
    return {task_id: approval.id for task_id, approval in chosen.items()}


def _outranks(candidate: Approval, incumbent: Approval) -> bool:
    """Return whether ``candidate`` should gate the task instead of ``incumbent``.

    Args:
        candidate: The approval being considered.
        incumbent: The approval currently chosen for the same task.

    Returns:
        ``True`` when the candidate is unresolved and the incumbent is not, or
        when neither is unresolved and the candidate is the newer of the two.
    """
    candidate_pending = candidate.status == ApprovalStatus.pending
    incumbent_pending = incumbent.status == ApprovalStatus.pending
    if candidate_pending != incumbent_pending:
        return candidate_pending
    return candidate.created_at > incumbent.created_at


def governing_approvals(
    tasks: Sequence[WorkflowTaskRead], active_by_task: Mapping[str, str]
) -> dict[str, frozenset[str]]:
    """Return the approvals governing each task of a run.

    A task carrying its own gate is governed by that gate alone -- the nearer
    approval displaces whatever covered the ground above it. Otherwise the task
    inherits the union of what governs its dependencies, so a merge collects
    every branch's gate.

    Iterative rather than recursive: a run may hold up to a thousand tasks, and
    a chain that long would overflow the interpreter's stack.

    Args:
        tasks: Every task of the run. Dependency edges pointing outside this
            set are ignored.
        active_by_task: Task id to gating approval id, from
            :func:`active_approval_by_task`.

    Returns:
        Task id to the (possibly empty) set of approval ids governing it.
    """
    known = {task.id for task in tasks}
    parents = {
        task.id: [dep for dep in task.depends_on_ids if dep in known] for task in tasks
    }
    resolved: dict[str, frozenset[str]] = {}
    #: Ids currently on the walk. Edges are a DAG (the repository rejects
    #: cycles before insertion), so this only guards against a graph that
    #: somehow became cyclic anyway -- a back edge contributes nothing rather
    #: than spinning forever.
    walking: set[str] = set()

    for root in known:
        if root in resolved:
            continue
        stack = [root]
        while stack:
            current = stack[-1]
            if current in resolved:
                stack.pop()
                walking.discard(current)
                continue
            gate = active_by_task.get(current)
            if gate is not None:
                resolved[current] = frozenset({gate})
                stack.pop()
                walking.discard(current)
                continue
            walking.add(current)
            unresolved = [
                dep
                for dep in parents[current]
                if dep not in resolved and dep not in walking
            ]
            if unresolved:
                stack.extend(unresolved)
                continue
            resolved[current] = frozenset(
                approval_id
                for dep in parents[current]
                for approval_id in resolved.get(dep, ())
            )
            stack.pop()
            walking.discard(current)
    return resolved


def covered_task_ids(
    tasks: Sequence[WorkflowTaskRead],
    active_by_task: Mapping[str, str],
    approval_id: str,
) -> frozenset[str]:
    """Return the tasks one approval governs.

    The inverse of :func:`governing_approvals`, for the callers that start from
    an approval rather than from a task: standing down the grants a new approval
    has just taken responsibility for, and issuing under a decision that has
    just been made.

    Args:
        tasks: Every task of the run.
        active_by_task: Task id to gating approval id, from
            :func:`active_approval_by_task`.
        approval_id: The approval to collect the covered tasks of.

    Returns:
        The ids of the tasks this approval governs, empty when it governs none
        (it may have been superseded on its own task by a newer request).
    """
    governing = governing_approvals(tasks, active_by_task)
    return frozenset(
        task_id
        for task_id, approval_ids in governing.items()
        if approval_id in approval_ids
    )
