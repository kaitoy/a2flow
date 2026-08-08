"""Endpoints for WorkflowExecution records and for their workflow sessions.

A WorkflowExecution is one run of a published workflow: the snapshot of the
workflow and skill it started against, plus the WorkflowTasks it works through.
The *workflow session* is the LLM chat that run happens in — the ADK session
named by ``WorkflowExecution.session_id``. It has no table of its own, so it is
identified by its execution and served from this router's ``/messages`` and
``/agent`` sub-resources — the same pair ``routers/workflows.py`` uses to serve
a workflow's design session, the design-time counterpart.
"""

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack
from typing import Any

import anyio
from ag_ui.core import Context, RunAgentInput, SystemMessage
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from dependencies import (
    APP_NAME,
    ApiMetaDep,
    CurrentUserDep,
    FilterDep,
    PaginationDep,
    SortDep,
    WorkflowExecutionServiceDep,
)
from infrastructure.agent import keep_a2ui_context, tenant_app_name, with_user_id
from infrastructure.locks import LockNotAcquiredError, advisory_lock, agent_run_key
from models.response import ApiResponse
from models.workflow_execution import WorkflowExecution
from models.workflow_task import WorkflowTaskRead
from repositories.exceptions import SessionRunInProgressError

router = APIRouter(prefix="/workflow-executions", tags=["workflow-executions"])


@router.get("", response_model=ApiResponse[list[WorkflowExecution]])
async def list_workflow_executions(
    service: WorkflowExecutionServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[WorkflowExecution]]:
    """Return WorkflowExecution records, defaulting to ``created_at`` descending."""
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.get("/{execution_id}", response_model=ApiResponse[WorkflowExecution])
async def get_workflow_execution(
    execution_id: str,
    service: WorkflowExecutionServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowExecution]:
    """Return the WorkflowExecution record for the given ID.

    Only the execution's initiator, a designated approver of the execution, or
    a super admin may access it; anyone else receives HTTP 403 (``FORBIDDEN``).
    """
    execution = await service.get(execution_id, caller=caller)
    return ApiResponse(meta=meta, data=execution)


