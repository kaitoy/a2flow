"""Use case service for Notification resources.

Wraps :class:`NotificationRepository` with the business rules the router needs:
every read and mutation is scoped to the requesting user, and accessing another
user's notification is indistinguishable from it not existing (``NotFoundError``)
so the API never leaks the existence of other users' notifications.
"""

from models.notification import Notification, NotificationUpdate
from repositories import NotificationRepository
from repositories.exceptions import NotFoundError


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
        unread_only: bool = False,
    ) -> list[Notification]:
        """Return the requesting user's notifications, newest first.

        Args:
            user_id: The recipient whose notifications to return.
            limit: Maximum number of records.
            offset: Number of records to skip.
            unread_only: When ``True``, exclude already-read notifications.

        Returns:
            The user's notifications.
        """
        return await self._repo.list(
            user_id=user_id, limit=limit, offset=offset, unread_only=unread_only
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

    async def mark_read(self, notification_id: str, *, user_id: str) -> Notification:
        """Mark one of the user's notifications as read.

        Args:
            notification_id: Identifier of the notification to update.
            user_id: The requesting user; must be the notification's recipient.

        Returns:
            The updated notification.

        Raises:
            NotFoundError: If the notification does not exist or is not addressed
                to ``user_id``.
        """
        await self.get(notification_id, user_id=user_id)
        return await self._repo.update(
            notification_id, NotificationUpdate(read=True), user_id=user_id
        )
