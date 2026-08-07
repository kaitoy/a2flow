"""Endpoints for Workflow resources and for their design sessions.

Workflows are not created here — they are born from
``POST /agent-skills/{skill_id}/workflows`` ("Generate workflow", see
``routers/agent_skills.py``), which registers a draft and generates its task
templates in the background. This router covers everything after that:
inspecting a workflow and its templates, editing name/description, publishing
it, deactivating it back to draft, and executing it.

The *design session* is the LLM chat a workflow's task templates are produced
and refined in — the ADK session named by ``Workflow.session_id``. It has no
table of its own, so it is identified by its workflow and served from this
router's ``/messages`` and ``/agent`` sub-resources, mirroring
``routers/workflow_executions.py``. Only the session owner
(``Workflow.created_by``) and super admins may use it — design has no approver
sharing, so there is no sender-attribution bookkeeping either.
"""

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack
from typing import Any

from ag_ui.core import RunAgentInput, SystemMessage
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from dependencies import (
    APP_NAME,
    ApiMetaDep,
    CurrentUserDep,
    CurrentUserIdDep,
    FilterDep,
    PaginationDep,
    SortDep,
    WorkflowDesignServiceDep,
    WorkflowServiceDep,
    WorkflowTaskTemplateServiceDep,
    require_roles,
)
from infrastructure.agent import tenant_app_name, with_user_id
from infrastructure.locks import LockNotAcquiredError, advisory_lock, agent_run_key
from models.response import ApiResponse
from models.user import Role
from models.workflow import Workflow, WorkflowUpdate
from models.workflow_execution import WorkflowExecution
from models.workflow_task_template import WorkflowTaskTemplateRead
from repositories.exceptions import SessionRunInProgressError

router = APIRouter(prefix="/workflows", tags=["workflows"])

#: Route dependency gating workflow writes behind the ``developer`` role.
_requires_developer = [Depends(require_roles(Role.developer))]

#: Route dependency gating workflow execution behind the ``requester`` or
#: ``developer`` role. ``developer`` (and, via the ``super_admin`` bypass,
#: ``super_admin``) additionally unlocks executing ``draft`` workflows — see
#: ``WorkflowService.execute``.
_requires_execute = [Depends(require_roles(Role.requester, Role.developer))]