@router.get(
    "/{execution_id}/workflow-tasks", response_model=ApiResponse[list[WorkflowTaskRead]]
)
async def list_workflow_execution_tasks(
    execution_id: str,
    service: WorkflowExecutionServiceDep,
    caller: CurrentUserDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[WorkflowTaskRead]]:
    """Return the WorkflowTasks belonging to the given WorkflowExecution.

    Restricted to the execution's initiator, its designated approvers, and
    super admins. Raises HTTP 404 (``NotFoundError``) if the parent execution
    does not exist, so callers can distinguish "no such execution" from
    "execution exists but has no tasks".
    """
    items = await service.list_tasks(
        execution_id,
        caller=caller,
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.delete("/{execution_id}", response_model=ApiResponse[None])
async def delete_workflow_execution(
    execution_id: str,
    service: WorkflowExecutionServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    """Delete a WorkflowExecution, its WorkflowTasks, and its workflow session.

    Restricted to the execution's initiator and super admins (stricter than the
    shared-chat access rule). Raises HTTP 404 (``NotFoundError``) if no
    execution exists with the given ID.
    """
    await service.delete(execution_id, caller=caller)
    return ApiResponse(meta=meta, data=None)


@router.post("/{execution_id}/agent", include_in_schema=False)
async def workflow_session_agent(
    execution_id: str,
    input_data: RunAgentInput,
    request: Request,
    service: WorkflowExecutionServiceDep,
    caller: CurrentUserDep,
) -> StreamingResponse:
    """Stream AG-UI events from the agent driving an execution's workflow session.

    Restricted to the execution's initiator, its designated approvers, and
    super admins. The skill and skill directory are resolved from the
    WorkflowExecution record so the correct ADK tools are loaded regardless of
    the global agent state. SystemMessages are stripped to prevent prompt
    injection.

    Because the run is keyed by the execution's initiator, the new messages are
    attributed to the actual sender (the caller) once the run ends: the
    session's attributable keys present before the run are snapshotted
    (``"user"`` event ids and tool-response tool_call_ids -- the latter covers
    A2UI user-action acknowledgements), and any that appear afterwards are
    recorded as the current user's -- except no-op render acknowledgements,
    which merely unblock surfaces nobody acted on (see
    ``WorkflowExecutionService.record_new_senders``). "Ends" includes ending
    badly: a run the client abandoned mid-stream has still appended its
    messages, so the attribution runs on the cancellation path too, shielded
    from it.

    The run is serialized per ADK session by a cross-process lock, so neither two
    replicas nor two people sharing the session (owner and approver) can drive it
    at once — the second run would reason over an in-memory session the first has
    already moved past, and its messages would be misattributed. A run already in
    progress surfaces as HTTP 409, before any SSE headers go out (see
    ``infrastructure/locks.py``).
    """
    # Resolve (and authorize) before locking, so a caller with no business here
    # gets their 403/404 rather than queueing behind someone else's run.
    adk_agent, execution = await service.resolve_agent(execution_id, caller=caller)
    current_user_id = caller.id

    filtered = [m for m in input_data.messages if not isinstance(m, SystemMessage)]
    # The context feeds the system instruction (via CONTEXT_STATE_KEY), so the
    # client-sent one is stripped to the A2UI entries the frontend middleware
    # injects — the LLM has no other source for the component catalog or the
    # render_a2ui argument format — and the workflow description is prepended
    # from the server-trusted record rather than taken from the client.
    context = keep_a2ui_context(input_data.context or [])
    if execution.description:
        context.insert(
            0,
            Context(description="Workflow description", value=execution.description),
        )
    input_data = input_data.model_copy(
        update={"messages": filtered, "context": context}
    )
    # Key the ADK run by the WorkflowExecution's owner rather than the current user
    # so every viewer (e.g. a designated approver) shares the same ADK session.
    input_data = with_user_id(
        input_data, execution.initiator_id, acting_user_id=caller.id
    )
    encoder = EventEncoder(accept=request.headers.get("accept") or "")

    async with AsyncExitStack() as stack:
        # Lock on the owner's id, matching how the ADK session is keyed above:
        # the owner and their approvers share one session, so two of them hitting
        # send at once is an ordinary collision here, not an edge case — and no
        # client-side "already running" guard can see across users.
        try:
            await stack.enter_async_context(
                advisory_lock(
                    agent_run_key(
                        tenant_app_name(APP_NAME, execution.tenant_id),
                        execution.initiator_id,
                        input_data.thread_id,
                    )
                )
            )
        except LockNotAcquiredError as exc:
            raise SessionRunInProgressError(input_data.thread_id) from exc

        # Snapshot inside the lock: this is the "before" half of a read-then-diff
        # over session state, and a concurrent run appending between the two
        # halves would misattribute its messages to this caller.
        prior_keys = await service.attributable_keys(execution_id)

        run_stack = stack.pop_all()

    async def event_generator() -> AsyncGenerator[str, None]:
        async with run_stack:
            try:
                async for event in adk_agent.run(input_data):
                    yield encoder.encode(event)
            finally:
                # A client that goes away mid-stream (tab closed, page reloaded)
                # makes Starlette cancel this generator wherever it is suspended
                # -- usually inside the run itself. Whatever the run already
                # appended to the shared ADK session stays there, so the
                # bookkeeping has to happen on the way out too, or an abandoned
                # run's messages end up attributed to nobody. It also has to be
                # shielded: without that, the cancellation unwinding us would
                # abort it at its first await, which is the same silent loss.
                with anyio.CancelScope(shield=True):
                    # Attribute the messages this run appended to the user who
                    # sent them. Still inside the run lock -- this is the "after"
                    # half of the read-then-diff the snapshot above opened.
                    await service.record_new_senders(
                        execution_id, prior_keys, current_user_id
                    )
                    # Associate each message with the workflow task in progress
                    # at the time.
                    await service.record_message_tasks(execution_id)

    return StreamingResponse(
        event_generator(),
        media_type=encoder.get_content_type(),
        headers={"X-Accel-Buffering": "no"},
    )


@router.get(
    "/{execution_id}/messages", response_model=ApiResponse[list[dict[str, Any]]]
)
async def get_workflow_session_messages(
    execution_id: str,
    service: WorkflowExecutionServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[dict[str, Any]]]:
    """Return the chat history of a WorkflowExecution's workflow session.

    Restricted to the execution's initiator, its designated approvers, and
    super admins. The history is keyed by the initiator, so a designated
    approver opening the chat sees their conversation rather than an empty,
    separate session. Returns an empty list when the ADK session has not been
    created yet. Raises HTTP 404 if the WorkflowExecution does not exist.
    """
    messages = await service.get_messages(execution_id, caller=caller)
    return ApiResponse(meta=meta, data=messages)
