"""DesignSession repository: Protocol interface and SQLModel-backed implementation."""

from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.design_session import DesignSession, DesignSessionCreate
from repositories._integrity import commit_or_translate_user_fk
from repositories.exceptions import NotFoundError


class DesignSessionRepository(Protocol):
    """Interface for DesignSession persistence operations."""

    async def get(self, ds_id: str) -> DesignSession | None: ...

    async def get_by_session_id(self, session_id: str) -> DesignSession | None: ...

    async def get_by_workflow_id(self, workflow_id: str) -> DesignSession | None: ...

    async def create(
        self, data: DesignSessionCreate, *, user_id: str
    ) -> DesignSession: ...

    async def commit_shas_for_skill(self, agent_skill_id: str) -> set[str]: ...

    async def delete(self, ds_id: str) -> None: ...


class SqlDesignSessionRepository:
    """SQLModel-backed implementation of DesignSessionRepository."""

    def __init__(self, session: AsyncSession, *, tenant_id: str) -> None:
        """Store the SQLModel async session and the tenant these queries are scoped to."""
        self._db = session
        self._tenant_id = tenant_id

    async def _get_scoped(self, ds_id: str) -> DesignSession | None:
        """Return the DesignSession with the given ID within the current tenant, or ``None``."""
        stmt = select(DesignSession).where(
            DesignSession.id == ds_id, DesignSession.tenant_id == self._tenant_id
        )
        result = await self._db.exec(stmt)
        return result.first()

    async def get(self, ds_id: str) -> DesignSession | None:
        """Return the DesignSession with the given ID, or ``None`` if missing."""
        return await self._get_scoped(ds_id)

    async def get_by_session_id(self, session_id: str) -> DesignSession | None:
        """Return the DesignSession for the given ADK session id, or ``None``.

        The ADK session id (the AG-UI thread id) is stored on
        :attr:`DesignSession.session_id`, which is distinct from the primary
        key. The design agent tools use this lookup to map the session they
        are running in back to the workflow whose templates they edit.

        Args:
            session_id: The ADK session id to look up.

        Returns:
            The matching DesignSession, or ``None`` if no session has that id.
        """
        stmt = (
            select(DesignSession)
            .where(
                col(DesignSession.session_id) == session_id,
                DesignSession.tenant_id == self._tenant_id,
            )
            .limit(1)
        )
        result = await self._db.exec(stmt)
        return result.first()

    async def get_by_workflow_id(self, workflow_id: str) -> DesignSession | None:
        """Return the DesignSession of the given workflow, or ``None``.

        A workflow has at most one design session
        (``uq_design_sessions_workflow_id``), created together with the
        workflow by the generation flow.

        Args:
            workflow_id: Identifier of the workflow whose session to fetch.

        Returns:
            The workflow's DesignSession, or ``None`` if it has none.
        """
        stmt = (
            select(DesignSession)
            .where(
                col(DesignSession.workflow_id) == workflow_id,
                DesignSession.tenant_id == self._tenant_id,
            )
            .limit(1)
        )
        result = await self._db.exec(stmt)
        return result.first()

    async def create(self, data: DesignSessionCreate, *, user_id: str) -> DesignSession:
        """Persist a new DesignSession with audit fields populated."""
        ds = DesignSession.model_validate(
            {
                **data.model_dump(),
                "tenant_id": self._tenant_id,
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        self._db.add(ds)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(ds)
        return ds

    async def commit_shas_for_skill(self, agent_skill_id: str) -> set[str]:
        """Return every skill revision that design sessions of this skill pin.

        These are revisions a prune of the skill store must keep alongside the
        ones pinned by workflow executions: each is the code some design
        conversation started against and will keep loading on its next run.

        Args:
            agent_skill_id: Identifier of the skill whose sessions to scan.

        Returns:
            The set of pinned commit shas.
        """
        stmt = select(DesignSession.agent_skill_commit_sha).where(
            col(DesignSession.agent_skill_id) == agent_skill_id,
            DesignSession.tenant_id == self._tenant_id,
        )
        result = await self._db.exec(stmt)
        return set(result.all())

    async def delete(self, ds_id: str) -> None:
        """Delete the DesignSession with the given ID, raising NotFoundError if missing."""
        ds = await self._get_scoped(ds_id)
        if ds is None:
            raise NotFoundError("DesignSession", ds_id)
        await self._db.delete(ds)
        await self._db.commit()
