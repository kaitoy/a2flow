"""LoginFailure repository: Protocol interface and SQLModel-backed implementation."""

from datetime import datetime
from typing import Protocol

from sqlalchemy import func
from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.login_failure import LoginFailure


class LoginFailureRepository(Protocol):
    """Interface for recording and counting failed login attempts."""

    async def recent(
        self, key: str, since: datetime
    ) -> tuple[int, datetime | None]: ...

    async def record(self, key: str, now: datetime, prune_before: datetime) -> None: ...

    async def clear(self, key: str) -> None: ...


class SqlLoginFailureRepository:
    """SQLModel-backed implementation of :class:`LoginFailureRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: The request-scoped async database session.
        """
        self._db = session

    async def recent(self, key: str, since: datetime) -> tuple[int, datetime | None]:
        """Count a key's failures since a cutoff and find the oldest of them.

        Args:
            key: The throttle key.
            since: Only failures at or after this instant count.

        Returns:
            The number of matching failures and the earliest ``failed_at``
            among them (``None`` when there are none).
        """
        stmt = select(
            func.count(col(LoginFailure.id)), func.min(col(LoginFailure.failed_at))
        ).where(
            col(LoginFailure.key) == key,
            col(LoginFailure.failed_at) >= since,
        )
        count, oldest = (await self._db.exec(stmt)).one()
        return count, oldest

    async def record(self, key: str, now: datetime, prune_before: datetime) -> None:
        """Record one failure against a key and prune expired rows.

        Args:
            key: The throttle key the failed attempt counts against.
            now: When the attempt failed.
            prune_before: Rows older than this have left every window and
                are deleted in the same transaction.
        """
        await self._db.exec(
            delete(LoginFailure).where(col(LoginFailure.failed_at) < prune_before)
        )
        self._db.add(LoginFailure(key=key, failed_at=now))
        await self._db.commit()

    async def clear(self, key: str) -> None:
        """Delete every recorded failure for a key.

        Args:
            key: The throttle key to reset.
        """
        await self._db.exec(delete(LoginFailure).where(col(LoginFailure.key) == key))
        await self._db.commit()
