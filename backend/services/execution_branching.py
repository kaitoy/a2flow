"""Server-side assignment of a run's tasks to the ADK sessions that work them.

A task is worked by exactly one session of its run, recorded as
:attr:`models.workflow_task.WorkflowTask.session_id`. The model never picks:
this module assigns every task the moment it becomes runnable -- ``pending``,
unassigned, and with every dependency ``completed`` -- and a session only ever
advances tasks assigned to it (``update_workflow_task`` refuses the rest).

Where a runnable task goes is decided by who worked its dependencies:

======================================================  ===================
Dependencies worked by                                  Target session
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

**Forking.** When the target already has unfinished work -- the graph has
branched -- the task goes to a new *branch session* forked from the target
instead, so the branches run side by side; :mod:`infrastructure.session_fork`
gives it a copy of the target's context on its first turn. A join never forks:
it is where branches meet. Once a run has ``max_sessions`` live sessions, the
task queues on its target instead, and the run carries on serially there.

**Waking.** A new branch session is queued with its task right away. An existing
target that is ``idle`` -- between turns, not waiting on anyone -- is queued
with a note naming its new work. A target that is mid-turn or waiting on a
person is left alone: it finds the task when it next looks, and a turn that
ends without having seen work assigned during it is nudged then
(:func:`services.session_settle.settle_turn`). What finished branches reported
reaches the main session as context on every one of its turns.

It runs after every task write (from
:func:`services.workflow_execution_completion.evaluate_completion`), once when a
run is created, and whenever a branch session finishes.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from config import get_settings
from models.execution_session import ExecutionSession, ExecutionSessionStatus
from models.workflow_task import WorkflowTaskRead, WorkflowTaskStatus
from repositories.execution_session import ExecutionSessionRepository
from repositories.workflow_task import WorkflowTaskRepository
from services.session_inputs import SessionInput
from services.session_queue import queue_input

_UNFINISHED = (WorkflowTaskStatus.pending, WorkflowTaskStatus.in_progress)


@dataclass(frozen=True)
class Assignment:
    """One runnable task and where it goes.

    Attributes:
        task_id: The task.
        session_id: The existing session to assign it to, or ``None`` for a
            new branch session.
        fork_from: For a new branch, the session it is forked from.
    """

    task_id: str
    session_id: str | None
    fork_from: str | None = None


def plan_assignments(
    tasks: Sequence[WorkflowTaskRead],
    sessions: Sequence[ExecutionSession],
    *,
    main_session_id: str,
    max_sessions: int,
) -> list[Assignment]:
    """Decide where each currently runnable task goes.

    Pure: it reads the run as given and writes nothing, so the rules in the
    module docstring can be tested without a database.

    Args:
        tasks: Every task of the run, in creation order.
        sessions: Every session of the run.
        main_session_id: Id of the run's main session.
        max_sessions: Most sessions the run may have alive at once.

    Returns:
        One assignment per runnable task, in creation order. A join whose
        branch sessions have not all finished is left out until they have.
    """
    by_id = {task.id: task for task in tasks}
    finished = {s.id for s in sessions if s.status == ExecutionSessionStatus.done}
    alive = len({main_session_id} | {s.id for s in sessions} - finished)
    busy = {
        t.session_id or main_session_id
        for t in tasks
        if t.session_id is not None and t.status in _UNFINISHED
    }
    assignments: list[Assignment] = []
    for task in tasks:
        if task.status != WorkflowTaskStatus.pending or task.session_id is not None:
            continue
        deps = [by_id.get(dep_id) for dep_id in task.depends_on_ids]
        if any(d is None or d.status != WorkflowTaskStatus.completed for d in deps):
            continue
        owners = {d.session_id or main_session_id for d in deps if d is not None}
        branches = owners - {main_session_id}
        join = len(owners) > 1
        if join:
            # It waits for every branch feeding it to finish, so the main
            # session picks it up with all of their work in place.
            if branches - finished:
                continue
            target = main_session_id
        elif branches:
            (branch,) = branches
            target = main_session_id if branch in finished else branch
        else:
            target = main_session_id
        if target in busy and not join and alive < max_sessions:
            assignments.append(Assignment(task.id, None, fork_from=target))
            alive += 1
        else:
            assignments.append(Assignment(task.id, target))
            busy.add(target)
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
    """Assign every runnable task of a run, forking and waking sessions as needed.

    Creates the main-session row first if the run has none yet. Each
    assignment is a compare-and-set claim, so two writers scheduling the same
    run at once cannot assign a task twice; a branch whose claim loses is
    removed again before anything ran in it.

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
    # Read before the claims below commit: a commit expires these rows, and
    # reloading one afterwards would need a lazy load outside the greenlet.
    statuses = {s.id: s.status for s in run_sessions}
    plan = plan_assignments(
        run_tasks,
        run_sessions,
        main_session_id=main_session_id,
        max_sessions=get_settings().execution_max_parallel_sessions,
    )
    by_task = {task.id: task for task in run_tasks}
    claimed_to: dict[str, list[WorkflowTaskRead]] = {}
    claimed = 0
    for assignment in plan:
        task = by_task[assignment.task_id]
        if assignment.session_id is None:
            branch_id = (
                await sessions.create_branch(
                    execution_id=execution_id,
                    parent_id=assignment.fork_from or main_session_id,
                    user_id=acting_user_id,
                )
            ).id
            if not await tasks.claim(task.id, branch_id, user_id=acting_user_id):
                await sessions.delete(branch_id)
                continue
            await queue_input(
                sessions,
                branch_id,
                SessionInput(kind="assigned", text=_branch_brief(task)),
                user_id=acting_user_id,
            )
        elif await tasks.claim(task.id, assignment.session_id, user_id=acting_user_id):
            claimed_to.setdefault(assignment.session_id, []).append(task)
        else:
            continue
        claimed += 1
    await _wake_idle_targets(sessions, statuses, claimed_to, acting_user_id)
    return claimed


async def _wake_idle_targets(
    sessions: ExecutionSessionRepository,
    statuses: dict[str, ExecutionSessionStatus],
    claimed_to: dict[str, list[WorkflowTaskRead]],
    acting_user_id: str,
) -> None:
    """Queue a note on every idle session that was just handed work.

    What finished branches reported is not repeated here: every main-session
    turn carries it as context (:mod:`services.session_runner`), so it reaches
    the agent even when the main session was busy when its join was assigned.
    """
    for session_id, assigned in claimed_to.items():
        if statuses.get(session_id) is not ExecutionSessionStatus.idle:
            continue
        await queue_input(
            sessions,
            session_id,
            SessionInput(
                kind="assigned",
                text="New tasks were assigned to you: "
                + ", ".join(t.title for t in assigned),
            ),
            user_id=acting_user_id,
        )


def _branch_brief(task: WorkflowTaskRead) -> str:
    """The first message of a branch session: the task it was forked for."""
    return (
        f"Your assigned task is: {task.title}. This session was forked to work "
        "one branch of the workflow while other sessions work the rest in "
        "parallel. Work only the tasks list_workflow_tasks marks "
        "assigned_to_you, then summarize what you did and stop."
    )
