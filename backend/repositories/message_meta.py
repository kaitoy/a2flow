"""MessageMeta repository: Protocol interface and SQLModel-backed implementation."""

from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.message_meta import MessageMeta
from repositories._integrity import commit_or_translate_user_fk
from repositories.exceptions import ForeignKeyViolationError


class MessageMetaRepository(Protocol):
    """Interface for per-message side-channel metadata persistence."""

    async def set_sender(
        self, *, workflow_session_id: str, adk_event_id: str, sender_user_id: str
    ) -> None: ...

    async def set_task(
        self,
        *,
        workflow_session_id: str,
        adk_event_id: str,
        workflow_task_id: str,
        user_id: str,
    ) -> None: ...

    async def meta_for_session(
        self, workflow_session_id: str
    ) -> dict[str, MessageMeta]: ...


class SqlMessageMetaRepository:
    """SQLModel-backed implementation of MessageMetaRepository.

    Each event has at most one row, created lazily by whichever setter records a
    fact about it first. ``set_sender`` and ``set_task`` therefore upsert: they
    create the row if absent and otherwise update only their own field, leaving
    the other field intact. Each setter commits independently so a best-effort
    task association cannot roll back a sender attribution (or vice versa).
    """

    def __init__(self, session: AsyncSession, *, tenant_id: str) -> None:
        """Store the SQLModel async session and the tenant these queries are scoped to."""
        self._db = session
        self._tenant_id = tenant_id

    async def _get(
        self, workflow_session_id: str, adk_event_id: str
    ) -> MessageMeta | None:
        """Return the metadata row for one event, or ``None`` if not yet recorded."""
        result = await self._db.exec(
            select(MessageMeta)
            .where(
                col(MessageMeta.workflow_session_id) == workflow_session_id,
                col(MessageMeta.adk_event_id) == adk_event_id,
                MessageMeta.tenant_id == self._tenant_id,
            )
            .limit(1)
        )
        return result.first()

    async def set_sender(
        self, *, workflow_session_id: str, adk_event_id: str, sender_user_id: str
    ) -> None:
        """Attribute one ADK user event to its sender, upserting its metadata row.

        Creates the event's row if absent, otherwise sets ``sender_user_id`` in
        place while leaving any recorded task untouched. Idempotent: when the
        sender is already recorded the call is a no-op, so re-processing a run
        does not churn the row.

        Args:
            workflow_session_id: The owning workflow session id.
            adk_event_id: The id of the ADK ``"user"`` event being attributed.
            sender_user_id: The user who actually sent the message; also recorded
                in the audit fields.

        Raises:
            ForeignKeyViolationError: If ``sender_user_id`` does not match an
                existing user.
        """
        row = await self._get(workflow_session_id, adk_event_id)
        if row is not None and row.sender_user_id == sender_user_id:
            return
        if row is None:
            row = MessageMeta(
                workflow_session_id=workflow_session_id,
                adk_event_id=adk_event_id,
                sender_user_id=sender_user_id,
                tenant_id=self._tenant_id,
                created_by=sender_user_id,
                updated_by=sender_user_id,
            )
        else:
            row.sender_user_id = sender_user_id
            row.updated_by = sender_user_id
        self._db.add(row)
        await commit_or_translate_user_fk(self._db, user_id=sender_user_id)

    async def set_task(
        self,
        *,
        workflow_session_id: str,
        adk_event_id: str,
        workflow_task_id: str,
        user_id: str,
    ) -> None:
        """Associate one ADK event with the WorkflowTask in progress when produced.

        Creates the event's row if absent, otherwise sets ``workflow_task_id`` in
        place while leaving any recorded sender untouched. Idempotent when the
        task is unchanged. Best-effort: if the referenced task no longer exists
        (it was deleted during the run), the foreign-key violation is swallowed
        and the association skipped.

        Args:
            workflow_session_id: The owning workflow session id.
            adk_event_id: The id of the ADK event being associated.
            workflow_task_id: The id of the in-progress WorkflowTask.
            user_id: The acting user recorded in the audit fields (the session
                owner).

        Raises:
            ForeignKeyViolationError: If ``user_id`` does not match an existing
                user (the audit FK); a missing task is swallowed instead.
        """
        row = await self._get(workflow_session_id, adk_event_id)
        if row is not None and row.workflow_task_id == workflow_task_id:
            return
        if row is None:
            row = MessageMeta(
                workflow_session_id=workflow_session_id,
                adk_event_id=adk_event_id,
                workflow_task_id=workflow_task_id,
                tenant_id=self._tenant_id,
                created_by=user_id,
                updated_by=user_id,
            )
        else:
            row.workflow_task_id = workflow_task_id
            row.updated_by = user_id
        self._db.add(row)
        try:
            await commit_or_translate_user_fk(self._db, user_id=user_id)
        except ForeignKeyViolationError:
            # The task was deleted during the run; the audit user always exists,
            # so this is the task FK. The commit already rolled back, so the row
            # change is reverted -- skip the association.
            return

    async def meta_for_session(
        self, workflow_session_id: str
    ) -> dict[str, MessageMeta]:
        """Return the ``adk_event_id -> MessageMeta`` map for a session.

        Args:
            workflow_session_id: The workflow session whose metadata to load.

        Returns:
            A mapping from ADK event id to its metadata row. Events without a
            row are simply absent from the map.
        """
        result = await self._db.exec(
            select(MessageMeta).where(
                col(MessageMeta.workflow_session_id) == workflow_session_id,
                MessageMeta.tenant_id == self._tenant_id,
            )
        )
        return {row.adk_event_id: row for row in result.all()}
