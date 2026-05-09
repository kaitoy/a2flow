import uuid

from ag_ui_adk import adk_events_to_messages
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from dependencies import APP_NAME, SessionServiceDep
from models.session import Session, SessionCreate

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=Session, status_code=201)
async def create_session(
    request: SessionCreate,
    session_service: SessionServiceDep,
) -> Session:
    """Create a new session."""
    session_id = request.id or str(uuid.uuid4())
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=request.user_id,
        session_id=session_id,
    )
    return Session(
        id=session.id,
        user_id=session.user_id,
        last_update_time=session.last_update_time,
    )


@router.get("", response_model=list[Session])
async def list_sessions(
    user_id: str,
    session_service: SessionServiceDep,
) -> list[Session]:
    """List all sessions for a user."""
    response = await session_service.list_sessions(
        app_name=APP_NAME,
        user_id=user_id,
    )
    return [
        Session(
            id=s.id,
            user_id=s.user_id,
            last_update_time=s.last_update_time,
        )
        for s in response.sessions
    ]


@router.get("/{session_id}/messages")
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


@router.delete("/{session_id}", status_code=204)
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
