"""Handing a session its next input, and waking the runner to run it.

Shared by every path that gives a session work: creating a run (its kickoff),
deciding an approval (the turn that resumes it), a person's input, and the
scheduler handing a session new tasks. Kept free of the agent machinery, and of
the scheduler, so any of them can import it.
"""

import asyncio
import contextlib

from models.approval import ApprovalStatus
from repositories.execution_session import ExecutionSessionRepository
from services.session_inputs import SessionInput, WaitingCall

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
        already busy and kept what it had.
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
