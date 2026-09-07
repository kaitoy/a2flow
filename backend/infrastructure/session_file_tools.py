"""ADK agent tools for the files attached to the current workflow session.

Attached to the execution agent (see :func:`infrastructure.agent.create_agent`) so
a run can work with the files its participants uploaded and hand results back as
files rather than as walls of text in the chat.

The agent may **read and create, never replace or remove**. There is no tool here
that overwrites or deletes, and :class:`services.session_file.SessionFileStore`
renames a colliding write rather than clobbering it, so a file a participant
uploaded survives whatever the agent does with it.

The two facts that shape :mod:`infrastructure.workflow_task_tools` shape this
module identically: the tools run *during* the AG-UI SSE stream, outside FastAPI's
dependency-injection scope, so each call opens its own ``AsyncSession`` on the
module-level engine; and one ``ADKAgent`` is cached per skill and serves every
session using it, so the run is resolved at call time by mapping the ADK session
id back to its WorkflowExecution and tenant through
:func:`repositories.tenant_bootstrap.resolve_workflow_execution_tenant`.

These tools take a :class:`~services.session_file.SessionFileStore`, not the
authorizing :class:`~services.session_file.SessionFileService`. They run inside a
turn ``WorkflowExecutionAccessPolicy`` has already authorized and have no caller
left to check; handing them the store means there is no access check here to
forget rather than one that is skipped on purpose.

Every tool returns plain JSON-serializable values so the LLM can consume them,
mapping failures to an ``{"error": ...}`` payload it can react to instead of
raising.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from google.adk.tools.tool_context import ToolContext
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure import database
from infrastructure.workflow_task_tools import ACTING_USER_STATE_KEY
from models.session_file import SessionFileOrigin, SessionFileRead
from repositories.exceptions import NotFoundError, SessionFileValidationError
from repositories.tenant_bootstrap import (
    NoTenantSessionError,
    resolve_workflow_execution_tenant,
)

if TYPE_CHECKING:
    # Type-only, for the same reason ``workflow_task_tools`` defers its own
    # ``services`` imports: importing any ``services`` submodule at runtime
    # executes ``services/__init__``, which reaches ``infrastructure.agent`` ->
    # back to this module. The runtime import is deferred into :func:`_store`.
    from services.session_file import SessionFileStore

_NO_SESSION = "no workflow execution is bound to the current run; cannot use files"


@asynccontextmanager
async def _store(
    tool_context: ToolContext,
) -> AsyncIterator[tuple[str, "SessionFileStore"]]:
    """Open a database session and yield the current run's id and file store.

    The engine is referenced through the ``database`` module so tests can
    monkeypatch ``database.engine``. The store builder is imported here rather
    than at module scope to break the import cycle noted above.

    Args:
        tool_context: The ADK tool context for the current invocation.

    Yields:
        The ``(workflow_execution_id, store)`` pair for this call.

    Raises:
        NoTenantSessionError: If no WorkflowExecution is bound to the current run.
    """
    from services.session_file import build_session_file_store

    settings = get_settings()
    async with AsyncSession(database.engine) as db:
        session = getattr(tool_context, "session", None)
        session_id = getattr(session, "id", None)
        resolved = (
            await resolve_workflow_execution_tenant(db, session_id)
            if session_id
            else None
        )
        if resolved is None:
            raise NoTenantSessionError()
        execution_id, tenant_id = resolved
        yield (
            execution_id,
            build_session_file_store(
                db,
                tenant_id=tenant_id,
                max_file_bytes=settings.session_file_max_bytes,
                max_total_bytes=settings.session_files_max_total_bytes,
            ),
        )


def _user_id(tool_context: ToolContext) -> str:
    """Return the acting caller's user id, for the audit fields on a written file.

    Same resolution as ``infrastructure.workflow_task_tools._user_id``: the
    per-turn acting user the router stamps into session state, falling back to
    the shared session's fixed owner.

    Args:
        tool_context: The ADK tool context for the current invocation.

    Returns:
        The user id to attribute the write to.
    """
    state = getattr(tool_context, "state", None)
    acting = state.get(ACTING_USER_STATE_KEY) if state is not None else None
    if acting:
        return str(acting)
    return getattr(tool_context, "user_id", None) or "user"


def _file_to_dict(file: SessionFileRead) -> dict[str, Any]:
    """Render one file's metadata as the shape the tools return.

    ``workflowExecutionId`` is included for the chat UI rather than for the
    model: a ``write_session_file`` result is persisted in the conversation and
    replayed as the download card the participants click, and carrying the run's
    id makes that card self-contained -- it can build its own download link on a
    reload, from the transcript alone.

    Args:
        file: The file's stored metadata.

    Returns:
        A JSON-serializable dict.
    """
    return {
        "fileId": file.id,
        "workflowExecutionId": file.workflow_execution_id,
        "name": file.name,
        "contentType": file.content_type,
        "sizeBytes": file.size_bytes,
        "origin": file.origin.value,
    }


async def list_session_files(tool_context: ToolContext) -> dict[str, Any]:
    """List the files attached to the current session, oldest first.

    The session's files are also listed in your context at the start of a turn.
    Call this when you need the list again after writing a file, since the
    context listing is a snapshot taken before the turn began.

    Args:
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        ``{"files": [{"fileId", "name", "contentType", "sizeBytes", "origin"},
        ...]}``, where ``origin`` is ``"user"`` for a file a participant
        attached and ``"agent"`` for one you wrote; or ``{"error": <message>}``
        if the session cannot be resolved.
    """
    try:
        async with _store(tool_context) as (execution_id, store):
            files = await store.list(execution_id)
            return {"files": [_file_to_dict(f) for f in files]}
    except NoTenantSessionError:
        return {"error": _NO_SESSION}


async def read_session_file(file_id: str, tool_context: ToolContext) -> dict[str, Any]:
    """Read the text content of one file attached to the current session.

    Only text is readable. A file whose bytes are not valid UTF-8 -- a
    spreadsheet, an image, an archive -- comes back as an error rather than as
    mangled text, so do not retry it: ask the participant for a text export
    instead.

    Args:
        file_id: Id of the file, as reported by ``list_session_files`` or by the
            session file listing in your context.
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        ``{"fileId", "name", "contentType", "sizeBytes", "content"}`` with the
        file's text, or ``{"error": <message>}`` if the session cannot be
        resolved, the file is not in this session, or it is not text.
    """
    try:
        async with _store(tool_context) as (execution_id, store):
            stored = await store.get(execution_id, file_id)
            try:
                content = stored.data.decode("utf-8")
            except UnicodeDecodeError:
                return {
                    "error": (
                        f"{stored.name!r} is not UTF-8 text, so its content cannot "
                        "be read. Ask for a text export of it instead."
                    )
                }
            return {
                "fileId": stored.id,
                "name": stored.name,
                "contentType": stored.content_type,
                "sizeBytes": stored.size_bytes,
                "content": content,
            }
    except NoTenantSessionError:
        return {"error": _NO_SESSION}
    except NotFoundError:
        return {"error": f"no file {file_id!r} in this session"}


async def write_session_file(
    name: str, content: str, content_type: str, tool_context: ToolContext
) -> dict[str, Any]:
    """Attach a new text file to the current session for its participants to download.

    Use this for anything long or structured you produce -- a report, a CSV
    extract, a generated config -- rather than pasting it into the chat. The
    file appears in the conversation with a download link.

    You can only add files. An existing file is never replaced: if ``name`` is
    already taken, the file is stored under a numbered variant and the name it
    actually got comes back in ``name``.

    Args:
        name: File name to store it under, including an extension (for example
            ``"error-summary.csv"``). Path separators are stripped.
        content: The file's text content.
        content_type: MIME type describing the content, for example
            ``"text/csv"``, ``"application/json"``, or ``"text/markdown"``.
        tool_context: Injected by ADK; identifies the current session. Not shown
            to the model.

    Returns:
        ``{"fileId", "name", "contentType", "sizeBytes", "origin"}`` for the
        stored file, or ``{"error": <message>}`` if the session cannot be
        resolved or the file was rejected (empty, too large, unusably named, or
        the session is at its total size limit).
    """
    try:
        async with _store(tool_context) as (execution_id, store):
            stored = await store.add(
                execution_id,
                name=name,
                data=content.encode("utf-8"),
                content_type=content_type,
                origin=SessionFileOrigin.agent,
                user_id=_user_id(tool_context),
            )
            return _file_to_dict(stored)
    except NoTenantSessionError:
        return {"error": _NO_SESSION}
    except SessionFileValidationError as exc:
        return {"error": exc.reason}
