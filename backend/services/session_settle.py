"""Recording where a finished turn left its session, and what follows from it.

After every server-driven turn (:mod:`services.session_runner`), the session's
row is brought up to date from the turn's events: what it now waits on --
an approval, a form, its initiator, or a time its agent chose with
``wait_until`` -- and
whether it is idle, finished, or failed. Three follow-ups can come out of that:

* An approval it waits on may already be decided -- from the approvals list,
  while the turn that requested it was still running. The decision is queued
  at once.
* A branch session with nothing left to do finishes, with its last reply as
  its summary, and the scheduler runs: a join it was feeding may now be ready.
* A session handed new tasks while its turn was running may have ended the
  turn without noticing them. It gets one note naming them -- never in reply
  to such a note, so it cannot loop.
"""

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from ag_ui.core import (
    BaseEvent,
    TextMessageContentEvent,
    TextMessageStartEvent,
)

from infrastructure.client_tools import RENDER_A2UI_TOOL_NAME, RENDER_APPROVAL_TOOL_NAME
from models.approval import ApprovalStatus
from models.execution_session import ExecutionSessionStatus
from models.workflow_task import WorkflowTaskStatus
from repositories.approval import ApprovalRepository
from repositories.execution_session import ExecutionSessionRepository
from repositories.workflow_execution import WorkflowExecutionRepository
from repositories.workflow_task import WorkflowTaskRepository
from services.execution_branching import assign_runnable_tasks
from services.session_inputs import SessionInput, WaitingCall, waiting_on_from_events
from services.session_queue import decision_input, queue_input

#: Most tasks read when settling a turn; mirrors the scheduler's scan.
_MAX_TASKS = 1000

_UNFINISHED = (WorkflowTaskStatus.pending, WorkflowTaskStatus.in_progress)


async def settle_turn(
    *,
    sessions: ExecutionSessionRepository,
    approvals: ApprovalRepository,
    executions: WorkflowExecutionRepository,
    tasks: WorkflowTaskRepository,
    session_id: str,
    execution_id: str,
    previous: Sequence[WaitingCall],
    answered: Iterable[str],
    events: Sequence[BaseEvent],
    failed: bool,
    turn_started: datetime,
    input_kind: str,
    user_id: str,
) -> None:
    """Record where a finished turn left its session, and act on it.

    The session now waits on what it waited on before minus what this turn
    answered, plus the client-tool calls this turn left open. It is waiting for
    an approval if any of those is ``render_approval``, for input if one is
    ``render_a2ui``. Otherwise it is ``waiting_for_initiator`` when its agent
    tried to start a task held back for the run's initiator (the row's
    ``initiator_task_id``), and ``scheduled`` when its agent called
    ``wait_until`` during the turn (the row's ``resume_at``). Otherwise a
    branch session with no unfinished task is
    ``done``, the main session is ``done`` once the run has finished, and
    either is ``idle`` until then. A failed turn leaves it in ``error``.

    Args:
        sessions: Repository holding the session.
        approvals: Repository used to see whether a waited-on approval is
            already decided.
        executions: Repository used to see whether the run has finished.
        tasks: Repository used to read the run's tasks.
        session_id: The session the turn ran in.
        execution_id: The run it belongs to.
        previous: What the session waited on before the turn.
        answered: The tool-call ids the turn's input answered.
        events: The AG-UI events the turn produced.
        failed: Whether the turn ended in an error.
        turn_started: When the turn began; tasks assigned since then are the
            ones the session may not have seen.
        input_kind: The ``SessionInput.kind`` the turn ran on.
        user_id: Recorded on the session's audit fields.
    """
    answered_ids = set(answered)
    waiting = [call for call in previous if call.tool_call_id not in answered_ids]
    waiting += waiting_on_from_events(events)
    names = {call.name for call in waiting}
    row = await sessions.get(session_id)
    execution = await executions.get(execution_id)
    if row is None or execution is None:
        return
    is_branch = row.parent_id is not None
    main_session_id = execution.session_id
    finished_run = execution.finished_at is not None
    run_tasks = await tasks.list(
        limit=_MAX_TASKS, offset=0, workflow_execution_id=execution_id
    )
    unfinished = [
        t for t in run_tasks if t.session_id == session_id and t.status in _UNFINISHED
    ]

    summary: str | None = None
    if failed:
        status = ExecutionSessionStatus.error
    elif RENDER_APPROVAL_TOOL_NAME in names:
        status = ExecutionSessionStatus.waiting_for_approval
    elif RENDER_A2UI_TOOL_NAME in names:
        status = ExecutionSessionStatus.waiting_for_input
    elif row.initiator_task_id is not None:
        status = ExecutionSessionStatus.waiting_for_initiator
    elif row.resume_at is not None:
        status = ExecutionSessionStatus.scheduled
    elif is_branch and not unfinished:
        status = ExecutionSessionStatus.done
        summary = last_reply(events) or "(no summary)"
    elif not is_branch and finished_run:
        status = ExecutionSessionStatus.done
    else:
        status = ExecutionSessionStatus.idle
    await sessions.set_state(
        session_id,
        status=status,
        user_id=user_id,
        waiting_on=[call.model_dump() for call in waiting],
        clear_input=True,
        summary=summary,
    )

    if status is ExecutionSessionStatus.waiting_for_approval:
        await _resume_if_decided(sessions, approvals, session_id, waiting, user_id)
    elif status is ExecutionSessionStatus.done and is_branch:
        await assign_runnable_tasks(
            tasks=tasks,
            sessions=sessions,
            execution_id=execution_id,
            main_session_id=main_session_id,
            run_tasks=run_tasks,
            acting_user_id=user_id,
        )
    elif status is ExecutionSessionStatus.idle and input_kind != "assigned":
        missed = [
            t
            for t in unfinished
            if t.status is WorkflowTaskStatus.pending
            and _as_utc(t.updated_at) >= turn_started
        ]
        if missed:
            await queue_input(
                sessions,
                session_id,
                SessionInput(
                    kind="assigned",
                    text="New tasks were assigned to you while you were working: "
                    + ", ".join(t.title for t in missed),
                ),
                user_id=user_id,
            )


async def _resume_if_decided(
    sessions: ExecutionSessionRepository,
    approvals: ApprovalRepository,
    session_id: str,
    waiting: Sequence[WaitingCall],
    user_id: str,
) -> None:
    """Queue the decision of a waited-on approval that was decided during the turn."""
    for call in waiting:
        if call.approval_id is None:
            continue
        approval = await approvals.get(call.approval_id)
        if approval is not None and approval.status is not ApprovalStatus.pending:
            await queue_input(
                sessions,
                session_id,
                decision_input(call, approval.status, approval.decided_by),
                user_id=user_id,
            )
            return


def _as_utc(moment: datetime) -> datetime:
    """Return ``moment`` as an aware UTC time; SQLite hands timestamps back naive."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def last_reply(events: Iterable[BaseEvent]) -> str | None:
    """Return the text of the last assistant message a turn streamed, if any."""
    texts: dict[str, str] = {}
    last: str | None = None
    for event in events:
        if isinstance(event, TextMessageStartEvent):
            texts[event.message_id] = ""
            last = event.message_id
        elif isinstance(event, TextMessageContentEvent):
            texts[event.message_id] = texts.get(event.message_id, "") + event.delta
            last = event.message_id
    text = texts.get(last, "").strip() if last else ""
    return text or None
