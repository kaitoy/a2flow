import logging
import os
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated

from ag_ui.core import RunAgentInput, SystemMessage
from ag_ui.encoder import EventEncoder
from ag_ui_adk import ADKAgent, adk_events_to_messages
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from google.adk.sessions import BaseSessionService
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from pydantic import BaseModel
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from agent import create_agent
from database import (
    AgentSkill,
    AgentSkillCreate,
    AgentSkillUpdate,
    get_session,
    init_db,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    level=logging.INFO,
)

APP_NAME = "A2Flow"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
    yield


app = FastAPI(
    title=APP_NAME,
    description="Google ADK agent with SSE streaming",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- dependency providers ----------


@lru_cache(maxsize=1)
def get_session_service() -> BaseSessionService:
    db_path = os.getenv("SESSION_DB_URL", "sqlite:///sessions.db")
    return SqliteSessionService(db_path)


@lru_cache(maxsize=1)
def get_adk_agent() -> ADKAgent:
    return ADKAgent(
        adk_agent=create_agent(),
        app_name=APP_NAME,
        user_id_extractor=lambda input: input.forwarded_props.get("userId", "user"),
        session_service=get_session_service(),
        use_thread_id_as_session_id=True,
        emit_messages_snapshot=True,
    )


SessionServiceDep = Annotated[BaseSessionService, Depends(get_session_service)]
ADKAgentDep = Annotated[ADKAgent, Depends(get_adk_agent)]
DBSessionDep = Annotated[AsyncSession, Depends(get_session)]


# ---------- request / response models ----------


class SessionCreateRequest(BaseModel):
    user_id: str
    session_id: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    last_update_time: float


# ---------- agent endpoint ----------


@app.post("/agent")
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


# ---------- session endpoints ----------


@app.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    request: SessionCreateRequest,
    session_service: SessionServiceDep,
) -> SessionResponse:
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
async def list_sessions(
    user_id: str,
    session_service: SessionServiceDep,
) -> list[SessionResponse]:
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
async def get_session_messages(
    session_id: str,
    user_id: str,
    session_service: SessionServiceDep,
) -> JSONResponse:
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
async def delete_session(
    session_id: str,
    user_id: str,
    session_service: SessionServiceDep,
) -> None:
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


# ---------- agent skill endpoints ----------


@app.post("/agent-skills", response_model=AgentSkill, status_code=201)
async def create_agent_skill(
    body: AgentSkillCreate,
    db: DBSessionDep,
) -> AgentSkill:
    skill = AgentSkill.model_validate(body.model_dump())
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return skill


@app.get("/agent-skills", response_model=list[AgentSkill])
async def list_agent_skills(
    db: DBSessionDep,
    limit: int = 20,
    offset: int = 0,
) -> list[AgentSkill]:
    result = await db.exec(
        select(AgentSkill)
        .order_by(col(AgentSkill.created_at).desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.all())


@app.get("/agent-skills/{skill_id}", response_model=AgentSkill)
async def get_agent_skill(skill_id: str, db: DBSessionDep) -> AgentSkill:
    skill = await db.get(AgentSkill, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Agent skill not found")
    return skill


@app.patch("/agent-skills/{skill_id}", response_model=AgentSkill)
async def update_agent_skill(
    skill_id: str,
    body: AgentSkillUpdate,
    db: DBSessionDep,
) -> AgentSkill:
    skill = await db.get(AgentSkill, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Agent skill not found")
    skill.sqlmodel_update(body.model_dump(exclude_unset=True))
    skill.updated_at = datetime.now(UTC)
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return skill


@app.delete("/agent-skills/{skill_id}", status_code=204)
async def delete_agent_skill(skill_id: str, db: DBSessionDep) -> None:
    skill = await db.get(AgentSkill, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Agent skill not found")
    await db.delete(skill)
    await db.commit()


# ---------- health ----------


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host=host, port=port, reload=True)
