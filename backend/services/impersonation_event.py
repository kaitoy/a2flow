"""Use case service for the impersonation audit trail: List and Get.

Rows are written by :class:`services.impersonation.ImpersonationService` as a
session starts and ends -- see :mod:`models.impersonation_event`. This service is
the read half only, and is deliberately separate from that one: the live control
flow decides *whether an actor may impersonate someone right now*, while this
answers *who impersonated whom, and when*. Keeping them apart means the audit
surface carries none of the live flow's collaborators, and no route can reach a
mutation through it.
"""

from collections.abc import Sequence

from models.impersonation_event import ImpersonationEventRead
from repositories.exceptions import NotFoundError
from repositories.impersonation_event import ImpersonationEventRepository
from repositories.query import FilterSpec, SortSpec


class ImpersonationEventService:
    """Application service orchestrating impersonation audit-trail reads."""

    def __init__(self, repo: ImpersonationEventRepository) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing impersonation-event persistence, already
                scoped to the acting tenant (or to every tenant for a
                platform-scoped caller browsing with the all-tenants selection).
        """
        self._repo = repo

    async def get(self, event_id: str) -> ImpersonationEventRead:
        """Return the recorded impersonation session with the given ID.

        Args:
            event_id: The event's primary key.

        Returns:
            The recorded session.

        Raises:
            NotFoundError: If no event exists with that ID within the acting
                tenant's scope.
        """
        event = await self._repo.get(event_id)
        if event is None:
            raise NotFoundError("ImpersonationEvent", event_id)
        return event

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[ImpersonationEventRead]:
        """Return a page of recorded impersonation sessions.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of records.
        """
        return await self._repo.list(
            limit=limit, offset=offset, sort=sort, filters=filters
        )
