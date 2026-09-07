"""Use case services for the files attached to a workflow session.

Split in two, along the line that matters:

:class:`SessionFileStore` holds what may be stored -- names are sanitized down to
a bare filename, sizes are capped per file and per session, and a name already
taken is never overwritten but suffixed instead. It knows nothing about callers.
That last rule is why the agent can only ever add to a session: there is no code
path here that replaces or removes stored bytes, so a file a participant uploaded
stays exactly as they uploaded it.

:class:`SessionFileService` wraps the store with who may touch it. Access is not a
new permission: both entry points fetch the owning WorkflowExecution and hand it to
:class:`~services.workflow_execution_access.WorkflowExecutionAccessPolicy`, so the
answer to "who can reach this session's files" is by construction the same as "who
can reach this session's chat". Uploading goes through the stricter
:meth:`~services.workflow_execution_access.WorkflowExecutionAccessPolicy.assert_access`
-- putting a file in front of the agent is acting on the run, exactly like driving
it -- while downloading goes through
:meth:`~services.workflow_execution_access.WorkflowExecutionAccessPolicy.assert_read_access`,
so a plain ``admin`` can read what a run produced without being able to feed it
anything.

The split is what makes the agent's tools safe to write. They run inside a turn
that the access policy already authorized and have no caller left to check, so
they take a :class:`SessionFileStore` and never see the policy at all -- rather
than taking the full service and being trusted to call the right method on it.
"""

import re
from collections.abc import Awaitable, Callable, Collection

from sqlmodel.ext.asyncio.session import AsyncSession

from models.session_file import SessionFile, SessionFileOrigin, SessionFileRead
from models.user import User
from repositories import (
    SessionFileRepository,
    SqlSessionFileRepository,
    WorkflowExecutionRepository,
)
from repositories.exceptions import NotFoundError, SessionFileValidationError
from services.workflow_execution_access import WorkflowExecutionAccessPolicy

#: Size of each chunk read from an upload stream while the per-file cap is checked.
_READ_CHUNK_BYTES = 64 * 1024

#: Longest accepted file name, in characters. Comfortably under the 255-byte limit
#: every common filesystem imposes, so a downloaded file can always be saved.
_MAX_NAME_LENGTH = 200

#: Characters removed from a supplied file name: C0 controls and DEL. They have no
#: business in a name and would corrupt the ``Content-Disposition`` header the name
#: is echoed in.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")

#: How many suffixed names (``report (2).csv`` … ) are tried before a write gives up.
_MAX_NAME_ATTEMPTS = 100


def _format_mib(size_bytes: int) -> str:
    """Render a byte count as a MiB figure for an error message.

    Args:
        size_bytes: The limit being reported.

    Returns:
        The size in MiB, without a trailing ``.0`` for whole values.
    """
    mib = size_bytes / (1024 * 1024)
    return f"{mib:.0f}" if mib.is_integer() else f"{mib:.1f}"


def sanitize_file_name(raw: str | None) -> str:
    """Reduce a client- or agent-supplied file name to a safe bare name.

    Everything up to the last path separator is dropped, so a name like
    ``../../etc/passwd`` or ``C:\\secrets\\key.pem`` becomes just its final
    segment. Control characters are removed because the name is echoed back in a
    ``Content-Disposition`` header. ``.`` and ``..`` survive that treatment as
    themselves and are rejected outright.

    Args:
        raw: The supplied name, possibly ``None`` or empty.

    Returns:
        The sanitized bare file name.

    Raises:
        SessionFileValidationError: If nothing usable is left, or the result is
            longer than :data:`_MAX_NAME_LENGTH`.
    """
    candidate = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    candidate = _CONTROL_CHARS.sub("", candidate).strip()
    if not candidate or candidate in {".", ".."}:
        raise SessionFileValidationError("File name is empty or unusable")
    if len(candidate) > _MAX_NAME_LENGTH:
        raise SessionFileValidationError(
            f"File name is longer than {_MAX_NAME_LENGTH} characters"
        )
    return candidate


def describe_session_files(files: Collection[SessionFileRead]) -> str:
    """Render a session's files as the listing injected into an agent run.

    One line per file, naming the id the read tool takes, the size, and who put
    it there. Kept beside the store rather than in the router so the wording the
    agent sees at the start of a run matches what ``list_session_files`` returns
    mid-run.

    Args:
        files: The session's files, oldest first.

    Returns:
        A newline-separated listing; empty when there are no files.
    """
    origin_label = {
        SessionFileOrigin.user: "attached by a participant",
        SessionFileOrigin.agent: "written by you earlier",
    }
    return "\n".join(
        f"- {f.name} (id: {f.id}, {f.content_type}, {f.size_bytes} bytes, "
        f"{origin_label[f.origin]})"
        for f in files
    )


