"""Endpoints for retrieving WorkflowSession details and streaming the workflow agent."""

from collections.abc import AsyncGenerator

from ag_ui.core import RunAgentInput, SystemMessage
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from dependencies import (
    ApiMetaDep,
    PaginationDep,
    WorkflowSessionServiceDep,
)
from models.response import ApiResponse
from models.workflow_session import WorkflowSession
from models.workflow_task import WorkflowTask

router = APIRouter(prefix="/workflow-sessions", tags=["workflow-sessions"])


@router.get("", response_model=ApiResponse[list[WorkflowSession]])
async def list_workflow_sessions(
    service: WorkflowSessionServiceDep,
    pagination: PaginationDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[WorkflowSession]]:
    """Return WorkflowSession records ordered by ``created_at`` descending."""
    items = await service.list(limit=pagination.limit, offset=pagination.offset)
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


@router.get("/{ws_id}/workflow-tasks", response_model=ApiResponse[list[WorkflowTask]])
async def list_workflow_session_tasks(
    ws_id: str,
    service: WorkflowSessionServiceDep,
    pagination: PaginationDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[WorkflowTask]]:
    """Return the WorkflowTasks belonging to the given WorkflowSession.

    Raises HTTP 404 (``NotFoundError``) if the parent session does not exist,
    so callers can distinguish "no such session" from "session exists but has
    no tasks".
    """
    items = await service.list_tasks(
        ws_id, limit=pagination.limit, offset=pagination.offset
    )
    return ApiResponse(meta=meta, data=items)


@router.post("/{ws_id}/agent", include_in_schema=False)
async def workflow_session_agent(
    ws_id: str,
    input_data: RunAgentInput,
    request: Request,
    service: WorkflowSessionServiceDep,
) -> StreamingResponse:
    """Stream AG-UI events from the agent bound to a specific workflow session.

    The skill and skill directory are resolved from the WorkflowSession record so
    the correct ADK tools are loaded regardless of the global agent state.
    SystemMessages are stripped to prevent prompt injection.
    """
    adk_agent = await service.resolve_agent(ws_id)

    filtered = [m for m in input_data.messages if not isinstance(m, SystemMessage)]
    input_data = input_data.model_copy(update={"messages": filtered})
    encoder = EventEncoder(accept=request.headers.get("accept") or "")

    async def event_generator() -> AsyncGenerator[str, None]:
        async for event in adk_agent.run(input_data):
            yield encoder.encode(event)

    return StreamingResponse(event_generator(), media_type=encoder.get_content_type())
