"""ImpersonationEvent repository: Protocol interface and SQLModel-backed implementation."""

from datetime import UTC, datetime
from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.impersonation_event import ImpersonationEvent


class ImpersonationEventRepository(Protocol):
    """Interface for impersonation audit-trail persistence operations."""

    async def create(
        self, *, impersonator_id: str, target_user_id: str
    ) -> ImpersonationEvent: ...

    async def get_open(
        self, *, impersonator_id: str, target_user_id: str
    ) -> ImpersonationEvent | None: ...

    async def close_open_for_actor(
        self, impersonator_id: str
    ) -> ImpersonationEvent | None: ...


class SqlImpersonationEventRepository:
    """SQLModel-backed implementation of :class:`ImpersonationEventRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: The request-scoped async database session.
        """
        self._db = session

    async def create(
        self, *, impersonator_id: str, target_user_id: str
    ) -> ImpersonationEvent:
        """Insert a new open impersonation event.

        Args:
            impersonator_id: The real, session-authenticated actor's id.
            target_user_id: The id of the user being impersonated.

        Returns:
            The persisted, still-open ``ImpersonationEvent``.
        """
        event = ImpersonationEvent(
            impersonator_id=impersonator_id, target_user_id=target_user_id
        )
        self._db.add(event)
        await self._db.commit()
        await self._db.refresh(event)
        return event

    async def get_open(
        self, *, impersonator_id: str, target_user_id: str
    ) -> ImpersonationEvent | None:
        """Return the open event for this exact actor/target pair, if any.

        Args:
            impersonator_id: The real, session-authenticated actor's id.
            target_user_id: The id of the user being impersonated.

        Returns:
            The matching open ``ImpersonationEvent``, or ``None``.
        """
        stmt = select(ImpersonationEvent).where(
            col(ImpersonationEvent.impersonator_id) == impersonator_id,
            col(ImpersonationEvent.target_user_id) == target_user_id,
            col(ImpersonationEvent.ended_at).is_(None),
        )
        return (await self._db.exec(stmt)).first()

    async def close_open_for_actor(
        self, impersonator_id: str
    ) -> ImpersonationEvent | None:
        """Close the most recent open event for this actor, if any.

        Args:
            impersonator_id: The real, session-authenticated actor's id.

        Returns:
            The closed ``ImpersonationEvent``, or ``None`` if none was open.
        """
        stmt = (
            select(ImpersonationEvent)
            .where(
                col(ImpersonationEvent.impersonator_id) == impersonator_id,
                col(ImpersonationEvent.ended_at).is_(None),
            )
            .order_by(col(ImpersonationEvent.started_at).desc())
        )
        event = (await self._db.exec(stmt)).first()
        if event is None:
            return None
        event.ended_at = datetime.now(UTC)
        self._db.add(event)
        await self._db.commit()
        await self._db.refresh(event)
        return event
