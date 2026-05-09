from collections.abc import AsyncGenerator

from ag_ui.core import RunAgentInput, SystemMessage
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from dependencies import ADKAgentDep

router = APIRouter()


@router.post("/agent")
async def agent_endpoint(
    input_data: RunAgentInput,
    request: Request,
    adk_agent: ADKAgentDep,
) -> StreamingResponse:
    # Exclude SystemMessage to prevent prompt injection: ag_ui_adk appends its content directly to agent instructions
    filtered = [m for m in input_data.messages if not isinstance(m, SystemMessage)]
    input_data = input_data.model_copy(update={"messages": filtered})
    encoder = EventEncoder(accept=request.headers.get("accept") or "")

    async def event_generator() -> AsyncGenerator[str, None]:
        async for event in adk_agent.run(input_data):
            yield encoder.encode(event)

    return StreamingResponse(event_generator(), media_type=encoder.get_content_type())
