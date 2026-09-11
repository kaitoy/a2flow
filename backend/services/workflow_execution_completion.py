"""Completion bookkeeping shared by every path that writes a WorkflowTask.

A WorkflowExecution has no explicit "finish" call: a run is over once it has at
least one task and every one of them has reached a terminal state. That has to
be re-evaluated after each task write, and task writes arrive through two
independent paths — the agent's tools (``infrastructure/workflow_task_tools.py``,
running outside FastAPI's request scope on their own session) and the REST task
endpoints (``services/workflow_task.py``). This module holds the rule once so
both stamp the same lifecycle.

A failed task also skips its blocked dependents here. Any task that transitively
depends on a ``failed`` one can never become runnable — the execution agent only
starts a task once its dependencies are ``completed`` — so without this the run
would never satisfy "every task terminal" and would hang in ``running`` forever.
Marking those tasks ``skipped`` (they did not run) lets the normal rule settle
the run ``failed``.

It is a module-level function rather than a method on
:class:`services.workflow_execution.WorkflowExecutionService` deliberately: that
service carries the ADK registry, skill store, and session service needed for
agent resolution, none of which completion bookkeeping wants. Taking only the
three repositories it actually reads keeps it callable from the agent tools,
which construct their repositories by hand.
"""

import logging
from datetime import UTC, datetime

from models.notification import NotificationCreate, NotificationType
from models.workflow_execution import WorkflowExecutionStatus
from models.workflow_task import (
    WorkflowTaskRead,
    WorkflowTaskStatus,
    WorkflowTaskUpdate,
)
from repositories.workflow_execution import WorkflowExecutionRepository
from repositories.workflow_task import WorkflowTaskRepository
from services.notification_dispatch import NotificationDispatcher

logger = logging.getLogger(__name__)

#: WorkflowTask statuses that count as "done" for run-completion detection.
TERMINAL_TASK_STATUSES = frozenset(
    {
        WorkflowTaskStatus.completed,
        WorkflowTaskStatus.failed,
        WorkflowTaskStatus.skipped,
    }
)

#: Ceiling on the tasks read when evaluating completion. Runs are expected to
#: hold far fewer; a run that somehow exceeds it simply never registers as
#: finished, which is the safe direction to fail in.
_TASK_SCAN_LIMIT = 1000


async def _skip_blocked_dependents(
    tasks: WorkflowTaskRepository,
    run_tasks: list[WorkflowTaskRead],
    acting_user_id: str,
) -> int:
    """Mark every ``pending`` task that transitively depends on a failed one ``skipped``.

    A task whose dependency has ``failed`` can never become runnable — the
    execution agent only starts a task once its ``depends_on_ids`` are all
    ``completed`` — so leaving it ``pending`` would keep the run from ever
    satisfying "every task terminal". Skipping it (it did not run) lets
    :func:`evaluate_completion` settle the run on its normal rule.

    The dependency graph is read straight off ``run_tasks`` (each
    :class:`WorkflowTaskRead` already carries ``depends_on_ids``), so this adds
    no query beyond the one write per newly skipped task.

    Args:
        tasks: Repository used to write the ``skipped`` status.
        run_tasks: The run's tasks as just read.
        acting_user_id: Recorded on each skipped task's ``updated_by``.

    Returns:
        How many tasks were moved to ``skipped``.
    """
    failed_ids = {t.id for t in run_tasks if t.status == WorkflowTaskStatus.failed}
    if not failed_ids:
        return 0
    dependents: dict[str, set[str]] = {}
    for task in run_tasks:
        for dep_id in task.depends_on_ids:
            dependents.setdefault(dep_id, set()).add(task.id)
    blocked: set[str] = set()
    queue = list(failed_ids)
    while queue:
        current = queue.pop()
        for dependent_id in dependents.get(current, ()):
            if dependent_id not in blocked:
                blocked.add(dependent_id)
                queue.append(dependent_id)
    by_id = {t.id: t for t in run_tasks}
    skipped = 0
    for task_id in blocked:
        blocked_task = by_id.get(task_id)
        if (
            blocked_task is not None
            and blocked_task.status == WorkflowTaskStatus.pending
        ):
            await tasks.update(
                task_id,
                WorkflowTaskUpdate(status=WorkflowTaskStatus.skipped),
                user_id=acting_user_id,
            )
            skipped += 1
    return skipped


async def evaluate_completion(
    *,
    executions: WorkflowExecutionRepository,
    tasks: WorkflowTaskRepository,
    notifications: NotificationDispatcher,
    execution_id: str,
    acting_user_id: str,
) -> None:
    """Finish a run whose tasks have all reached a terminal state.

    When every task of the run is terminal (and there is at least one), stamps
    the execution's ``status`` and ``finished_at`` and emits the one-shot
    ``execution_completed`` notification. The run is marked ``failed`` if any
    task failed and ``completed`` otherwise; a ``skipped`` task on its own does
    not make the run a failure.

    If a task has ``failed``, every still-``pending`` task that transitively
    depends on it is marked ``skipped`` first (see
    :func:`_skip_blocked_dependents`): those tasks can never run, and skipping
    them is what lets a run whose failure left dependents behind settle instead
    of hanging in ``running``.

    A run with no tasks stays ``running``: an empty list is indistinguishable
    from a run whose agent has not registered its tasks yet.

    Both writes are idempotent — ``mark_finished`` ignores an execution that
    already has a ``finished_at``, and the notification is guarded by
    ``exists_for_session`` — so calling this after every task write is safe.

    This is best-effort bookkeeping on the side of a task write that has already
    committed: every failure is logged and swallowed, so a completion that
    cannot be recorded never fails the caller's own operation.

    Args:
        executions: Repository used to resolve and stamp the execution.
        tasks: Repository used to read the run's tasks and skip blocked ones.
        notifications: Dispatcher used to check for, persist, and email the
            one-shot completion notification.
        execution_id: Primary key of the workflow execution to evaluate.
        acting_user_id: Recorded on the ``updated_by`` of any task this skips as
            a blocked dependent of a failed one.
    """
    try:
        run_tasks = await tasks.list(
            limit=_TASK_SCAN_LIMIT, offset=0, workflow_execution_id=execution_id
        )
        if not run_tasks:
            return
        if await _skip_blocked_dependents(tasks, run_tasks, acting_user_id):
            run_tasks = await tasks.list(
                limit=_TASK_SCAN_LIMIT, offset=0, workflow_execution_id=execution_id
            )
        if any(t.status not in TERMINAL_TASK_STATUSES for t in run_tasks):
            return
        status = (
            WorkflowExecutionStatus.failed
            if any(t.status == WorkflowTaskStatus.failed for t in run_tasks)
            else WorkflowExecutionStatus.completed
        )
        await executions.mark_finished(
            execution_id, status=status, finished_at=datetime.now(UTC)
        )
        execution = await executions.get(execution_id)
        if execution is None:
            return
        if await notifications.exists_for_session(
            execution_id, NotificationType.execution_completed
        ):
            return
        count = len(run_tasks)
        await notifications.create(
            NotificationCreate(
                user_id=execution.created_by,
                type=NotificationType.execution_completed,
                title="Workflow execution completed",
                body=(
                    f"All {count} task{'s' if count != 1 else ''} "
                    "in this workflow execution have finished."
                ),
                workflow_execution_id=execution_id,
            ),
            user_id=execution.created_by,
        )
    except Exception:
        logger.exception(
            "failed to evaluate completion for workflow execution %s", execution_id
        )
