"""AuthSession repository: Protocol interface and SQLModel-backed implementation."""

from datetime import datetime
from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.auth_session import AuthSession


class AuthSessionRepository(Protocol):
    """Interface for login-session persistence operations."""

    async def create(
        self, *, user_id: str, token_hash: str, csrf_token: str
    ) -> AuthSession: ...

    async def get_by_token_hash(self, token_hash: str) -> AuthSession | None: ...

    async def touch(self, session: AuthSession, now: datetime) -> None: ...

    async def delete_by_token_hash(self, token_hash: str) -> None: ...


class SqlAuthSessionRepository:
    """SQLModel-backed implementation of :class:`AuthSessionRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: The request-scoped async database session.
        """
        self._db = session

    async def create(
        self, *, user_id: str, token_hash: str, csrf_token: str
    ) -> AuthSession:
        """Insert a new login session for the given user.

        Args:
            user_id: The authenticated user's id.
            token_hash: SHA-256 hash of the session cookie token.
            csrf_token: The double-submit CSRF token value.

        Returns:
            The persisted ``AuthSession``.
        """
        auth_session = AuthSession(
            user_id=user_id, token_hash=token_hash, csrf_token=csrf_token
        )
        self._db.add(auth_session)
        await self._db.commit()
        await self._db.refresh(auth_session)
        return auth_session

    async def get_by_token_hash(self, token_hash: str) -> AuthSession | None:
        """Return the session matching the given token hash, or ``None``.

        Args:
            token_hash: SHA-256 hash of the presented session token.

        Returns:
            The matching ``AuthSession`` or ``None``.
        """
        stmt = select(AuthSession).where(col(AuthSession.token_hash) == token_hash)
        return (await self._db.exec(stmt)).first()

    async def touch(self, session: AuthSession, now: datetime) -> None:
        """Refresh a session's ``last_active_at`` to slide the idle timeout.

        Args:
            session: The session to refresh.
            now: The timestamp to record as the last activity time.
        """
        session.last_active_at = now
        self._db.add(session)
        await self._db.commit()

    async def delete_by_token_hash(self, token_hash: str) -> None:
        """Delete the session matching the given token hash, if any.

        Args:
            token_hash: SHA-256 hash of the session token to revoke.
        """
        session = await self.get_by_token_hash(token_hash)
        if session is not None:
            await self._db.delete(session)
            await self._db.commit()
