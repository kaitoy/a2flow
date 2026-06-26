"""MessageSender repository: Protocol interface and SQLModel-backed implementation."""

from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.message_sender import MessageSender
from repositories._integrity import commit_or_translate_user_fk


class MessageSenderRepository(Protocol):
    """Interface for per-message sender attribution persistence."""

    async def record(
        self, *, workflow_session_id: str, adk_event_id: str, sender_user_id: str
    ) -> None: ...

    async def senders_for_session(self, workflow_session_id: str) -> dict[str, str]: ...


class SqlMessageSenderRepository:
    """SQLModel-backed implementation of MessageSenderRepository."""

    def __init__(self, session: AsyncSession) -> None:
        """Store the SQLModel async session used for all queries."""
        self._db = session

    async def record(
        self, *, workflow_session_id: str, adk_event_id: str, sender_user_id: str
    ) -> None:
        """Attribute one ADK user event to its sender, ignoring duplicates.

        Recording is idempotent: if the ``(workflow_session_id, adk_event_id)``
        pair is already attributed, the call is a no-op so re-processing a run
        does not fail on the unique constraint.

        Args:
            workflow_session_id: The owning workflow session id.
            adk_event_id: The id of the ADK ``"user"`` event being attributed.
            sender_user_id: The user who actually sent the message; also recorded
                in the audit fields.

        Raises:
            ForeignKeyViolationError: If ``sender_user_id`` does not match an
                existing user.
        """
        existing = await self._db.exec(
            select(MessageSender.id)
            .where(
                col(MessageSender.workflow_session_id) == workflow_session_id,
                col(MessageSender.adk_event_id) == adk_event_id,
            )
            .limit(1)
        )
        if existing.first() is not None:
            return
        record = MessageSender(
            workflow_session_id=workflow_session_id,
            adk_event_id=adk_event_id,
            sender_user_id=sender_user_id,
            created_by=sender_user_id,
            updated_by=sender_user_id,
        )
        self._db.add(record)
        await commit_or_translate_user_fk(self._db, user_id=sender_user_id)

    async def senders_for_session(self, workflow_session_id: str) -> dict[str, str]:
        """Return the ``adk_event_id -> sender_user_id`` map for a session.

        Args:
            workflow_session_id: The workflow session whose attributions to load.

        Returns:
            A mapping from ADK user event id to the user id that sent it. Events
            without an attribution row are simply absent from the map.
        """
        result = await self._db.exec(
            select(MessageSender.adk_event_id, MessageSender.sender_user_id).where(
                col(MessageSender.workflow_session_id) == workflow_session_id
            )
        )
        return {event_id: user_id for event_id, user_id in result.all()}
