"""AuthSession repository: Protocol interface and SQLModel-backed implementation."""

from datetime import datetime
from typing import Protocol

from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.auth_session import AuthSession


class AuthSessionRepository(Protocol):
    """Interface for login-session persistence operations."""

    async def create(
        self,
        *,
        user_id: str,
        token_hash: str,
        csrf_token: str,
        prune_before: datetime,
    ) -> AuthSession: ...

    async def get_by_token_hash(self, token_hash: str) -> AuthSession | None: ...

    async def touch(self, session: AuthSession, now: datetime) -> None: ...

    async def delete_by_token_hash(self, token_hash: str) -> None: ...

    async def delete_for_user(self, user_id: str) -> None: ...


class SqlAuthSessionRepository:
    """SQLModel-backed implementation of :class:`AuthSessionRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: The request-scoped async database session.
        """
        self._db = session

    async def create(
        self,
        *,
        user_id: str,
        token_hash: str,
        csrf_token: str,
        prune_before: datetime,
    ) -> AuthSession:
        """Insert a new login session for the given user and prune expired ones.

        A session whose token is never presented again is otherwise never
        deleted, and logins are the only thing that adds rows, so pruning here
        keeps the table to roughly one idle window's worth of logins.

        Args:
            user_id: The authenticated user's id.
            token_hash: SHA-256 hash of the session cookie token.
            csrf_token: The double-submit CSRF token value.
            prune_before: Sessions last active before this have passed the idle
                timeout and are deleted in the same transaction.

        Returns:
            The persisted ``AuthSession``.
        """
        # ponytail: no index on last_active_at, so this scans the table; that
        # stays small while every login prunes it. Index it if the scan shows up.
        await self._db.exec(
            delete(AuthSession).where(col(AuthSession.last_active_at) < prune_before)
        )
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

    async def delete_for_user(self, user_id: str) -> None:
        """Delete every login session belonging to a user.

        Args:
            user_id: The user whose sessions to revoke.
        """
        await self._db.exec(
            delete(AuthSession).where(col(AuthSession.user_id) == user_id)
        )
        await self._db.commit()
