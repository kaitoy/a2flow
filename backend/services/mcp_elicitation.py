"""Use case service for the questions MCP servers ask during a workflow run.

The waiting side lives in :mod:`infrastructure.mcp_elicitation`; this is the
answering side, behind two routes: reading a question (so the chat can show its
state after a reload) and answering it.

Who may do what mirrors the forms an agent renders in the same chat: anyone who
may read the run may read its questions, but only the run's initiator may answer
one -- the person the run acts for, with no super-admin bypass.
"""

from collections.abc import Collection
from datetime import UTC, datetime

import jsonschema

from models.mcp_elicitation import (
    MCPElicitation,
    MCPElicitationAnswer,
    MCPElicitationStatus,
)
from models.user import User
from repositories.exceptions import (
    ElicitationAlreadyAnsweredError,
    ForbiddenError,
    NotFoundError,
    SessionInputValidationError,
)
from repositories.mcp_elicitation import MCPElicitationRepository
from repositories.workflow_execution import WorkflowExecutionRepository
from services.workflow_execution_access import WorkflowExecutionAccessPolicy

#: Status a question moves to for each answer.
_STATUS_FOR_ACTION = {
    "accept": MCPElicitationStatus.accepted,
    "decline": MCPElicitationStatus.declined,
    "cancel": MCPElicitationStatus.cancelled,
}


class MCPElicitationService:
    """Reads and answers the questions servers asked in a run's sessions."""

    def __init__(
        self,
        elicitations: MCPElicitationRepository,
        executions: WorkflowExecutionRepository,
        access: WorkflowExecutionAccessPolicy,
    ) -> None:
        """Initialize the service.

        Args:
            elicitations: The questions.
            executions: Runs, restricted to those the caller's access-control
                tags admit -- fetched first, so a hidden run's questions are 404.
            access: The run's participant rules.
        """
        self._elicitations = elicitations
        self._executions = executions
        self._access = access

    async def get(
        self,
        execution_id: str,
        session_id: str,
        elicitation_id: str,
        *,
        caller: User,
        caller_roles: Collection[str],
    ) -> MCPElicitation:
        """Return one question, for anyone who may read the run.

        Args:
            execution_id: Identifier of the run.
            session_id: The session the question was asked in.
            elicitation_id: Identifier of the question.
            caller: The authenticated user.
            caller_roles: The caller's effective roles.

        Returns:
            The question.

        Raises:
            NotFoundError: If the run or the question does not exist, or the
                run is hidden from the caller.
            ForbiddenError: If the caller may not read the run.
        """
        execution = await self._executions.get(execution_id)
        if execution is None:
            raise NotFoundError("WorkflowExecution", execution_id)
        await self._access.assert_read_access(
            execution_id, execution.initiator_id, caller, caller_roles
        )
        return await self._question(execution_id, session_id, elicitation_id)

    async def answer(
        self,
        execution_id: str,
        session_id: str,
        elicitation_id: str,
        data: MCPElicitationAnswer,
        *,
        caller: User,
    ) -> MCPElicitation:
        """Record the initiator's answer; the waiting tool call picks it up.

        Args:
            execution_id: Identifier of the run.
            session_id: The session the question was asked in.
            elicitation_id: Identifier of the question.
            data: The answer.
            caller: The authenticated user answering.

        Returns:
            The question, now closed.

        Raises:
            NotFoundError: If the run or the question does not exist, or the
                run is hidden from the caller.
            ForbiddenError: If the caller may not act on the run, or is not
                its initiator.
            SessionInputValidationError: If an ``accept`` carries values that do
                not satisfy the question's schema.
            ElicitationAlreadyAnsweredError: If the question was already
                answered or has expired.
        """
        execution = await self._executions.get(execution_id)
        if execution is None:
            raise NotFoundError("WorkflowExecution", execution_id)
        await self._access.assert_access(execution_id, execution.initiator_id, caller)
        if caller.id != execution.initiator_id:
            raise ForbiddenError("only the run's initiator can answer its questions")
        question = await self._question(execution_id, session_id, elicitation_id)
        content = None
        if data.action == "accept":
            content = data.content or {}
            try:
                jsonschema.validate(content, question.requested_schema)
            except jsonschema.ValidationError as exc:
                raise SessionInputValidationError(
                    f"the answer does not fit the question: {exc.message}"
                ) from exc
            except jsonschema.SchemaError as exc:
                raise SessionInputValidationError(
                    "the question's form cannot be checked"
                ) from exc
        answered = await self._elicitations.answer(
            elicitation_id,
            status=_STATUS_FOR_ACTION[data.action],
            content=content,
            user_id=caller.id,
            now=datetime.now(UTC),
        )
        closed = await self._question(execution_id, session_id, elicitation_id)
        if not answered:
            status = (
                MCPElicitationStatus.expired
                if closed.status is MCPElicitationStatus.pending
                else closed.status
            )
            raise ElicitationAlreadyAnsweredError(elicitation_id, status.value)
        return closed

    async def _question(
        self, execution_id: str, session_id: str, elicitation_id: str
    ) -> MCPElicitation:
        """Return a question of the session, or raise NotFoundError.

        Args:
            execution_id: Identifier of the run.
            session_id: The session the question was asked in.
            elicitation_id: Identifier of the question.

        Returns:
            The question.

        Raises:
            NotFoundError: If the session has no such question.
        """
        question = await self._elicitations.get_for_session(
            execution_id, session_id, elicitation_id
        )
        if question is None:
            raise NotFoundError("MCPElicitation", elicitation_id)
        return question
