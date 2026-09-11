"""Session file repository: Protocol interface and SQLModel-backed implementation.

Every query is filtered by both the tenant and the owning WorkflowExecution, which
is what keeps one workflow session's files invisible to another: there is no method
that reads a file by id alone.

Listing deliberately never loads the ``data`` column. A session can hold a few
hundred megabytes of files, and the two callers that list them -- the agent's
``list_session_files`` tool and the context injected into a run -- want names and
sizes, not bytes. Only :meth:`SqlSessionFileRepository.get` fetches the blob, and it
exists to serve exactly one download.
"""

from typing import Protocol, cast

from sqlalchemy import func
from sqlalchemy.orm import QueryableAttribute, defer
from sqlmodel import col, select

from models.session_file import SessionFile, SessionFileOrigin, SessionFileRead
from repositories._integrity import commit_or_translate_user_fk
from repositories._scoped import TenantScopedRepository


class SessionFileRepository(Protocol):
    """Interface for session-file persistence operations."""

    async def list_for_execution(self, execution_id: str) -> list[SessionFileRead]: ...

    async def get(self, execution_id: str, file_id: str) -> SessionFile | None: ...

    async def name_exists(self, execution_id: str, name: str) -> bool: ...

    async def total_bytes(self, execution_id: str) -> int: ...

    async def create(
        self,
        execution_id: str,
        *,
        name: str,
        data: bytes,
        content_type: str,
        origin: SessionFileOrigin,
        user_id: str,
    ) -> SessionFile: ...


class SqlSessionFileRepository(TenantScopedRepository[SessionFile]):
    """SQLModel-backed implementation of :class:`SessionFileRepository`.

    ``tenant_id`` follows the same convention as
    :class:`~repositories.workflow_execution.SqlWorkflowExecutionRepository`:
    a concrete id scopes every query to that tenant, and ``None`` -- the
    platform-scoped read case -- leaves the tenant predicate off. Writes always
    need a concrete tenant.
    """

    model = SessionFile

    async def list_for_execution(self, execution_id: str) -> list[SessionFileRead]:
        """Return the metadata of every file in a run's workflow session.

        Ordered oldest first, so a listing reads as the session's own history:
        what the initiator attached, then what the agent produced from it.

        ``data`` is deferred, so the query loads names and sizes and leaves
        every byte in the database. The returned rows are converted to
        :class:`SessionFileRead` right here and never handed out as entities:
        touching a deferred attribute later would emit a lazy load, which under
        an async session raises rather than quietly fetching.

        Args:
            execution_id: Identifier of the owning WorkflowExecution.

        Returns:
            One :class:`SessionFileRead` per file, oldest first.
        """
        stmt = (
            select(SessionFile)
            .where(col(SessionFile.workflow_execution_id) == execution_id)
            # ``col`` under-types its result as ``Mapped``; ``defer`` wants the
            # ``QueryableAttribute`` the same object actually is at runtime.
            .options(defer(cast(QueryableAttribute[bytes], col(SessionFile.data))))
            .order_by(col(SessionFile.created_at), col(SessionFile.id))
        )
        stmt = self._scoped(stmt)
        rows = (await self._db.exec(stmt)).all()
        return [SessionFileRead.model_validate(row) for row in rows]

    async def get(self, execution_id: str, file_id: str) -> SessionFile | None:
        """Return one file *with its bytes*, or ``None`` when it is not in this session.

        Both the file id and its owning execution are matched, so an id from
        another run reads as missing rather than as forbidden -- the same
        404-not-403 rule the tenant scoping elsewhere follows.

        Args:
            execution_id: Identifier of the owning WorkflowExecution.
            file_id: Identifier of the file.

        Returns:
            The stored :class:`SessionFile`, or ``None``.
        """
        stmt = select(SessionFile).where(
            col(SessionFile.id) == file_id,
            col(SessionFile.workflow_execution_id) == execution_id,
        )
        stmt = self._scoped(stmt)
        return (await self._db.exec(stmt)).first()

    async def name_exists(self, execution_id: str, name: str) -> bool:
        """Return whether the session already holds a file under this name.

        Args:
            execution_id: Identifier of the owning WorkflowExecution.
            name: File name to test.

        Returns:
            ``True`` when the name is taken.
        """
        stmt = select(SessionFile.id).where(
            col(SessionFile.workflow_execution_id) == execution_id,
            col(SessionFile.name) == name,
        )
        stmt = self._scoped(stmt)
        return (await self._db.exec(stmt)).first() is not None

    async def total_bytes(self, execution_id: str) -> int:
        """Return the combined size of every file in a run's workflow session.

        Backs the per-session quota. Summing the ``size_bytes`` column rather
        than measuring the blobs keeps the check off the bytes themselves.

        Args:
            execution_id: Identifier of the owning WorkflowExecution.

        Returns:
            The total stored size in bytes; ``0`` when the session has no files.
        """
        stmt = select(func.coalesce(func.sum(col(SessionFile.size_bytes)), 0)).where(
            col(SessionFile.workflow_execution_id) == execution_id
        )
        stmt = self._scoped(stmt)
        return int((await self._db.exec(stmt)).one())

    async def create(
        self,
        execution_id: str,
        *,
        name: str,
        data: bytes,
        content_type: str,
        origin: SessionFileOrigin,
        user_id: str,
    ) -> SessionFile:
        """Store a new file in a run's workflow session.

        Args:
            execution_id: Identifier of the owning WorkflowExecution.
            name: File name, unique within the session.
            data: Raw file bytes.
            content_type: MIME type recorded alongside the bytes.
            origin: Whether a participant uploaded the file or the agent wrote it.
            user_id: ID of the user the write is attributed to (audit fields).

        Returns:
            The stored :class:`SessionFile`.

        Raises:
            ForeignKeyViolationError: If the acting user does not exist.
        """
        record = SessionFile(
            workflow_execution_id=execution_id,
            name=name,
            data=data,
            content_type=content_type,
            size_bytes=len(data),
            origin=origin,
            tenant_id=self._require_tenant(),
            created_by=user_id,
            updated_by=user_id,
        )
        self._db.add(record)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(record)
        return record
