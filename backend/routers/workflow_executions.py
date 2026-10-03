"""Endpoints for WorkflowExecution records and for their workflow sessions.

A WorkflowExecution is one run of a published workflow: the snapshot of the
workflow and skill it started against, plus the WorkflowTasks it works through.
The *workflow session* is the LLM chat that run happens in — the ADK session
named by ``WorkflowExecution.session_id``. It has no table of its own, so it is
identified by its execution. A run may be worked in several ADK sessions -- a
main session plus branch sessions forked from it -- each served from the
``/sessions/{session_id}`` sub-resources: its ``messages`` (the history), its
``input`` (what a person sends; the server runs the turn), and its ``stream``
(the turn's events, live, for every viewer).

A workflow session also holds files (:mod:`models.session_file`), served from
the ``/files`` sub-resources: participants attach them, the agent reads them and
writes new ones, and everyone who can read the chat can download them. A design
session has no equivalent.

Three further sub-resources aggregate these records for operational dashboards
rather than returning them one by one: ``/by-workflow`` (run volume and lead
time per workflow), ``/lead-time-trend`` (the same lead time as a daily series),
and ``/failures`` (runs needing human triage, with the failure cause each of
their failed tasks recorded). All three are declared before ``/{execution_id}``
so their literal path segment is matched first.
"""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from dependencies.auth import CurrentUserDep, EffectiveRolesDep
from dependencies.authz import require_roles
from dependencies.context import (
    ApiMetaDep,
    FilterDep,
    MetricsWindowDep,
    PaginationDep,
    SortDep,
)
from dependencies.service import (
    MetricsServiceDep,
    SessionFileServiceDep,
    WorkflowExecutionServiceDep,
)
from infrastructure import database
from models.execution_session import (
    ExecutionSession,
    SessionHistory,
    SessionInputCreate,
)
from models.mcp_tool_invocation import MCPToolInvocation
from models.metrics import (
    FailedExecutionEntry,
    LeadTimeBucket,
    WorkflowVolumeEntry,
)
from models.response import ApiResponse
from models.session_file import SessionFileRead
from models.user import Role
from models.workflow_execution import WorkflowExecutionRead
from models.workflow_task import WorkflowTaskRead
from services.metrics import MetricsWindow
from services.session_stream import stream_events

router = APIRouter(prefix="/workflow-executions", tags=["workflow-executions"])

#: Route dependency gating workflow-execution deletion behind the ``admin`` role.
_requires_admin = [Depends(require_roles(Role.admin))]


@router.get("", response_model=ApiResponse[list[WorkflowExecutionRead]])
async def list_workflow_executions(
    service: WorkflowExecutionServiceDep,
    caller: CurrentUserDep,
    caller_roles: EffectiveRolesDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[WorkflowExecutionRead]]:
    """Return WorkflowExecution records, defaulting to ``created_at`` descending.

    A super admin or admin sees every execution in the tenant; anyone else
    sees only executions they initiated or are a designated approver of.
    """
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        caller=caller,
        caller_roles=caller_roles,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.get("/by-workflow", response_model=ApiResponse[list[WorkflowVolumeEntry]])
async def workflow_execution_volume_by_workflow(
    service: MetricsServiceDep,
    window: MetricsWindowDep,
    pagination: PaginationDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[WorkflowVolumeEntry]]:
    """Return per-workflow run volume and average lead time over a time window.

    Answers "which workflows run most, and how long do they take end to end".
    The window defaults to the last 30 days; ``limit`` caps how many workflows
    come back, busiest first.
    """
    entries = await service.volume_by_workflow(
        MetricsWindow(since=window.since, until=window.until),
        limit=pagination.limit,
    )
    return ApiResponse(meta=meta, data=entries)


@router.get("/lead-time-trend", response_model=ApiResponse[list[LeadTimeBucket]])
async def workflow_execution_lead_time_trend(
    service: MetricsServiceDep,
    window: MetricsWindowDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[LeadTimeBucket]]:
    """Return the daily average lead time of runs finishing in a time window.

    One bucket per calendar day in the configured ``TIMEZONE``,
    including days on which nothing finished, so the series can be plotted as
    is.
    """
    buckets = await service.lead_time_trend(
        MetricsWindow(since=window.since, until=window.until)
    )
    return ApiResponse(meta=meta, data=buckets)


@router.get("/failures", response_model=ApiResponse[list[FailedExecutionEntry]])
async def list_failed_workflow_executions(
    service: MetricsServiceDep,
    window: MetricsWindowDep,
    pagination: PaginationDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[FailedExecutionEntry]]:
    """Return the runs with failed tasks in a window, each with its failures.

    The triage list: driven by the failed tasks rather than by the runs' own
    status, so a run that is still in flight but already has a failure shows up
    right away.
    """
    entries = await service.failed_executions(
        MetricsWindow(since=window.since, until=window.until),
        limit=pagination.limit,
    )
    return ApiResponse(meta=meta, data=entries)


