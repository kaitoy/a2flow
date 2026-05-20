from collections.abc import AsyncGenerator
from pathlib import Path

from ag_ui.core import RunAgentInput, SystemMessage
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from agent import AGENT_SKILL_ID_KEY, SKILL_DIR_KEY
from dependencies import APP_NAME, AgentRegistryDep, SessionServiceDep

router = APIRouter()


@router.post("/agent", include_in_schema=False)
async def agent_endpoint(
    input_data: RunAgentInput,
    request: Request,
    registry: AgentRegistryDep,
    session_service: SessionServiceDep,
) -> StreamingResponse:
    # Exclude SystemMessage to prevent prompt injection: ag_ui_adk appends its content directly to agent instructions
    filtered = [m for m in input_data.messages if not isinstance(m, SystemMessage)]
    input_data = input_data.model_copy(update={"messages": filtered})
    encoder = EventEncoder(accept=request.headers.get("accept") or "")

    user_id = input_data.forwarded_props.get("userId", "user")
    session = await session_service.get_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=input_data.thread_id,
    )
    skill_id: str | None = None
    skill_dir: Path | None = None
    if session is not None:
        state = session.state or {}
        raw_skill_id = state.get(AGENT_SKILL_ID_KEY)
        raw_skill_dir = state.get(SKILL_DIR_KEY)
        if raw_skill_id:
            skill_id = str(raw_skill_id)
        if raw_skill_dir:
            skill_dir = Path(str(raw_skill_dir))
    adk_agent = registry.get(skill_id, skill_dir)

    async def event_generator() -> AsyncGenerator[str, None]:
        async for event in adk_agent.run(input_data):
            yield encoder.encode(event)

    return StreamingResponse(event_generator(), media_type=encoder.get_content_type())
