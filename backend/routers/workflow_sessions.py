"""Endpoints for retrieving WorkflowSession details and streaming the workflow agent."""

from collections.abc import AsyncGenerator
from pathlib import Path

from ag_ui.core import RunAgentInput, SystemMessage
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from dependencies import AgentRegistryDep, WorkflowSessionRepositoryDep
from models.workflow_session import WorkflowSession
from repositories.exceptions import NotFoundError

router = APIRouter(prefix="/workflow-sessions", tags=["workflow-sessions"])


@router.get("/{ws_id}", response_model=WorkflowSession)
async def get_workflow_session(
    ws_id: str,
    ws_repo: WorkflowSessionRepositoryDep,
) -> WorkflowSession:
    """Return the WorkflowSession record for the given ID."""
    ws = await ws_repo.get(ws_id)
    if ws is None:
        raise NotFoundError("WorkflowSession", ws_id)
    return ws


@router.post("/{ws_id}/agent", include_in_schema=False)
async def workflow_session_agent(
    ws_id: str,
    input_data: RunAgentInput,
    request: Request,
    ws_repo: WorkflowSessionRepositoryDep,
    registry: AgentRegistryDep,
) -> StreamingResponse:
    """Stream AG-UI events from the agent bound to a specific workflow session.

    The skill and skill directory are resolved from the WorkflowSession record so
    the correct ADK tools are loaded regardless of the global agent state.
    SystemMessages are stripped to prevent prompt injection.
    """
    ws = await ws_repo.get(ws_id)
    if ws is None:
        raise NotFoundError("WorkflowSession", ws_id)

    filtered = [m for m in input_data.messages if not isinstance(m, SystemMessage)]
    input_data = input_data.model_copy(update={"messages": filtered})
    encoder = EventEncoder(accept=request.headers.get("accept") or "")

    skill_dir = Path(ws.skill_dir)
    adk_agent = registry.get(ws.agent_skill_id, skill_dir)

    async def event_generator() -> AsyncGenerator[str, None]:
        async for event in adk_agent.run(input_data):
            yield encoder.encode(event)

    return StreamingResponse(event_generator(), media_type=encoder.get_content_type())