class SessionFileStore:
    """Validates and persists the files of one workflow session.

    Holds no notion of a caller -- see this module's docstring for why that is
    the point.
    """

    def __init__(
        self,
        files: SessionFileRepository,
        *,
        max_file_bytes: int,
        max_total_bytes: int,
    ) -> None:
        """Initialize the store.

        Args:
            files: Repository providing session-file persistence.
            max_file_bytes: Largest accepted single file, in bytes.
            max_total_bytes: Largest accepted combined size per session, in bytes.
        """
        self._files = files
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes

    async def read_capped(self, read: Callable[[int], Awaitable[bytes]]) -> bytes:
        """Drain an upload stream, refusing it as soon as it passes the per-file cap.

        Reading in chunks and stopping at the limit is what keeps an oversized
        body from being buffered whole before it is rejected.

        Args:
            read: The stream's chunked reader (an ``UploadFile.read``).

        Returns:
            The file's bytes.

        Raises:
            SessionFileValidationError: If the stream exceeds the per-file cap.
        """
        buffer = bytearray()
        while chunk := await read(_READ_CHUNK_BYTES):
            buffer.extend(chunk)
            if len(buffer) > self.max_file_bytes:
                raise SessionFileValidationError(
                    f"File exceeds the {_format_mib(self.max_file_bytes)} MiB size limit"
                )
        return bytes(buffer)

    async def list(self, execution_id: str) -> list[SessionFileRead]:
        """Return the metadata of every file in a run's workflow session.

        Args:
            execution_id: Identifier of the owning WorkflowExecution.

        Returns:
            One record per file, oldest first.
        """
        return await self._files.list_for_execution(execution_id)

    async def get(self, execution_id: str, file_id: str) -> SessionFile:
        """Return one file with its bytes.

        Args:
            execution_id: Identifier of the owning WorkflowExecution.
            file_id: Identifier of the file.

        Returns:
            The stored :class:`SessionFile`.

        Raises:
            NotFoundError: If the session holds no such file.
        """
        stored = await self._files.get(execution_id, file_id)
        if stored is None:
            raise NotFoundError("SessionFile", file_id)
        return stored

    async def add(
        self,
        execution_id: str,
        *,
        name: str,
        data: bytes,
        content_type: str,
        origin: SessionFileOrigin,
        user_id: str,
    ) -> SessionFileRead:
        """Validate a file and store it under a name free within the session.

        Args:
            execution_id: Identifier of the owning WorkflowExecution.
            name: Raw (unsanitized) file name.
            data: The file's bytes.
            content_type: MIME type to record.
            origin: Whether a participant or the agent produced the file.
            user_id: The user the write is attributed to.

        Returns:
            The stored file's metadata, carrying the name it actually got.

        Raises:
            SessionFileValidationError: If the file is empty, too large, named
                unusably, or would overflow the session's total size limit.
            ForeignKeyViolationError: If the acting user does not exist.
        """
        if not data:
            raise SessionFileValidationError("File is empty")
        if len(data) > self.max_file_bytes:
            raise SessionFileValidationError(
                f"File exceeds the {_format_mib(self.max_file_bytes)} MiB size limit"
            )
        await self._assert_fits(execution_id, len(data))
        resolved = await self._resolve_name(execution_id, sanitize_file_name(name))
        normalized = content_type.split(";", 1)[0].strip().lower()
        stored = await self._files.create(
            execution_id,
            name=resolved,
            data=data,
            content_type=normalized or "application/octet-stream",
            origin=origin,
            user_id=user_id,
        )
        return SessionFileRead.model_validate(stored)

    async def _assert_fits(self, execution_id: str, size: int) -> None:
        """Reject a write that would push the session over its total size limit.

        Args:
            execution_id: Identifier of the owning WorkflowExecution.
            size: Size of the file about to be stored, in bytes.

        Raises:
            SessionFileValidationError: If the session has no room left.
        """
        stored = await self._files.total_bytes(execution_id)
        if stored + size > self.max_total_bytes:
            raise SessionFileValidationError(
                f"The session's files would exceed the "
                f"{_format_mib(self.max_total_bytes)} MiB total size limit"
            )

    async def _resolve_name(self, execution_id: str, name: str) -> str:
        """Return a name free within the session, suffixing the given one if needed.

        A colliding write is renamed rather than refused or allowed to
        overwrite: refusing would fail an agent's turn over a detail it cannot
        see coming, and overwriting would destroy a file somebody uploaded.

        Args:
            execution_id: Identifier of the owning WorkflowExecution.
            name: The desired name, already sanitized.

        Returns:
            ``name`` itself when free, otherwise ``"<stem> (n)<.ext>"``.

        Raises:
            SessionFileValidationError: If no free name is found within
                :data:`_MAX_NAME_ATTEMPTS` attempts.
        """
        if not await self._files.name_exists(execution_id, name):
            return name
        stem, dot, extension = name.rpartition(".")
        base = stem if dot else name
        suffix = f".{extension}" if dot else ""
        for attempt in range(2, _MAX_NAME_ATTEMPTS + 2):
            candidate = f"{base} ({attempt}){suffix}"
            if not await self._files.name_exists(execution_id, candidate):
                return candidate
        raise SessionFileValidationError(
            f"The session already holds too many files named like {name!r}"
        )


