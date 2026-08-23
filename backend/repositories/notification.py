"""Notification repository: Protocol interface and SQLModel-backed implementation.

Notifications are always queried in the scope of a single recipient: every read
takes a ``user_id`` and filters on it, so one user can never see another's
notifications at the persistence layer.
"""

from collections.abc import Sequence
from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.notification import (
    Notification,
    NotificationCreate,
    NotificationType,
    NotificationUpdate,
    build_notification_link,
)
from repositories._integrity import commit_or_translate_user_fk
from repositories.exceptions import NotFoundError
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort


class NotificationRepository(Protocol):
    """Interface for Notification persistence operations."""

    async def get(self, notification_id: str) -> Notification | None: ...

    async def list(
        self,
        *,
        user_id: str,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[Notification]: ...

    def stage(self, data: NotificationCreate, *, user_id: str) -> Notification: ...

    async def create(
        self, data: NotificationCreate, *, user_id: str
    ) -> Notification: ...

    async def update(
        self, notification_id: str, data: NotificationUpdate, *, user_id: str
    ) -> Notification: ...

    async def delete(self, notification_id: str) -> None: ...

    async def mark_all_read(self, *, user_id: str) -> int: ...

    async def exists_for_session(
        self, workflow_execution_id: str, notification_type: NotificationType
    ) -> bool: ...


class SqlNotificationRepository:
    """SQLModel-backed implementation of NotificationRepository."""

    def __init__(self, session: AsyncSession, *, tenant_id: str) -> None:
        """Store the SQLModel async session and the tenant these queries are scoped to."""
        self._db = session
        self._tenant_id = tenant_id

    async def _get_scoped(self, notification_id: str) -> Notification | None:
        """Return the Notification with the given ID within the current tenant, or ``None``."""
        stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.tenant_id == self._tenant_id,
        )
        result = await self._db.exec(stmt)
        return result.first()

    async def get(self, notification_id: str) -> Notification | None:
        """Return the Notification with the given ID, or ``None`` if missing."""
        return await self._get_scoped(notification_id)

    async def list(
        self,
        *,
        user_id: str,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[Notification]:
        """Return the recipient's notifications, defaulting to newest first.

        The recipient and tenant predicates are applied unconditionally, before
        any caller-supplied ``filters``. Since :func:`apply_filters` only ever
        adds conjunctions, a filter naming ``userId`` or ``tenantId`` can narrow
        the result set but never widen it beyond this recipient's own
        notifications.

        Args:
            user_id: Recipient whose notifications to return.
            limit: Maximum number of records.
            offset: Number of records to skip.
            sort: Sort specifications; defaults to ``created_at`` descending.
            filters: Filter specifications applied as a conjunction. Unread-only
                listing is expressed as ``read:eq:false``.

        Returns:
            The matching notifications.
        """
        stmt = select(Notification).where(
            Notification.user_id == user_id,
            Notification.tenant_id == self._tenant_id,
        )
        stmt = apply_filters(stmt, Notification, filters, readable=Notification)
        stmt = apply_sort(
            stmt,
            Notification,
            sort,
            default=[col(Notification.created_at).desc()],
            readable=Notification,
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    def stage(self, data: NotificationCreate, *, user_id: str) -> Notification:
        """Add a new Notification to the session **without committing** it.

        Exists so a caller can write a notification and something else in one
        transaction — :class:`services.notification_dispatch.NotificationDispatcher`
        stages the notification and its outgoing email together, so a crash can
        never leave a notification whose email was never queued. :meth:`create`
        is this plus the commit, which is what every other caller wants.

        Args:
            data: The notification to create; ``user_id`` on it is the recipient.
            user_id: The acting user recorded in the audit fields.

        Returns:
            The pending instance, already populated with its id and deep link.
            It is not refreshed from the database, since it has not been
            written yet.
        """
        notification = Notification.model_validate(
            {
                **data.model_dump(),
                "tenant_id": self._tenant_id,
                "created_by": user_id,
                "updated_by": user_id,
                "link": build_notification_link(
                    data.type,
                    workflow_execution_id=data.workflow_execution_id,
                    workflow_id=data.workflow_id,
                ),
            }
        )
        self._db.add(notification)
        return notification

    async def create(self, data: NotificationCreate, *, user_id: str) -> Notification:
        """Persist a new Notification with audit fields and its deep link populated."""
        notification = self.stage(data, user_id=user_id)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(notification)
        return notification

    async def update(
        self, notification_id: str, data: NotificationUpdate, *, user_id: str
    ) -> Notification:
        """Apply a partial update to a Notification, raising NotFoundError if missing."""
        notification = await self._get_scoped(notification_id)
        if notification is None:
            raise NotFoundError("Notification", notification_id)
        notification.sqlmodel_update(data.model_dump(exclude_unset=True))
        notification.updated_by = user_id
        self._db.add(notification)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(notification)
        return notification

    async def delete(self, notification_id: str) -> None:
        """Delete a Notification by ID, raising NotFoundError if it does not exist.

        Notifications are leaf rows that nothing references, so a plain commit
        cannot raise a referential-integrity error.
        """
        notification = await self._get_scoped(notification_id)
        if notification is None:
            raise NotFoundError("Notification", notification_id)
        await self._db.delete(notification)
        await self._db.commit()

    async def mark_all_read(self, *, user_id: str) -> int:
        """Mark all of the recipient's unread notifications as read.

        Args:
            user_id: Recipient whose unread notifications to mark read; also
                recorded as the acting ``updated_by`` on each affected row.

        Returns:
            The number of notifications that were marked read.
        """
        stmt = select(Notification).where(
            Notification.user_id == user_id,
            Notification.tenant_id == self._tenant_id,
            col(Notification.read).is_(False),
        )
        result = await self._db.exec(stmt)
        notifications = list(result.all())
        for notification in notifications:
            notification.read = True
            notification.updated_by = user_id
            self._db.add(notification)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        return len(notifications)

    async def exists_for_session(
        self, workflow_execution_id: str, notification_type: NotificationType
    ) -> bool:
        """Return whether a notification of the given type already exists for a session.

        Used to keep one-shot events (such as ``execution_completed``) idempotent so
        repeated triggers do not produce duplicate notifications.
        """
        stmt = (
            select(Notification.id)
            .where(Notification.workflow_execution_id == workflow_execution_id)
            .where(Notification.type == notification_type)
            .where(Notification.tenant_id == self._tenant_id)
            .limit(1)
        )
        result = await self._db.exec(stmt)
        return result.first() is not None
