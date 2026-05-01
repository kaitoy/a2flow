import logging
import os
import uuid
from collections.abc import AsyncGenerator

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    level=logging.INFO,
)

from ag_ui.core import RunAgentInput, SystemMessage  # noqa: E402
from ag_ui.encoder import EventEncoder  # noqa: E402
from ag_ui_adk import ADKAgent, adk_events_to_messages  # noqa: E402
from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from agent import create_agent  # noqa: E402

APP_NAME = "A2Flow"

app = FastAPI(title="A2Flow", description="Google ADK agent with SSE streaming")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

session_service = InMemorySessionService()  # type: ignore[no-untyped-call]

adk_agent = ADKAgent(
    adk_agent=create_agent(),
    app_name=APP_NAME,
    user_id_extractor=lambda input: input.forwarded_props.get("userId", "user"),
    session_service=session_service,
    use_thread_id_as_session_id=True,
    emit_messages_snapshot=True,
)


@app.post("/agent")
async def agent_endpoint(
    input_data: RunAgentInput, request: Request
) -> StreamingResponse:
    # Exclude SystemMessage to prevent prompt injection: ag_ui_adk appends its content directly to agent instructions
    filtered = [m for m in input_data.messages if not isinstance(m, SystemMessage)]
    input_data = input_data.model_copy(update={"messages": filtered})
    encoder = EventEncoder(accept=request.headers.get("accept") or "")

    async def event_generator() -> AsyncGenerator[str, None]:
        async for event in adk_agent.run(input_data):
            yield encoder.encode(event)

    return StreamingResponse(event_generator(), media_type=encoder.get_content_type())


# ---------- request / response models ----------


class SessionCreateRequest(BaseModel):
    user_id: str
    session_id: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    last_update_time: float


# ---------- session endpoints ----------


@app.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(request: SessionCreateRequest) -> SessionResponse:
    """Create a new session."""
    session_id = request.session_id or str(uuid.uuid4())
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=request.user_id,
        session_id=session_id,
    )
    return SessionResponse(
        session_id=session.id,
        user_id=session.user_id,
        last_update_time=session.last_update_time,
    )


@app.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(user_id: str) -> list[SessionResponse]:
    """List all sessions for a user."""
    response = await session_service.list_sessions(
        app_name=APP_NAME,
        user_id=user_id,
    )
    return [
        SessionResponse(
            session_id=s.id,
            user_id=s.user_id,
            last_update_time=s.last_update_time,
        )
        for s in response.sessions
    ]


@app.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, user_id: str) -> JSONResponse:
    """Get message history for a session."""
    session = await session_service.get_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = adk_events_to_messages(session.events)
    return JSONResponse([m.model_dump(mode="json", by_alias=True) for m in messages])


@app.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, user_id: str) -> None:
    """Delete a session."""
    session = await session_service.get_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await session_service.delete_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )


# ---------- health ----------


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host=host, port=port, reload=True)
