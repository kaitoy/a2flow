"""Use case service for WorkflowSession resources.

Exposes WorkflowSession reads, the parent-checked task listing, and resolution
of the ADK agent bound to a session. HTTP concerns (SSE encoding, streaming,
message filtering) remain in the router; this service only owns the data access
and agent-resolution business rules.
"""

import builtins
from pathlib import Path

from ag_ui_adk import ADKAgent

from infrastructure.agent import AgentRegistry
from models.workflow_session import WorkflowSession
from models.workflow_task import WorkflowTask
from repositories import WorkflowSessionRepository, WorkflowTaskRepository
from repositories.exceptions import NotFoundError


class WorkflowSessionService:
    """Application service orchestrating WorkflowSession operations."""

    def __init__(
        self,
        ws_repo: WorkflowSessionRepository,
        tasks: WorkflowTaskRepository,
        registry: AgentRegistry,
    ) -> None:
        """Initialize the service.

        Args:
            ws_repo: Repository providing WorkflowSession persistence.
            tasks: Repository providing WorkflowTask persistence.
            registry: Registry resolving ADK agents per skill.
        """
        self._ws_repo = ws_repo
        self._tasks = tasks
        self._registry = registry

    async def get(self, ws_id: str) -> WorkflowSession:
        """Return the WorkflowSession with the given ID.

        Args:
            ws_id: Identifier of the session to fetch.

        Returns:
            The matching WorkflowSession.

        Raises:
            NotFoundError: If no session exists with the given ID.
        """
        ws = await self._ws_repo.get(ws_id)
        if ws is None:
            raise NotFoundError("WorkflowSession", ws_id)
        return ws

    async def list(self, *, limit: int, offset: int) -> builtins.list[WorkflowSession]:
        """Return a page of WorkflowSession records.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.

        Returns:
            The requested page of sessions, newest first.
        """
        return await self._ws_repo.list(limit=limit, offset=offset)

    async def list_tasks(
        self, ws_id: str, *, limit: int, offset: int
    ) -> builtins.list[WorkflowTask]:
        """Return the WorkflowTasks belonging to a session.

        Args:
            ws_id: Identifier of the parent session.
            limit: Maximum number of records to return.
            offset: Number of records to skip.

        Returns:
            The requested page of tasks for the session.

        Raises:
            NotFoundError: If the parent session does not exist, so callers can
                distinguish "no such session" from "session has no tasks".
        """
        await self.get(ws_id)
        return await self._tasks.list(
            limit=limit, offset=offset, workflow_session_id=ws_id
        )

    async def resolve_agent(self, ws_id: str) -> ADKAgent:
        """Resolve the ADK agent bound to a WorkflowSession.

        The skill and skill directory are read from the session record so the
        correct ADK tools are loaded regardless of global agent state.

        Args:
            ws_id: Identifier of the session whose agent to resolve.

        Returns:
            The ADK agent configured for the session's skill.

        Raises:
            NotFoundError: If no session exists with the given ID.
        """
        ws = await self.get(ws_id)
        skill_dir = Path(ws.skill_dir)
        return self._registry.get(ws.agent_skill_id, skill_dir)
