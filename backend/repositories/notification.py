"""Notification repository: Protocol interface and SQLModel-backed implementation.

Notifications are always queried in the scope of a single recipient: every read
takes a ``user_id`` and filters on it, so one user can never see another's
notifications at the persistence layer.
"""

from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.notification import (
    Notification,
    NotificationCreate,
    NotificationType,
    NotificationUpdate,
)
from repositories._integrity import commit_or_translate_user_fk
from repositories.exceptions import NotFoundError


class NotificationRepository(Protocol):
    """Interface for Notification persistence operations."""

    async def get(self, notification_id: str) -> Notification | None: ...

    async def list(
        self,
        *,
        user_id: str,
        limit: int,
        offset: int,
        unread_only: bool = False,
    ) -> list[Notification]: ...

    async def create(
        self, data: NotificationCreate, *, user_id: str
    ) -> Notification: ...

    async def update(
        self, notification_id: str, data: NotificationUpdate, *, user_id: str
    ) -> Notification: ...

    async def exists_for_session(
        self, workflow_session_id: str, notification_type: NotificationType
    ) -> bool: ...


class SqlNotificationRepository:
    """SQLModel-backed implementation of NotificationRepository."""

    def __init__(self, session: AsyncSession) -> None:
        """Store the SQLModel async session used for all queries."""
        self._db = session

    async def get(self, notification_id: str) -> Notification | None:
        """Return the Notification with the given ID, or ``None`` if missing."""
        return await self._db.get(Notification, notification_id)

    async def list(
        self,
        *,
        user_id: str,
        limit: int,
        offset: int,
        unread_only: bool = False,
    ) -> list[Notification]:
        """Return the recipient's notifications, newest first.

        Args:
            user_id: Recipient whose notifications to return.
            limit: Maximum number of records.
            offset: Number of records to skip.
            unread_only: When ``True``, exclude already-read notifications.

        Returns:
            The matching notifications ordered by ``created_at`` descending.
        """
        stmt = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            stmt = stmt.where(col(Notification.read).is_(False))
        stmt = stmt.order_by(col(Notification.created_at).desc())
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def create(self, data: NotificationCreate, *, user_id: str) -> Notification:
        """Persist a new Notification with audit fields populated."""
        notification = Notification.model_validate(
            {**data.model_dump(), "created_by": user_id, "updated_by": user_id}
        )
        self._db.add(notification)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(notification)
        return notification

    async def update(
        self, notification_id: str, data: NotificationUpdate, *, user_id: str
    ) -> Notification:
        """Apply a partial update to a Notification, raising NotFoundError if missing."""
        notification = await self._db.get(Notification, notification_id)
        if notification is None:
            raise NotFoundError("Notification", notification_id)
        notification.sqlmodel_update(data.model_dump(exclude_unset=True))
        notification.updated_by = user_id
        self._db.add(notification)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(notification)
        return notification

    async def exists_for_session(
        self, workflow_session_id: str, notification_type: NotificationType
    ) -> bool:
        """Return whether a notification of the given type already exists for a session.

        Used to keep one-shot events (such as ``session_completed``) idempotent so
        repeated triggers do not produce duplicate notifications.
        """
        stmt = (
            select(Notification.id)
            .where(Notification.workflow_session_id == workflow_session_id)
            .where(Notification.type == notification_type)
            .limit(1)
        )
        result = await self._db.exec(stmt)
        return result.first() is not None