class SessionFileService:
    """Application service gating a run's file store behind its access policy."""

    def __init__(
        self,
        store: SessionFileStore,
        executions: WorkflowExecutionRepository,
        access: WorkflowExecutionAccessPolicy,
    ) -> None:
        """Initialize the service.

        Args:
            store: The validating store the authorized operations delegate to.
            executions: Repository used to resolve the owning run, both to
                confirm it exists and to read the initiator the access policy
                compares against.
            access: The policy deciding who may read or act on a run.
        """
        self._store = store
        self._executions = executions
        self._access = access

    async def _require_execution(self, execution_id: str) -> str:
        """Return the initiator of an existing run, or raise.

        Fetching first is what keeps a missing run a 404 rather than a 403 --
        the access policy can only be asked about a run that exists.

        Args:
            execution_id: Identifier of the WorkflowExecution.

        Returns:
            The run initiator's user id.

        Raises:
            NotFoundError: If no such run exists in the caller's tenant.
        """
        execution = await self._executions.get(execution_id)
        if execution is None:
            raise NotFoundError("WorkflowExecution", execution_id)
        return execution.initiator_id

    async def upload(
        self,
        execution_id: str,
        *,
        filename: str | None,
        content_type: str | None,
        read: Callable[[int], Awaitable[bytes]],
        caller: User,
    ) -> SessionFileRead:
        """Attach an uploaded file to a run's workflow session.

        Args:
            execution_id: Identifier of the owning WorkflowExecution.
            filename: Name reported by the client, sanitized before use.
            content_type: MIME type reported by the client, recorded as-is for
                the agent's benefit. Downloads never serve a file under it.
            read: The upload stream's chunked reader (an ``UploadFile.read``).
            caller: The authenticated user performing the upload.

        Returns:
            The stored file's metadata.

        Raises:
            NotFoundError: If the run does not exist.
            ForbiddenError: If the caller may not act on the run.
            SessionFileValidationError: If the file fails validation.
        """
        initiator_id = await self._require_execution(execution_id)
        await self._access.assert_access(execution_id, initiator_id, caller)
        data = await self._store.read_capped(read)
        return await self._store.add(
            execution_id,
            name=filename or "",
            data=data,
            content_type=content_type or "application/octet-stream",
            origin=SessionFileOrigin.user,
            user_id=caller.id,
        )

    async def download(
        self,
        execution_id: str,
        file_id: str,
        *,
        caller: User,
        caller_roles: Collection[str],
    ) -> SessionFile:
        """Return a session file with its bytes, for serving to the caller.

        Args:
            execution_id: Identifier of the owning WorkflowExecution.
            file_id: Identifier of the file.
            caller: The authenticated user performing the download.
            caller_roles: The caller's effective roles, since ``admin`` -- which
                may read a run it has no part in -- can be granted by a group.

        Returns:
            The stored :class:`SessionFile`.

        Raises:
            NotFoundError: If the run or the file does not exist.
            ForbiddenError: If the caller may not read the run.
        """
        initiator_id = await self._require_execution(execution_id)
        await self._access.assert_read_access(
            execution_id, initiator_id, caller, caller_roles
        )
        return await self._store.get(execution_id, file_id)

    async def list_for_run(self, execution_id: str) -> list[SessionFileRead]:
        """Return the metadata of every file in an *already authorized* run.

        The agent route calls this after ``resolve_agent`` has authorized the
        run, to build the file listing injected into the turn's context. It
        performs no check of its own, which is why it names the precondition.

        Args:
            execution_id: Identifier of the owning WorkflowExecution.

        Returns:
            One record per file, oldest first.
        """
        return await self._store.list(execution_id)


def build_session_file_store(
    db: AsyncSession, *, tenant_id: str, max_file_bytes: int, max_total_bytes: int
) -> SessionFileStore:
    """Build a :class:`SessionFileStore` on a caller-owned database session.

    For the agent tools, which run outside FastAPI's request scope and open
    their own session, so they cannot receive the injected dependency the
    routes use.

    Args:
        db: The ``AsyncSession`` to build the repository on.
        tenant_id: Tenant the repository is scoped to.
        max_file_bytes: Largest accepted single file, in bytes.
        max_total_bytes: Largest accepted combined size per session, in bytes.

    Returns:
        A store backed by ``db``.
    """
    return SessionFileStore(
        SqlSessionFileRepository(db, tenant_id=tenant_id),
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
    )
