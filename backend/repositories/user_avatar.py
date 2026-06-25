"""User avatar repository: Protocol interface and SQLModel-backed implementation.

Persists a single :class:`~models.user_avatar.UserAvatar` per user and keeps the
owning :class:`~models.user.User`'s ``avatar_updated_at`` marker in sync within
the same transaction, so read views can report avatar presence without loading
the image blob.
"""

from datetime import UTC, datetime
from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.user import User
from models.user_avatar import UserAvatar
from repositories.exceptions import ForeignKeyViolationError, NotFoundError


class UserAvatarRepository(Protocol):
    """Interface for custom user-avatar persistence operations."""

    async def get(self, user_id: str) -> UserAvatar | None: ...

    async def upsert(
        self, user_id: str, *, data: bytes, content_type: str, acting_user_id: str
    ) -> UserAvatar: ...

    async def delete(self, user_id: str) -> None: ...


class SqlUserAvatarRepository:
    """SQLModel-backed implementation of :class:`UserAvatarRepository`.

    ``upsert`` and ``delete`` also maintain ``User.avatar_updated_at`` so the
    marker stays consistent with the stored blob.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def get(self, user_id: str) -> UserAvatar | None:
        """Return the user's avatar, or ``None`` when no custom image is stored.

        Args:
            user_id: Identifier of the owning user.

        Returns:
            The stored :class:`UserAvatar` or ``None``.
        """
        stmt = select(UserAvatar).where(col(UserAvatar.user_id) == user_id)
        return (await self._db.exec(stmt)).first()

    async def upsert(
        self, user_id: str, *, data: bytes, content_type: str, acting_user_id: str
    ) -> UserAvatar:
        """Create or replace the user's avatar and stamp ``avatar_updated_at``.

        Args:
            user_id: Identifier of the owning user.
            data: Raw image bytes to store.
            content_type: MIME type of the image (e.g. ``image/png``).
            acting_user_id: ID of the user performing the upload (audit fields).

        Returns:
            The stored :class:`UserAvatar`.

        Raises:
            ForeignKeyViolationError: If the owning user does not exist.
        """
        user = await self._db.get(User, user_id)
        if user is None:
            raise ForeignKeyViolationError("User", user_id)

        avatar = await self.get(user_id)
        if avatar is None:
            avatar = UserAvatar(
                user_id=user_id,
                data=data,
                content_type=content_type,
                created_by=acting_user_id,
                updated_by=acting_user_id,
            )
        else:
            avatar.data = data
            avatar.content_type = content_type
            avatar.updated_by = acting_user_id
        self._db.add(avatar)

        user.avatar_updated_at = datetime.now(UTC)
        self._db.add(user)

        await self._db.commit()
        await self._db.refresh(avatar)
        return avatar

    async def delete(self, user_id: str) -> None:
        """Remove the user's avatar and clear ``avatar_updated_at``.

        Args:
            user_id: Identifier of the owning user.

        Raises:
            NotFoundError: If the user has no stored avatar.
        """
        avatar = await self.get(user_id)
        if avatar is None:
            raise NotFoundError("UserAvatar", user_id)
        user = await self._db.get(User, user_id)
        if user is not None:
            user.avatar_updated_at = None
            self._db.add(user)
        await self._db.delete(avatar)
        await self._db.commit()
