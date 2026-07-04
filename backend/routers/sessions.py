from datetime import UTC, datetime
from typing import Any

from ag_ui_adk import adk_events_to_messages
from fastapi import APIRouter

from dependencies import (
    APP_NAME,
    ApiMetaDep,
    CurrentUserIdDep,
    SessionServiceDep,
)
from infrastructure.agent import SESSION_TITLE_KEY
from models.response import ApiResponse
from models.session import Session
from repositories.exceptions import NotFoundError

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=ApiResponse[list[Session]])
async def list_sessions(
    user_id: CurrentUserIdDep,
    session_service: SessionServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[Session]]:
    """List all sessions for a user."""
    response = await session_service.list_sessions(
        app_name=APP_NAME,
        user_id=user_id,
    )
    items = [
        Session(
            id=s.id,
            user_id=s.user_id,
            last_update_time=datetime.fromtimestamp(s.last_update_time, tz=UTC),
            title=(s.state or {}).get(SESSION_TITLE_KEY),
        )
        for s in response.sessions
    ]
    return ApiResponse(meta=meta, data=items)


@router.get("/{session_id}", response_model=ApiResponse[Session])
async def get_session(
    session_id: str,
    user_id: CurrentUserIdDep,
    session_service: SessionServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[Session]:
    """Get a single session by ID."""
    session = await session_service.get_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        raise NotFoundError("Session", session_id)
    item = Session(
        id=session.id,
        user_id=session.user_id,
        last_update_time=datetime.fromtimestamp(session.last_update_time, tz=UTC),
        title=(session.state or {}).get(SESSION_TITLE_KEY),
    )
    return ApiResponse(meta=meta, data=item)


@router.get("/{session_id}/messages", response_model=ApiResponse[list[dict[str, Any]]])
async def get_session_messages(
    session_id: str,
    user_id: CurrentUserIdDep,
    session_service: SessionServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[dict[str, Any]]]:
    """Get message history for a session.

    Messages come from ``ag_ui.core.Message`` (a discriminated union of role-
    tagged variants). They are serialized to plain dicts here so OpenAPI does
    not embed the entire union signature into the response schema name.
    Clients narrow the dicts back to typed ``Message`` values themselves.
    """
    session = await session_service.get_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        raise NotFoundError("Session", session_id)
    messages = adk_events_to_messages(session.events)
    return ApiResponse(
        meta=meta,
        data=[m.model_dump(mode="json", by_alias=True) for m in messages],
    )


@router.delete("/{session_id}", response_model=ApiResponse[None])
async def delete_session(
    session_id: str,
    user_id: CurrentUserIdDep,
    session_service: SessionServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
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
    return ApiResponse(meta=meta, data=None)
