"""Handing a session its next input, and recording where a turn left it.

Both halves are shared by every path that touches a session's lifecycle: the
session runner (:mod:`services.session_runner`) runs queued turns, a browser
still drives turns through the agent route, and deciding an approval
(:meth:`services.approval.ApprovalService.resolve`) queues the turn that
resumes the run. Kept free of the agent machinery so any of them can import it.
"""

import asyncio
import contextlib
import logging
from collections.abc import Iterable, Sequence

from ag_ui.core import BaseEvent

from infrastructure.client_tools import RENDER_A2UI_TOOL_NAME, RENDER_APPROVAL_TOOL_NAME
from models.approval import ApprovalStatus
from models.execution_session import ExecutionSessionStatus
from repositories.approval import ApprovalRepository
from repositories.execution_session import ExecutionSessionRepository
from repositories.workflow_execution import WorkflowExecutionRepository
from services.session_inputs import SessionInput, WaitingCall, waiting_on_from_events

logger = logging.getLogger(__name__)

#: Set whenever this process queues input, so its runner starts the turn at
#: once instead of on its next poll. ponytail: in-process only -- input queued
#: on another replica waits for that runner's poll (a couple of seconds); a
#: ``NOTIFY`` channel would close the gap if it ever matters.
_wake = asyncio.Event()


def wake_runner() -> None:
    """Tell this process's session runner there is input to run."""
    _wake.set()


async def wait_for_wake(timeout: float) -> None:
    """Block until :func:`wake_runner` is called or ``timeout`` seconds pass."""
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(_wake.wait(), timeout)
    _wake.clear()


async def queue_input(
    sessions: ExecutionSessionRepository,
    session_id: str,
    session_input: SessionInput,
    *,
    user_id: str,
) -> bool:
    """Queue ``session_input`` on a session and wake the runner.

    Args:
        sessions: Repository holding the session.
        session_id: The session to hand the input to.
        session_input: The input its next turn runs on.
        user_id: Recorded on the session's ``updated_by``.

    Returns:
        ``True`` when the input was queued; ``False`` when the session was
        already busy or finished and kept what it had.
    """
    queued = await sessions.queue_input(
        session_id, session_input.model_dump(), user_id=user_id
    )
    if queued:
        wake_runner()
    return queued


def decision_input(
    call: WaitingCall, status: ApprovalStatus, decided_by: str | None
) -> SessionInput:
    """Build the input that answers a paused ``render_approval`` call with its decision.

    The content is the decision itself (``approved``, ``rejected``,
    ``returned``) -- what the browser's approval controls used to send -- and
    it is attributed to whoever decided, so the chat shows who approved.
    """
    return SessionInput(
        kind="tool_result",
        tool_call_id=call.tool_call_id,
        content=status.value,
        sender_id=decided_by,
    )


async def settle_turn(
    *,
    sessions: ExecutionSessionRepository,
    approvals: ApprovalRepository,
    executions: WorkflowExecutionRepository,
    session_id: str,
    execution_id: str,
    previous: Sequence[WaitingCall],
    answered: Iterable[str],
    events: Iterable[BaseEvent],
    failed: bool,
    user_id: str,
) -> None:
    """Record where a finished turn left its session, and queue any resume already due.

    The session now waits on what it waited on before minus what this turn
    answered, plus the client-tool calls this turn left open. It is waiting
    for an approval if any of those is ``render_approval``, for input if one
    is ``render_a2ui``, and otherwise idle -- or done, once the run has
    finished. A failed turn leaves it in ``error``.

    An approval can be decided before its controls are ever shown -- from the
    approvals list, while the turn that requested it is still running. Nothing
    was waiting on it then, so the decision queued nothing; it is picked up
    here instead.

    Args:
        sessions: Repository holding the session.
        approvals: Repository used to see whether a waited-on approval is
            already decided.
        executions: Repository used to see whether the run has finished.
        session_id: The session the turn ran in.
        execution_id: The run it belongs to.
        previous: What the session waited on before the turn.
        answered: The tool-call ids the turn's input answered.
        events: The AG-UI events the turn produced.
        failed: Whether the turn ended in an error.
        user_id: Recorded on the session's ``updated_by``.
    """
    answered_ids = set(answered)
    waiting = [call for call in previous if call.tool_call_id not in answered_ids]
    waiting += waiting_on_from_events(events)
    names = {call.name for call in waiting}
    if failed:
        status = ExecutionSessionStatus.error
    elif RENDER_APPROVAL_TOOL_NAME in names:
        status = ExecutionSessionStatus.waiting_for_approval
    elif RENDER_A2UI_TOOL_NAME in names:
        status = ExecutionSessionStatus.waiting_for_input
    else:
        execution = await executions.get(execution_id)
        finished = execution is not None and execution.finished_at is not None
        status = (
            ExecutionSessionStatus.done if finished else ExecutionSessionStatus.idle
        )
    await sessions.set_state(
        session_id,
        status=status,
        user_id=user_id,
        waiting_on=[call.model_dump() for call in waiting],
        clear_input=True,
    )
    if status is not ExecutionSessionStatus.waiting_for_approval:
        return
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
