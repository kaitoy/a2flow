"""PlanningSession repository: Protocol interface and SQLModel-backed implementation."""

from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.planning_session import PlanningSession, PlanningSessionCreate
from repositories._integrity import commit_or_translate_user_fk
from repositories.exceptions import NotFoundError


class PlanningSessionRepository(Protocol):
    """Interface for PlanningSession persistence operations."""

    async def get(self, ps_id: str) -> PlanningSession | None: ...

    async def get_by_session_id(self, session_id: str) -> PlanningSession | None: ...

    async def get_by_workflow_id(self, workflow_id: str) -> PlanningSession | None: ...

    async def create(
        self, data: PlanningSessionCreate, *, user_id: str
    ) -> PlanningSession: ...

    async def commit_shas_for_skill(self, agent_skill_id: str) -> set[str]: ...

    async def delete(self, ps_id: str) -> None: ...


class SqlPlanningSessionRepository:
    """SQLModel-backed implementation of PlanningSessionRepository."""

    def __init__(self, session: AsyncSession) -> None:
        """Store the SQLModel async session used for all queries."""
        self._db = session

    async def get(self, ps_id: str) -> PlanningSession | None:
        """Return the PlanningSession with the given ID, or ``None`` if missing."""
        return await self._db.get(PlanningSession, ps_id)

    async def get_by_session_id(self, session_id: str) -> PlanningSession | None:
        """Return the PlanningSession for the given ADK session id, or ``None``.

        The ADK session id (the AG-UI thread id) is stored on
        :attr:`PlanningSession.session_id`, which is distinct from the primary
        key. The planning agent tools use this lookup to map the session they
        are running in back to the workflow whose templates they edit.

        Args:
            session_id: The ADK session id to look up.

        Returns:
            The matching PlanningSession, or ``None`` if no session has that id.
        """
        stmt = (
            select(PlanningSession)
            .where(col(PlanningSession.session_id) == session_id)
            .limit(1)
        )
        result = await self._db.exec(stmt)
        return result.first()

    async def get_by_workflow_id(self, workflow_id: str) -> PlanningSession | None:
        """Return the PlanningSession of the given workflow, or ``None``.

        A workflow has at most one planning session
        (``uq_planning_sessions_workflow_id``), created together with the
        workflow by the generation flow.

        Args:
            workflow_id: Identifier of the workflow whose session to fetch.

        Returns:
            The workflow's PlanningSession, or ``None`` if it has none.
        """
        stmt = (
            select(PlanningSession)
            .where(col(PlanningSession.workflow_id) == workflow_id)
            .limit(1)
        )
        result = await self._db.exec(stmt)
        return result.first()

    async def create(
        self, data: PlanningSessionCreate, *, user_id: str
    ) -> PlanningSession:
        """Persist a new PlanningSession with audit fields populated."""
        ps = PlanningSession.model_validate(
            {**data.model_dump(), "created_by": user_id, "updated_by": user_id}
        )
        self._db.add(ps)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(ps)
        return ps

    async def commit_shas_for_skill(self, agent_skill_id: str) -> set[str]:
        """Return every skill revision that planning sessions of this skill pin.

        These are revisions a prune of the skill store must keep alongside the
        ones pinned by workflow sessions: each is the code some planning
        conversation started against and will keep loading on its next run.

        Args:
            agent_skill_id: Identifier of the skill whose sessions to scan.

        Returns:
            The set of pinned commit shas.
        """
        stmt = select(PlanningSession.agent_skill_commit_sha).where(
            col(PlanningSession.agent_skill_id) == agent_skill_id
        )
        result = await self._db.exec(stmt)
        return set(result.all())

    async def delete(self, ps_id: str) -> None:
        """Delete the PlanningSession with the given ID, raising NotFoundError if missing."""
        ps = await self._db.get(PlanningSession, ps_id)
        if ps is None:
            raise NotFoundError("PlanningSession", ps_id)
        await self._db.delete(ps)
        await self._db.commit()
