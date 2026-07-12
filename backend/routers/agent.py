"""General-purpose agent streaming endpoint that serves AG-UI events over SSE."""

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack

from ag_ui.core import RunAgentInput, SystemMessage
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from dependencies import APP_NAME, AgentRegistryDep, CurrentUserIdDep, SessionServiceDep
from infrastructure.agent import (
    SESSION_TITLE_KEY,
    derive_session_title,
    first_user_message_text,
    with_user_id,
)
from infrastructure.locks import LockNotAcquiredError, advisory_lock, agent_run_key
from repositories.exceptions import SessionRunInProgressError

router = APIRouter()


@router.post("/agent", include_in_schema=False)
async def agent_endpoint(
    input_data: RunAgentInput,
    request: Request,
    registry: AgentRegistryDep,
    session_service: SessionServiceDep,
    user_id: CurrentUserIdDep,
) -> StreamingResponse:
    """Stream AG-UI events from the ADK agent for the given thread.

    SystemMessages are stripped from the input to prevent prompt injection
    (ag_ui_adk appends their content directly to agent instructions).

    This is the general-purpose chat endpoint and always runs the default
    skill-less agent. Skill-backed runs go through
    ``POST /workflow-sessions/{ws_id}/agent``, which resolves the skill and its
    pinned revision from the WorkflowSession record.

    The whole run is serialized per ADK session by a cross-process lock, so a
    horizontally scaled deployment never has two replicas driving one session at
    once — the second would spend its run reasoning over an in-memory session the
    first has already moved past (see ``infrastructure/locks.py``). A run already
    in progress for this thread surfaces as HTTP 409, before any SSE headers go
    out.
    """
    # Exclude SystemMessage to prevent prompt injection: ag_ui_adk appends its content directly to agent instructions
    filtered = [m for m in input_data.messages if not isinstance(m, SystemMessage)]
    input_data = input_data.model_copy(update={"messages": filtered})
    encoder = EventEncoder(accept=request.headers.get("accept") or "")

    async with AsyncExitStack() as stack:
        try:
            await stack.enter_async_context(
                advisory_lock(agent_run_key(APP_NAME, user_id, input_data.thread_id))
            )
        except LockNotAcquiredError as exc:
            raise SessionRunInProgressError(input_data.thread_id) from exc

        session = await session_service.get_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=input_data.thread_id,
        )
        if session is None:
            first_text = first_user_message_text(filtered)
            title = derive_session_title(first_text) if first_text is not None else None
            if title is not None:
                await session_service.create_session(
                    app_name=APP_NAME,
                    user_id=user_id,
                    session_id=input_data.thread_id,
                    state={SESSION_TITLE_KEY: title},
                )
        adk_agent = registry.get(None, None, None)

        # Override forwarded_props.userId with the trusted X-User-Id header so the
        # agent run is keyed by the same user the skill lookup above resolved.
        input_data = with_user_id(input_data, user_id)

        # The run outlives this handler, so the lock has to as well: pop_all()
        # hands its release to the generator below, leaving the `async with` here
        # to unwind empty. Until that hand-off the stack still owns the lock, so
        # anything that raises above releases it instead of stranding the session.
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
