"""Use case service for OutboundEmail: List, Get, and status-gated Delete.

Rows are created only by :class:`services.notification_dispatch.NotificationDispatcher`
(via :meth:`repositories.outbound_email.OutboundEmailRepository.stage`, inside the
caller's own transaction) and mutated only by
:class:`repositories.outbound_email_queue.SqlOutboundEmailQueue`'s named lifecycle
steps -- see :mod:`models.outbound_email`. This service therefore exposes only the
read/delete surface the super_admin-only admin API needs; there is deliberately no
``create()`` or ``update()`` here.
"""

from collections.abc import Sequence

from models.outbound_email import OutboundEmailRead, OutboundEmailStatus
from repositories.exceptions import NotFoundError, OutboundEmailNotDeletableError
from repositories.outbound_email import OutboundEmailRepository
from repositories.query import FilterSpec, SortSpec

#: Statuses a row may be deleted from. `pending`/`sending` rows may be actively
#: claimed by the queue worker and are excluded.
_DELETABLE_STATUSES = frozenset({OutboundEmailStatus.sent, OutboundEmailStatus.failed})


class OutboundEmailService:
    """Application service orchestrating OutboundEmail read/delete operations."""

    def __init__(self, repo: OutboundEmailRepository) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing OutboundEmail persistence, already
                scoped to the acting tenant.
        """
        self._repo = repo

    async def get(self, email_id: str) -> OutboundEmailRead:
        """Return the OutboundEmail with the given ID.

        Raises:
            NotFoundError: If no row exists with that ID in the acting tenant.
        """
        email = await self._repo.get(email_id)
        if email is None:
            raise NotFoundError("OutboundEmail", email_id)
        return email

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[OutboundEmailRead]:
        """Return a page of OutboundEmail rows in the acting tenant."""
        return await self._repo.list(
            limit=limit, offset=offset, sort=sort, filters=filters
        )

    async def delete(self, email_id: str) -> None:
        """Delete an OutboundEmail row, refusing one that is not yet terminal.

        Raises:
            NotFoundError: If no row exists with that ID in the acting tenant.
            OutboundEmailNotDeletableError: If the row's status is `pending`
                or `sending`.
        """
        email = await self.get(email_id)
        if email.status not in _DELETABLE_STATUSES:
            raise OutboundEmailNotDeletableError(email_id, email.status.value)
        await self._repo.delete(email_id)
