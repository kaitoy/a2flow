"""Endpoints for retrieving WorkflowSession details and streaming the workflow agent."""

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack
from typing import Any

from ag_ui.core import RunAgentInput, SystemMessage
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from dependencies import (
    APP_NAME,
    ApiMetaDep,
    CurrentUserDep,
    FilterDep,
    PaginationDep,
    SortDep,
    WorkflowSessionServiceDep,
)
from infrastructure.agent import with_user_id
from infrastructure.locks import LockNotAcquiredError, advisory_lock, agent_run_key
from models.response import ApiResponse
from models.workflow_session import WorkflowSession
from models.workflow_task import WorkflowTaskRead
from repositories.exceptions import SessionRunInProgressError

router = APIRouter(prefix="/workflow-sessions", tags=["workflow-sessions"])


@router.get("", response_model=ApiResponse[list[WorkflowSession]])
async def list_workflow_sessions(
    service: WorkflowSessionServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[WorkflowSession]]:
    """Return WorkflowSession records, defaulting to ``created_at`` descending."""
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.get("/{ws_id}", response_model=ApiResponse[WorkflowSession])
async def get_workflow_session(
    ws_id: str,
    service: WorkflowSessionServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowSession]:
    """Return the WorkflowSession record for the given ID.

    Only the session owner, a designated approver of the session, or a super
    admin may access it; anyone else receives HTTP 403 (``FORBIDDEN``).
    """
    ws = await service.get(ws_id, caller=caller)
    return ApiResponse(meta=meta, data=ws)


@router.get(
    "/{ws_id}/workflow-tasks", response_model=ApiResponse[list[WorkflowTaskRead]]
)
async def list_workflow_session_tasks(
    ws_id: str,
    service: WorkflowSessionServiceDep,
    caller: CurrentUserDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[WorkflowTaskRead]]:
    """Return the WorkflowTasks belonging to the given WorkflowSession.

    Restricted to the session owner, its designated approvers, and super
    admins. Raises HTTP 404 (``NotFoundError``) if the parent session does not
    exist, so callers can distinguish "no such session" from "session exists
    but has no tasks".
    """
    items = await service.list_tasks(
        ws_id,
        caller=caller,
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.delete("/{ws_id}", response_model=ApiResponse[None])
async def delete_workflow_session(
    ws_id: str,
    service: WorkflowSessionServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    """Delete a WorkflowSession, its WorkflowTasks, and its ADK chat session.

    Restricted to the session owner and super admins (stricter than the
    shared-chat access rule). Raises HTTP 404 (``NotFoundError``) if no
    session exists with the given ID.
    """
    await service.delete(ws_id, caller=caller)
    return ApiResponse(meta=meta, data=None)


@router.post("/{ws_id}/agent", include_in_schema=False)
async def workflow_session_agent(
    ws_id: str,
    input_data: RunAgentInput,
    request: Request,
    service: WorkflowSessionServiceDep,
    caller: CurrentUserDep,
) -> StreamingResponse:
    """Stream AG-UI events from the agent bound to a specific workflow session.

    Restricted to the session owner, its designated approvers, and super
    admins. The skill and skill directory are resolved from the
    WorkflowSession record so the correct ADK tools are loaded regardless of
    the global agent state. SystemMessages are stripped to prevent prompt
    injection.

    Because the run is keyed by the session owner, the new messages are
    attributed to the actual sender (the caller) after streaming completes:
    the session's attributable keys present before the run are snapshotted
    (``"user"`` event ids and tool-response tool_call_ids -- the latter covers
    A2UI user-action acknowledgements), and any that appear afterwards are
    recorded as the current user's -- except no-op render acknowledgements,
    which merely unblock surfaces nobody acted on (see
    ``WorkflowSessionService.record_new_senders``).

    The run is serialized per ADK session by a cross-process lock, so neither two
    replicas nor two people sharing the session (owner and approver) can drive it
    at once — the second run would reason over an in-memory session the first has
    already moved past, and its messages would be misattributed. A run already in
    progress surfaces as HTTP 409, before any SSE headers go out (see
    ``infrastructure/locks.py``).
    """
    # Resolve (and authorize) before locking, so a caller with no business here
    # gets their 403/404 rather than queueing behind someone else's run.
    adk_agent, ws = await service.resolve_agent(ws_id, caller=caller)
    current_user_id = caller.id

    filtered = [m for m in input_data.messages if not isinstance(m, SystemMessage)]
    input_data = input_data.model_copy(update={"messages": filtered})
    # Key the ADK run by the WorkflowSession's owner rather than the current user
    # so every viewer (e.g. a designated approver) shares the same ADK session.
    input_data = with_user_id(input_data, ws.user_id)
    encoder = EventEncoder(accept=request.headers.get("accept") or "")

    async with AsyncExitStack() as stack:
        # Lock on the owner's id, matching how the ADK session is keyed above:
        # the owner and their approvers share one session, so two of them hitting
        # send at once is an ordinary collision here, not an edge case — and no
        # client-side "already running" guard can see across users.
        try:
            await stack.enter_async_context(
                advisory_lock(agent_run_key(APP_NAME, ws.user_id, input_data.thread_id))
            )
        except LockNotAcquiredError as exc:
            raise SessionRunInProgressError(input_data.thread_id) from exc

        # Snapshot inside the lock: this is the "before" half of a read-then-diff
        # over session state, and a concurrent run appending between the two
        # halves would misattribute its messages to this caller.
        prior_keys = await service.attributable_keys(ws_id)

        run_stack = stack.pop_all()

    async def event_generator() -> AsyncGenerator[str, None]:
        async with run_stack:
            async for event in adk_agent.run(input_data):
                yield encoder.encode(event)
            # Attribute the messages this run appended to the user who sent them.
            await service.record_new_senders(ws_id, prior_keys, current_user_id)
            # Associate each message with the workflow task in progress at the time.
            await service.record_message_tasks(ws_id)

    return StreamingResponse(event_generator(), media_type=encoder.get_content_type())


@router.get("/{ws_id}/messages", response_model=ApiResponse[list[dict[str, Any]]])
async def get_workflow_session_messages(
    ws_id: str,
    service: WorkflowSessionServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[dict[str, Any]]]:
    """Return the chat history of a WorkflowSession's ADK session.

    Restricted to the session owner, its designated approvers, and super
    admins. The history is keyed by the session's owner, so a designated
    approver opening the chat sees the owner's conversation rather than an
    empty, separate session. Returns an empty list when the ADK session has not
    been created yet. Raises HTTP 404 if the WorkflowSession does not exist.
    """
    messages = await service.get_messages(ws_id, caller=caller)
    return ApiResponse(meta=meta, data=messages)
