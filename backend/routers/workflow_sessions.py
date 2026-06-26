"""Endpoints for retrieving WorkflowSession details and streaming the workflow agent."""

from collections.abc import AsyncGenerator
from typing import Any

from ag_ui.core import RunAgentInput, SystemMessage
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from dependencies import (
    ApiMetaDep,
    CurrentUserIdDep,
    FilterDep,
    PaginationDep,
    SortDep,
    WorkflowSessionServiceDep,
)
from infrastructure.agent import with_user_id
from models.response import ApiResponse
from models.workflow_session import WorkflowSession
from models.workflow_task import WorkflowTaskRead

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
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowSession]:
    """Return the WorkflowSession record for the given ID."""
    ws = await service.get(ws_id)
    return ApiResponse(meta=meta, data=ws)


@router.get(
    "/{ws_id}/workflow-tasks", response_model=ApiResponse[list[WorkflowTaskRead]]
)
async def list_workflow_session_tasks(
    ws_id: str,
    service: WorkflowSessionServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[WorkflowTaskRead]]:
    """Return the WorkflowTasks belonging to the given WorkflowSession.

    Raises HTTP 404 (``NotFoundError``) if the parent session does not exist,
    so callers can distinguish "no such session" from "session exists but has
    no tasks".
    """
    items = await service.list_tasks(
        ws_id,
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
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    """Delete a WorkflowSession, its WorkflowTasks, and its ADK chat session.

    Raises HTTP 404 (``NotFoundError``) if no session exists with the given ID.
    """
    await service.delete(ws_id)
    return ApiResponse(meta=meta, data=None)


@router.post("/{ws_id}/agent", include_in_schema=False)
async def workflow_session_agent(
    ws_id: str,
    input_data: RunAgentInput,
    request: Request,
    service: WorkflowSessionServiceDep,
    current_user_id: CurrentUserIdDep,
) -> StreamingResponse:
    """Stream AG-UI events from the agent bound to a specific workflow session.

    The skill and skill directory are resolved from the WorkflowSession record so
    the correct ADK tools are loaded regardless of the global agent state.
    SystemMessages are stripped to prevent prompt injection.

    Because the run is keyed by the session owner, the new user messages are
    attributed to the actual sender (``current_user_id``) after streaming
    completes: the ``"user"`` events present before the run are snapshotted, and
    any that appear afterwards are recorded as the current user's.
    """
    adk_agent, ws = await service.resolve_agent(ws_id)
    prior_user_event_ids = await service.user_event_ids(ws_id)

    filtered = [m for m in input_data.messages if not isinstance(m, SystemMessage)]
    input_data = input_data.model_copy(update={"messages": filtered})
    # Key the ADK run by the WorkflowSession's owner rather than the current user
    # so every viewer (e.g. a designated approver) shares the same ADK session.
    input_data = with_user_id(input_data, ws.user_id)
    encoder = EventEncoder(accept=request.headers.get("accept") or "")

    async def event_generator() -> AsyncGenerator[str, None]:
        async for event in adk_agent.run(input_data):
            yield encoder.encode(event)
        # Attribute the messages this run appended to the user who sent them.
        await service.record_new_senders(ws_id, prior_user_event_ids, current_user_id)

    return StreamingResponse(event_generator(), media_type=encoder.get_content_type())


@router.get("/{ws_id}/messages", response_model=ApiResponse[list[dict[str, Any]]])
async def get_workflow_session_messages(
    ws_id: str,
    service: WorkflowSessionServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[dict[str, Any]]]:
    """Return the chat history of a WorkflowSession's ADK session.

    The history is keyed by the session's owner, so a designated approver (or any
    other viewer) opening the chat sees the owner's conversation rather than an
    empty, separate session. Returns an empty list when the ADK session has not
    been created yet. Raises HTTP 404 if the WorkflowSession does not exist.
    """
    messages = await service.get_messages(ws_id)
    return ApiResponse(meta=meta, data=messages)
