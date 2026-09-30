"""Server-side assignment of a run's tasks to the ADK sessions that work them.

A task is worked by exactly one session of its run, recorded as
:attr:`models.workflow_task.WorkflowTask.session_id`. The model never picks:
this module assigns every task the moment it becomes runnable -- ``pending``,
unassigned, and with every dependency ``completed`` -- and a session only ever
advances tasks assigned to it (``update_workflow_task`` refuses the rest).

Where a runnable task goes is decided by who worked its dependencies:

======================================================  ===================
Dependencies worked by                                  Assigned to
======================================================  ===================
nobody (a root task), or only the main session          the main session
one branch session that is still alive                  that branch session
one branch session that has finished (``done``)         the main session
two or more sessions (a join)                           the main session, once
                                                        every branch session
                                                        among them is ``done``
======================================================  ===================

A dependency with no session recorded counts as the main session's: before
sessions were tracked, the main session was the only one there was, and a task
a person completed through the REST API was never claimed by any session.

It runs after every task write (from
:func:`services.workflow_execution_completion.evaluate_completion`) and once
when a run is created, so the first runnable tasks are assigned before the
agent's first turn.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from models.execution_session import ExecutionSession, ExecutionSessionStatus
from models.workflow_task import WorkflowTaskRead, WorkflowTaskStatus
from repositories.execution_session import ExecutionSessionRepository
from repositories.workflow_task import WorkflowTaskRepository


@dataclass(frozen=True)
class Assignment:
    """One runnable task and the session it should be assigned to."""

    task_id: str
    session_id: str


def plan_assignments(
    tasks: Sequence[WorkflowTaskRead],
    sessions: Sequence[ExecutionSession],
    *,
    main_session_id: str,
) -> list[Assignment]:
    """Decide which session each currently runnable task goes to.

    Pure: it reads the run as given and writes nothing, so the rules in the
    module docstring can be tested without a database.

    Args:
        tasks: Every task of the run, in creation order.
        sessions: Every session of the run.
        main_session_id: Id of the run's main session.

    Returns:
        One assignment per runnable task, in creation order. A join whose
        branch sessions have not all finished is left out until they have.
    """
    by_id = {task.id: task for task in tasks}
    finished = {s.id for s in sessions if s.status == ExecutionSessionStatus.done}
    assignments: list[Assignment] = []
    for task in tasks:
        if task.status != WorkflowTaskStatus.pending or task.session_id is not None:
            continue
        deps = [by_id.get(dep_id) for dep_id in task.depends_on_ids]
        if any(d is None or d.status != WorkflowTaskStatus.completed for d in deps):
            continue
        owners = {d.session_id or main_session_id for d in deps if d is not None}
        branches = owners - {main_session_id}
        if len(owners) > 1:
            # A join: it waits for every branch feeding it to finish, so the
            # main session picks it up with all of their work in place.
            if branches - finished:
                continue
            target = main_session_id
        elif branches:
            (branch,) = branches
            target = main_session_id if branch in finished else branch
        else:
            target = main_session_id
        assignments.append(Assignment(task.id, target))
    return assignments


async def assign_runnable_tasks(
    *,
    tasks: WorkflowTaskRepository,
    sessions: ExecutionSessionRepository,
    execution_id: str,
    main_session_id: str,
    run_tasks: Sequence[WorkflowTaskRead],
    acting_user_id: str,
) -> int:
    """Assign every runnable task of a run to its session.

    Creates the main-session row first if the run has none yet. Each
    assignment is a compare-and-set claim, so two writers scheduling the same
    run at once cannot assign a task twice.

    Args:
        tasks: Repository used to claim the tasks.
        sessions: Repository holding the run's sessions.
        execution_id: Primary key of the workflow execution.
        main_session_id: The execution's ``session_id``.
        run_tasks: The run's tasks as just read, in creation order.
        acting_user_id: Recorded on the audit fields of what this writes.

    Returns:
        How many tasks this call assigned.
    """
    await sessions.ensure_main(
        execution_id=execution_id, session_id=main_session_id, user_id=acting_user_id
    )
    run_sessions = await sessions.list_for_execution(execution_id)
    claimed = 0
    for assignment in plan_assignments(
        run_tasks, run_sessions, main_session_id=main_session_id
    ):
        if await tasks.claim(
            assignment.task_id, assignment.session_id, user_id=acting_user_id
        ):
            claimed += 1
    return claimed
