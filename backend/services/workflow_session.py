"""Use case service for WorkflowSession resources.

Exposes WorkflowSession reads, the parent-checked task listing, and resolution
of the ADK agent bound to a session. HTTP concerns (SSE encoding, streaming,
message filtering) remain in the router; this service only owns the data access
and agent-resolution business rules.
"""

import builtins
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ag_ui_adk import ADKAgent, adk_events_to_messages
from google.adk.sessions import BaseSessionService

from infrastructure.agent import AgentRegistry
from models.workflow_session import WorkflowSession
from models.workflow_task import WorkflowTaskRead
from repositories import WorkflowSessionRepository, WorkflowTaskRepository
from repositories.exceptions import NotFoundError
from repositories.query import FilterSpec, SortSpec


class WorkflowSessionService:
    """Application service orchestrating WorkflowSession operations."""

    def __init__(
        self,
        ws_repo: WorkflowSessionRepository,
        tasks: WorkflowTaskRepository,
        registry: AgentRegistry,
        session_service: BaseSessionService,
        app_name: str,
    ) -> None:
        """Initialize the service.

        Args:
            ws_repo: Repository providing WorkflowSession persistence.
            tasks: Repository providing WorkflowTask persistence.
            registry: Registry resolving ADK agents per skill.
            session_service: ADK session store, used to delete the underlying
                chat session when a WorkflowSession is removed.
            app_name: ADK application name keying sessions in the store.
        """
        self._ws_repo = ws_repo
        self._tasks = tasks
        self._registry = registry
        self._session_service = session_service
        self._app_name = app_name

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

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> builtins.list[WorkflowSession]:
        """Return a page of WorkflowSession records.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of sessions, newest first by default.
        """
        return await self._ws_repo.list(
            limit=limit, offset=offset, sort=sort, filters=filters
        )

    async def list_tasks(
        self,
        ws_id: str,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> builtins.list[WorkflowTaskRead]:
        """Return the WorkflowTasks belonging to a session.

        Args:
            ws_id: Identifier of the parent session.
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of tasks for the session.

        Raises:
            NotFoundError: If the parent session does not exist, so callers can
                distinguish "no such session" from "session has no tasks".
        """
        await self.get(ws_id)
        return await self._tasks.list(
            limit=limit,
            offset=offset,
            workflow_session_id=ws_id,
            sort=sort,
            filters=filters,
        )

    async def resolve_agent(self, ws_id: str) -> tuple[ADKAgent, WorkflowSession]:
        """Resolve the ADK agent bound to a WorkflowSession and the session record.

        The skill and skill directory are read from the session record so the
        correct ADK tools are loaded regardless of global agent state. The record
        is returned alongside the agent so the caller can key the ADK run by the
        session's owner (``WorkflowSession.user_id``) rather than the current user,
        letting every viewer (for example a designated approver) share the same
        ADK session.

        Args:
            ws_id: Identifier of the session whose agent to resolve.

        Returns:
            A ``(agent, workflow_session)`` tuple: the ADK agent configured for
            the session's skill, and the WorkflowSession record itself.

        Raises:
            NotFoundError: If no session exists with the given ID.
        """
        ws = await self.get(ws_id)
        skill_dir = Path(ws.skill_dir)
        return self._registry.get(ws.agent_skill_id, skill_dir), ws

    async def get_messages(self, ws_id: str) -> builtins.list[dict[str, Any]]:
        """Return the chat history of a WorkflowSession's ADK session.

        The ADK session is looked up by the WorkflowSession's owner
        (``ws.user_id``), so the same history is returned regardless of which user
        requests it — a designated approver opening the chat sees the owner's
        conversation instead of starting a fresh session. Returns an empty list
        when the ADK session does not exist yet (before the first agent run).

        Args:
            ws_id: Identifier of the WorkflowSession whose messages to fetch.

        Returns:
            The session's messages as plain JSON-serializable dicts (the same
            shape as ``GET /sessions/{id}/messages``).

        Raises:
            NotFoundError: If no WorkflowSession exists with the given ID.
        """
        ws = await self.get(ws_id)
        session = await self._session_service.get_session(
            app_name=self._app_name,
            user_id=ws.user_id,
            session_id=ws.session_id,
        )
        if session is None:
            return []
        messages = adk_events_to_messages(session.events)
        return [m.model_dump(mode="json", by_alias=True) for m in messages]

    async def delete(self, ws_id: str) -> None:
        """Delete a WorkflowSession and its underlying ADK chat session.

        Removes, in order: the ADK chat session keyed by the record's
        ``session_id`` (best effort — skipped if it no longer exists), then the
        WorkflowSession row itself. Deleting the row cascades to its
        WorkflowTasks (and their dependency edges and tool bindings) via the
        ``ON DELETE CASCADE`` foreign keys.

        Args:
            ws_id: Identifier of the session to delete.

        Raises:
            NotFoundError: If no WorkflowSession exists with the given ID.
        """
        ws = await self.get(ws_id)
        existing = await self._session_service.get_session(
            app_name=self._app_name,
            user_id=ws.user_id,
            session_id=ws.session_id,
        )
        if existing is not None:
            await self._session_service.delete_session(
                app_name=self._app_name,
                user_id=ws.user_id,
                session_id=ws.session_id,
            )
        await self._ws_repo.delete(ws_id)
