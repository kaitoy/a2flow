from datetime import UTC, datetime

from ag_ui_adk import adk_events_to_messages
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dependencies import APP_NAME, CurrentUserIdDep, SessionServiceDep
from models.session import Session
from repositories.exceptions import NotFoundError

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[Session])
async def list_sessions(
    user_id: CurrentUserIdDep,
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
            last_update_time=datetime.fromtimestamp(s.last_update_time, tz=UTC),
        )
        for s in response.sessions
    ]


@router.get("/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    user_id: CurrentUserIdDep,
    session_service: SessionServiceDep,
) -> JSONResponse:
    """Get message history for a session."""
    session = await session_service.get_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        raise NotFoundError("Session", session_id)
    messages = adk_events_to_messages(session.events)
    return JSONResponse([m.model_dump(mode="json", by_alias=True) for m in messages])


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    user_id: CurrentUserIdDep,
    session_service: SessionServiceDep,
) -> None:
    """Delete a session."""
    session = await session_service.get_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        raise NotFoundError("Session", session_id)
    await session_service.delete_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
