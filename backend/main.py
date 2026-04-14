import logging
import os
import uuid

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    level=logging.INFO,
)

from ag_ui_adk import ADKAgent, add_adk_fastapi_endpoint
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.adk.sessions import InMemorySessionService
from pydantic import BaseModel

from agent import create_agent

APP_NAME = "A2Flow"

app = FastAPI(title="A2Flow", description="Google ADK agent with SSE streaming")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

session_service = InMemorySessionService()

adk_agent = ADKAgent(
    adk_agent=create_agent(),
    app_name=APP_NAME,
    user_id_extractor=lambda input: input.forwarded_props.get("userId", "user"),
    session_service=session_service,
    use_thread_id_as_session_id=True,
)

add_adk_fastapi_endpoint(app, adk_agent, path="/agent")


# ---------- request / response models ----------

class SessionCreateRequest(BaseModel):
    user_id: str
    session_id: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    last_update_time: float


# ---------- session endpoints ----------

@app.get("/hoge")
async def hoge():
    """Create a new session."""
    print("#######################")
    print(adk_agent._adk_agent.instruction)
    tools = adk_agent._adk_agent.tools
    toolset = tools[0]
    tools = toolset._ui_tools
    print(tools[0].description)

    print(tools[0].name)

@app.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(request: SessionCreateRequest):
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
async def list_sessions(user_id: str):
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


@app.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, user_id: str):
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
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host=host, port=port, reload=True)
