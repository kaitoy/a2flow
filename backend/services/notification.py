"""Use case service for Notification resources.

Wraps :class:`NotificationRepository` with the business rules the router needs:
every read and mutation is scoped to the requesting user, and accessing another
user's notification is indistinguishable from it not existing (``NotFoundError``)
so the API never leaks the existence of other users' notifications.
"""

from models.notification import Notification, NotificationUpdate
from repositories import NotificationRepository
from repositories.exceptions import NotFoundError
from repositories.query import FilterSpec, SortSpec


class NotificationService:
    """Application service orchestrating Notification operations."""

    def __init__(self, repo: NotificationRepository) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing Notification persistence.
        """
        self._repo = repo

    async def list(
        self,
        *,
        user_id: str,
        limit: int,
        offset: int,
        sort: tuple[SortSpec, ...] | list[SortSpec] = (),
        filters: tuple[FilterSpec, ...] | list[FilterSpec] = (),
    ) -> list[Notification]:
        """Return the requesting user's notifications, defaulting to newest first.

        Args:
            user_id: The recipient whose notifications to return.
            limit: Maximum number of records.
            offset: Number of records to skip.
            sort: Sort specifications; defaults to ``created_at`` descending.
            filters: Filter specifications applied as a conjunction. Unread-only
                listing is expressed as ``read:eq:false``.

        Returns:
            The user's notifications.
        """
        return await self._repo.list(
            user_id=user_id,
            limit=limit,
            offset=offset,
            sort=sort,
            filters=filters,
        )

    async def get(self, notification_id: str, *, user_id: str) -> Notification:
        """Return one of the user's notifications.

        Args:
            notification_id: Identifier of the notification to fetch.
            user_id: The requesting user; must be the notification's recipient.

        Returns:
            The matching notification.

        Raises:
            NotFoundError: If the notification does not exist or is not addressed
                to ``user_id``.
        """
        notification = await self._repo.get(notification_id)
        if notification is None or notification.user_id != user_id:
            raise NotFoundError("Notification", notification_id)
        return notification

    async def update(
        self, notification_id: str, data: NotificationUpdate, *, user_id: str
    ) -> Notification:
        """Apply a partial update to one of the user's notifications.

        Only the read flag is mutable, which :class:`NotificationUpdate` already
        enforces by being the sole field it declares.

        Args:
            notification_id: Identifier of the notification to update.
            data: Fields to apply; unset fields are left untouched.
            user_id: The requesting user; must be the notification's recipient.

        Returns:
            The updated notification.

        Raises:
            NotFoundError: If the notification does not exist or is not addressed
                to ``user_id``.
        """
        await self.get(notification_id, user_id=user_id)
        return await self._repo.update(notification_id, data, user_id=user_id)

    async def mark_all_read(self, *, user_id: str) -> None:
        """Mark all of the requesting user's unread notifications as read.

        Args:
            user_id: The requesting user whose notifications to mark read.
        """
        await self._repo.mark_all_read(user_id=user_id)

    async def delete(self, notification_id: str, *, user_id: str) -> None:
        """Delete one of the user's notifications.

        Args:
            notification_id: Identifier of the notification to delete.
            user_id: The requesting user; must be the notification's recipient.

        Raises:
            NotFoundError: If the notification does not exist or is not addressed
                to ``user_id``.
        """
        await self.get(notification_id, user_id=user_id)
        await self._repo.delete(notification_id)