@router.get("/{execution_id}", response_model=ApiResponse[WorkflowExecutionRead])
async def get_workflow_execution(
    execution_id: str,
    service: WorkflowExecutionServiceDep,
    caller: CurrentUserDep,
    caller_roles: EffectiveRolesDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowExecutionRead]:
    """Return the WorkflowExecution record for the given ID.

    Only the execution's initiator, a designated approver of the execution,
    an admin, or a super admin may access it; anyone else receives HTTP 403
    (``FORBIDDEN``).
    """
    execution = await service.get(
        execution_id, caller=caller, caller_roles=caller_roles
    )
    return ApiResponse(meta=meta, data=execution)


@router.get(
    "/{execution_id}/workflow-tasks", response_model=ApiResponse[list[WorkflowTaskRead]]
)
async def list_workflow_execution_tasks(
    execution_id: str,
    service: WorkflowExecutionServiceDep,
    caller: CurrentUserDep,
    caller_roles: EffectiveRolesDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[WorkflowTaskRead]]:
    """Return the WorkflowTasks belonging to the given WorkflowExecution.

    Restricted to the execution's initiator, its designated approvers,
    admins, and super admins. Raises HTTP 404 (``NotFoundError``) if the
    parent execution does not exist, so callers can distinguish "no such
    execution" from "execution exists but has no tasks".
    """
    items = await service.list_tasks(
        execution_id,
        caller=caller,
        caller_roles=caller_roles,
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.get(
    "/{execution_id}/tool-invocations",
    response_model=ApiResponse[list[MCPToolInvocation]],
)
async def list_workflow_execution_tool_invocations(
    execution_id: str,
    service: WorkflowExecutionServiceDep,
    caller: CurrentUserDep,
    caller_roles: EffectiveRolesDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[MCPToolInvocation]]:
    """Return the MCP tool-call decisions recorded for the given WorkflowExecution.

    These are the calls that reached the MCP proxy: ``allowed`` ones that went
    upstream and ``denied`` ones a policy vetoed. Calls answered by a tool mock
    never reach the proxy and are therefore absent — the chat transcript shows
    those. Arguments appear only as ``argumentsDigest``; the raw values are
    never recorded here.

    Restricted to the execution's initiator, its designated approvers, admins,
    and super admins. Raises HTTP 404 (``NotFoundError``) if the parent
    execution does not exist.
    """
    items = await service.list_tool_invocations(
        execution_id,
        caller=caller,
        caller_roles=caller_roles,
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.delete(
    "/{execution_id}",
    response_model=ApiResponse[None],
    dependencies=_requires_admin,
)
async def delete_workflow_execution(
    execution_id: str,
    service: WorkflowExecutionServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    """Delete a WorkflowExecution, its WorkflowTasks, and its workflow session.

    Restricted to admins and super admins. Raises HTTP 404 (``NotFoundError``)
    if no execution exists with the given ID.
    """
    await service.delete(execution_id)
    return ApiResponse(meta=meta, data=None)


def _content_disposition(name: str) -> str:
    """Build a ``Content-Disposition`` header value that downloads ``name`` as a file.

    Always ``attachment``: a session file's bytes are whatever a participant or
    the agent put there, and serving arbitrary uploaded content inline is how an
    upload endpoint turns into a stored-XSS vector. The name is emitted twice --
    a quoted ASCII form every client understands, and the RFC 5987 ``filename*``
    form that carries the real, possibly non-ASCII name.

    Args:
        name: The stored file name.

    Returns:
        The header value.
    """
    fallback = name.encode("ascii", "replace").decode("ascii")
    fallback = fallback.replace('"', "'").replace("\\", "_")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}"


@router.post(
    "/{execution_id}/files",
    response_model=ApiResponse[SessionFileRead],
    status_code=201,
)
async def upload_session_file(
    execution_id: str,
    file: Annotated[UploadFile, File(description="File to attach to the session")],
    service: SessionFileServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[SessionFileRead]:
    """Attach an uploaded file to this execution's workflow session.

    Restricted to the same people who may drive the run -- its initiator, its
    designated approvers, and super admins. A plain admin can read a run and
    download what it produced, but putting a new file in front of its agent is
    acting on the run, so it goes through the stricter check.

    The response carries the file's metadata, including the name it was actually
    stored under: a name already taken in the session is suffixed rather than
    overwritten.
    """
    stored = await service.upload(
        execution_id,
        filename=file.filename,
        content_type=file.content_type,
        read=file.read,
        caller=caller,
    )
    return ApiResponse(meta=meta, data=stored)


@router.get("/{execution_id}/files/{file_id}/content")
async def download_session_file(
    execution_id: str,
    file_id: str,
    service: SessionFileServiceDep,
    caller: CurrentUserDep,
    caller_roles: EffectiveRolesDep,
) -> Response:
    """Serve one of this execution's session files as a download.

    Open to everyone who may read the run's chat, which is the point: a file is
    part of the conversation, so the same people see it.

    Deliberately outside the ``ApiResponse`` envelope -- it returns the file's
    bytes, like ``GET /users/{id}/avatar``. Every file is served as a generic
    attachment rather than under its recorded type, so nothing a participant or
    the agent stored can be rendered by the browser.
    """
    stored = await service.download(
        execution_id, file_id, caller=caller, caller_roles=caller_roles
    )
    return Response(
        content=stored.data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": _content_disposition(stored.name),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get(
    "/{execution_id}/sessions", response_model=ApiResponse[list[ExecutionSession]]
)
async def list_workflow_execution_sessions(
    execution_id: str,
    service: WorkflowExecutionServiceDep,
    caller: CurrentUserDep,
    caller_roles: EffectiveRolesDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[ExecutionSession]]:
    """List the ADK sessions a run is worked in, main session first.

    Each carries its status -- running, waiting for an approval or for input,
    idle, done -- and the client-tool calls it is paused on. Read access, like
    the chat.
    """
    sessions = await service.list_sessions(
        execution_id, caller=caller, caller_roles=caller_roles
    )
    return ApiResponse(meta=meta, data=sessions)


@router.get(
    "/{execution_id}/sessions/{session_id}/messages",
    response_model=ApiResponse[SessionHistory],
)
async def get_workflow_session_messages(
    execution_id: str,
    session_id: str,
    service: WorkflowExecutionServiceDep,
    caller: CurrentUserDep,
    caller_roles: EffectiveRolesDep,
    meta: ApiMetaDep,
) -> ApiResponse[SessionHistory]:
    """Return one session's chat history and the cursor to stream what follows from.

    Restricted to the execution's initiator, its designated approvers, admins,
    and super admins. The history is keyed by the initiator, so a designated
    approver opening the chat sees their conversation rather than an empty,
    separate one. While a turn is under way the history stops where it began,
    and the turn is replayed from ``GET .../stream?after=<streamCursor>``.

    A read: a platform-scoped super_admin who has selected "All tenants"
    (``X-Tenant-Id: __all__``) can read it for an execution in any tenant -- see
    ``dependencies.auth.get_current_tenant_scope``.
    """
    history = await service.get_session_messages(
        execution_id, session_id, caller=caller, caller_roles=caller_roles
    )
    return ApiResponse(meta=meta, data=history)


@router.post(
    "/{execution_id}/sessions/{session_id}/input",
    response_model=ApiResponse[ExecutionSession],
    status_code=202,
)
async def send_workflow_session_input(
    execution_id: str,
    session_id: str,
    data: SessionInputCreate,
    service: WorkflowExecutionServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[ExecutionSession]:
    """Queue a chat message, or a form's answer, for the session's next turn.

    The turn itself runs on the server (:mod:`services.session_runner`); this
    returns as soon as the input is queued, and the turn reaches the chat
    through the session's stream. Restricted to the execution's initiator, its
    designated approvers, and super admins; answering a form the agent rendered
    is the initiator's alone. An approval is not decided here but through
    ``PATCH /approvals/{id}``, which resumes the session itself.

    409 ``SESSION_RUN_IN_PROGRESS`` when the session already has a turn queued
    or running, and 409 ``SESSION_AWAITING_APPROVAL`` for a message sent while
    it waits on an approval.
    """
    session = await service.send_input(execution_id, session_id, data, caller=caller)
    return ApiResponse(meta=meta, data=session)


@router.get("/{execution_id}/sessions/{session_id}/stream", include_in_schema=False)
async def stream_workflow_session(
    execution_id: str,
    session_id: str,
    request: Request,
    service: WorkflowExecutionServiceDep,
    caller: CurrentUserDep,
    caller_roles: EffectiveRolesDep,
    after: Annotated[int, Query(ge=0)] = 0,
) -> StreamingResponse:
    """Stream a session's AG-UI events after ``after``, until its turn ends.

    Whichever replica runs the turn, every viewer gets its events as they come;
    between turns the stream waits for the next one, sending keepalive
    comments. It ends after the turn's last event, and the client re-reads the
    history and subscribes again. Read access, like the history: a plain admin
    can watch a run without being able to drive it.
    """
    await service.authorize_stream(
        execution_id, session_id, caller=caller, caller_roles=caller_roles
    )
    return StreamingResponse(
        stream_events(
            session_id,
            after,
            open_db=lambda: AsyncSession(database.engine),
            disconnected=request.is_disconnected,
        ),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