@router.get("", response_model=ApiResponse[list[Workflow]])
async def list_workflows(
    service: WorkflowServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[Workflow]]:
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.get("/{workflow_id}", response_model=ApiResponse[Workflow])
async def get_workflow(
    workflow_id: str,
    service: WorkflowServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[Workflow]:
    workflow = await service.get(workflow_id)
    return ApiResponse(meta=meta, data=workflow)


@router.get(
    "/{workflow_id}/task-templates",
    response_model=ApiResponse[list[WorkflowTaskTemplateRead]],
)
async def list_workflow_task_templates(
    workflow_id: str,
    service: WorkflowTaskTemplateServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[WorkflowTaskTemplateRead]]:
    """Return the task templates belonging to the given Workflow.

    Raises HTTP 404 (``NotFoundError``) if the workflow does not exist, so
    callers can distinguish "no such workflow" from "workflow has no
    templates".
    """
    items = await service.list_for_workflow(
        workflow_id,
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.get("/{workflow_id}/messages", response_model=ApiResponse[list[dict[str, Any]]])
async def get_design_session_messages(
    workflow_id: str,
    service: WorkflowServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[dict[str, Any]]]:
    """Return the chat history of a Workflow's design session.

    Restricted to the session owner (the workflow's ``createdBy``) and super
    admins. Returns an empty list when the ADK session has not been created yet
    (the background generation run has not started). Raises HTTP 404 if the
    workflow does not exist.
    """
    messages = await service.get_messages(workflow_id, caller=caller)
    return ApiResponse(meta=meta, data=messages)


@router.post("/{workflow_id}/agent", include_in_schema=False)
async def design_session_agent(
    workflow_id: str,
    input_data: RunAgentInput,
    request: Request,
    service: WorkflowServiceDep,
    caller: CurrentUserDep,
) -> StreamingResponse:
    """Stream AG-UI events from the agent driving a Workflow's design session.

    Restricted to the session owner and super admins. The skill directory is
    resolved from the Workflow record (pinned revision) and the agent runs with
    the interactive design instruction and toolset, editing the workflow's task
    templates. SystemMessages are stripped to prevent prompt injection, and the
    run is keyed by the session owner so a super admin continuing the chat
    shares the same ADK session.

    The run is serialized per ADK session by the same cross-process lock the
    workflow-execution endpoint uses; it also excludes the background generation
    run, so reopening the chat while generation is still in flight surfaces as
    HTTP 409 instead of corrupting the session.
    """
    adk_agent, workflow = await service.resolve_agent(workflow_id, caller=caller)

    filtered = [m for m in input_data.messages if not isinstance(m, SystemMessage)]
    input_data = input_data.model_copy(update={"messages": filtered})
    input_data = with_user_id(input_data, workflow.created_by)
    encoder = EventEncoder(accept=request.headers.get("accept") or "")

    async with AsyncExitStack() as stack:
        try:
            await stack.enter_async_context(
                advisory_lock(
                    agent_run_key(
                        tenant_app_name(APP_NAME, workflow.tenant_id),
                        workflow.created_by,
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


@router.patch(
    "/{workflow_id}",
    response_model=ApiResponse[Workflow],
    dependencies=_requires_developer,
)
async def update_workflow(
    workflow_id: str,
    body: WorkflowUpdate,
    service: WorkflowServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[Workflow]:
    """Apply a partial update to a Workflow.

    Changing ``generated_description`` is restricted to a ``super_admin``
    (HTTP 403 ``FORBIDDEN`` otherwise); every other field stays open to any
    caller who reaches this route.
    """
    workflow = await service.update(workflow_id, body, caller=caller)
    return ApiResponse(meta=meta, data=workflow)


@router.delete(
    "/{workflow_id}",
    response_model=ApiResponse[None],
    dependencies=_requires_developer,
)
async def delete_workflow(
    workflow_id: str,
    service: WorkflowServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    await service.delete(workflow_id)
    return ApiResponse(meta=meta, data=None)


@router.post(
    "/{workflow_id}/publish",
    response_model=ApiResponse[Workflow],
    dependencies=_requires_developer,
)
async def publish_workflow(
    workflow_id: str,
    service: WorkflowDesignServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[Workflow]:
    """Publish a workflow, making it executable.

    Freezes the current design into the workflow's published snapshot. Raises
    HTTP 409 (``WORKFLOW_NOT_RUNNABLE``) while generation is in flight, when
    the workflow has no task templates, or when it is already ``published``
    and therefore has no changes to promote.
    """
    workflow = await service.publish(workflow_id, user_id=user_id)
    return ApiResponse(meta=meta, data=workflow)


@router.post(
    "/{workflow_id}/generate-description",
    response_model=ApiResponse[Workflow],
    dependencies=_requires_developer,
)
async def generate_workflow_description(
    workflow_id: str,
    service: WorkflowDesignServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[Workflow]:
    """Summarize the workflow's design conversation into its description.

    Overwrites the workflow's AI-generated description and returns the updated
    workflow; a ``published`` workflow becomes ``modified``. Raises HTTP 409
    (``WORKFLOW_DESCRIPTION_NOT_GENERATABLE``) while generation is in flight or
    when there is no design conversation to summarize, and HTTP 502
    (``SUMMARIZATION_FAILED``) when the summarizer call fails.
    """
    workflow = await service.generate_description(workflow_id, user_id=user_id)
    return ApiResponse(meta=meta, data=workflow)


@router.post(
    "/{workflow_id}/discard-changes",
    response_model=ApiResponse[Workflow],
    dependencies=_requires_developer,
)
async def discard_workflow_changes(
    workflow_id: str,
    service: WorkflowServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[Workflow]:
    """Drop a modified workflow's edits, restoring its last published version.

    Rewrites the task templates from the snapshot taken at publish time and
    returns the workflow to ``published``. Raises HTTP 409
    (``WORKFLOW_NOT_MODIFIED``) when the workflow has no unpublished changes.
    """
    workflow = await service.discard_changes(workflow_id, user_id=user_id)
    return ApiResponse(meta=meta, data=workflow)


@router.post(
    "/{workflow_id}/deactivate",
    response_model=ApiResponse[Workflow],
    dependencies=_requires_developer,
)
async def deactivate_workflow(
    workflow_id: str,
    service: WorkflowServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[Workflow]:
    """Deactivate a workflow, returning it to draft.

    Raises HTTP 409 (``WORKFLOW_NOT_DEACTIVATABLE``) unless the workflow is
    currently ``published`` or ``modified``.
    """
    workflow = await service.deactivate(workflow_id, user_id=user_id)
    return ApiResponse(meta=meta, data=workflow)


@router.post(
    "/{workflow_id}/execute",
    response_model=ApiResponse[WorkflowExecution],
    status_code=201,
    dependencies=_requires_execute,
)
async def execute_workflow(
    workflow_id: str,
    service: WorkflowServiceDep,
    caller: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowExecution]:
    """Create a WorkflowExecution pre-filled with the workflow's task templates.

    ``published`` workflows can be executed by any caller who reaches this
    route. ``draft`` workflows can additionally be executed, but only by a
    caller holding the ``developer`` role (or ``super_admin``), for
    pre-publish testing (HTTP 409 ``WORKFLOW_NOT_RUNNABLE`` otherwise). The ADK
    session is created lazily on the first agent call, which starts executing
    immediately.
    """
    execution = await service.execute(workflow_id, caller=caller)
    return ApiResponse(meta=meta, data=execution)
