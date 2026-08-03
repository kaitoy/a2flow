"""Endpoints for DesignSession details and streaming the design agent.

A design session is the chat in which a workflow's task templates are
produced and refined. It is created together with its workflow by
``POST /agent-skills/{skill_id}/workflows`` and looked up from the workflow via
``GET /workflows/{workflow_id}/design-session``; this router serves the chat
itself. Only the session owner (and super admins) may use it — design has no
approver sharing, so there is no sender-attribution bookkeeping either.
"""

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack
from typing import Any

from ag_ui.core import RunAgentInput, SystemMessage
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from dependencies import (
    APP_NAME,
    ApiMetaDep,
    CurrentUserDep,
    DesignSessionServiceDep,
)
from infrastructure.agent import tenant_app_name, with_user_id
from infrastructure.locks import LockNotAcquiredError, advisory_lock, agent_run_key
from models.design_session import DesignSession
from models.response import ApiResponse
from repositories.exceptions import SessionRunInProgressError

router = APIRouter(prefix="/design-sessions", tags=["design-sessions"])


@router.get("/{ds_id}", response_model=ApiResponse[DesignSession])
async def get_design_session(
    ds_id: str,
    service: DesignSessionServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[DesignSession]:
    """Return the DesignSession record for the given ID.

    Only the session owner or a super admin may access it; anyone else
    receives HTTP 403 (``FORBIDDEN``).
    """
    ds = await service.get(ds_id, caller=caller)
    return ApiResponse(meta=meta, data=ds)


@router.get("/{ds_id}/messages", response_model=ApiResponse[list[dict[str, Any]]])
async def get_design_session_messages(
    ds_id: str,
    service: DesignSessionServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[dict[str, Any]]]:
    """Return the chat history of a DesignSession's ADK session.

    Restricted to the session owner and super admins. Returns an empty list
    when the ADK session has not been created yet (the background generation
    run has not started). Raises HTTP 404 if the DesignSession does not
    exist.
    """
    messages = await service.get_messages(ds_id, caller=caller)
    return ApiResponse(meta=meta, data=messages)


@router.post("/{ds_id}/agent", include_in_schema=False)
async def design_session_agent(
    ds_id: str,
    input_data: RunAgentInput,
    request: Request,
    service: DesignSessionServiceDep,
    caller: CurrentUserDep,
) -> StreamingResponse:
    """Stream AG-UI events from the design agent bound to a design session.

    Restricted to the session owner and super admins. The skill directory is
    resolved from the DesignSession record (pinned revision) and the agent
    runs with the interactive design instruction and toolset, editing the
    workflow's task templates. SystemMessages are stripped to prevent prompt
    injection, and the run is keyed by the session owner so a super admin
    continuing the chat shares the same ADK session.

    The run is serialized per ADK session by the same cross-process lock the
    workflow-session endpoint uses; it also excludes the background generation
    run, so reopening the chat while generation is still in flight surfaces as
    HTTP 409 instead of corrupting the session.
    """
    adk_agent, ds = await service.resolve_agent(ds_id, caller=caller)

    filtered = [m for m in input_data.messages if not isinstance(m, SystemMessage)]
    input_data = input_data.model_copy(update={"messages": filtered})
    input_data = with_user_id(input_data, ds.user_id)
    encoder = EventEncoder(accept=request.headers.get("accept") or "")

    async with AsyncExitStack() as stack:
        try:
            await stack.enter_async_context(
                advisory_lock(
                    agent_run_key(
                        tenant_app_name(APP_NAME, ds.tenant_id),
                        ds.user_id,
                        input_data.thread_id,
                    )
                )
            )
        except LockNotAcquiredError as exc:
            raise SessionRunInProgressError(input_data.thread_id) from exc
        run_stack = stack.pop_all()

    async def event_generator() -> AsyncGenerator[str, None]:
        async with run_stack:
            async for event in adk_agent.run(input_data):
                yield encoder.encode(event)

    return StreamingResponse(
        event_generator(),
        media_type=encoder.get_content_type(),
        headers={"X-Accel-Buffering": "no"},
    )
