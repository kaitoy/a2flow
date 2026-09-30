"""Use case service for a workflow execution's ADK sessions.

Keeps a session's server-side record in step with the turns a browser still
drives through the agent route: which client-tool calls the turn left open,
and so what an approval decision -- made anywhere -- has to resume.
"""

from collections.abc import Iterable, Sequence

from ag_ui.core import BaseEvent, Message, ToolMessage

from repositories.approval import ApprovalRepository
from repositories.execution_session import ExecutionSessionRepository
from repositories.workflow_execution import WorkflowExecutionRepository
from services.session_inputs import WaitingCall
from services.session_queue import settle_turn


class ExecutionSessionService:
    """Application service over a run's ADK sessions."""

    def __init__(
        self,
        sessions: ExecutionSessionRepository,
        approvals: ApprovalRepository,
        executions: WorkflowExecutionRepository,
    ) -> None:
        """Initialize the service.

        Args:
            sessions: Repository holding the run's ADK sessions.
            approvals: Repository used to see whether a waited-on approval has
                already been decided.
            executions: Repository used to see whether the run has finished.
        """
        self._sessions = sessions
        self._approvals = approvals
        self._executions = executions

    async def waiting_on(self, session_id: str) -> list[WaitingCall]:
        """Return the client-tool calls a session is paused on, before a turn.

        Args:
            session_id: The ADK session about to run a turn.

        Returns:
            The calls its last turn left open; empty for an unknown session.
        """
        row = await self._sessions.get(session_id)
        return [WaitingCall.model_validate(c) for c in row.waiting_on] if row else []

    async def settle_browser_turn(
        self,
        *,
        session_id: str,
        execution_id: str,
        previous: Sequence[WaitingCall],
        messages: Iterable[Message],
        events: Iterable[BaseEvent],
        failed: bool,
        user_id: str,
    ) -> None:
        """Record where a browser-driven turn left its session.

        The turn answered whichever paused calls its ``tool`` messages name;
        everything else follows :func:`services.session_queue.settle_turn`,
        including resuming right away when the approval the turn now waits on
        was decided while it ran.

        Args:
            session_id: The ADK session the turn ran in.
            execution_id: The run it belongs to.
            previous: What the session waited on before the turn.
            messages: The messages the browser sent.
            events: The AG-UI events the turn produced.
            failed: Whether the turn ended in an error or was cut short.
            user_id: The user who drove the turn.
        """
        if await self._sessions.get(session_id) is None:
            return
        await settle_turn(
            sessions=self._sessions,
            approvals=self._approvals,
            executions=self._executions,
            session_id=session_id,
            execution_id=execution_id,
            previous=previous,
            answered=[m.tool_call_id for m in messages if isinstance(m, ToolMessage)],
            events=events,
            failed=failed,
            user_id=user_id,
        )
