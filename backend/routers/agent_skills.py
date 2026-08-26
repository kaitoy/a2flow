"""CRUD endpoints for AgentSkill resources, plus the repository pull."""

from fastapi import APIRouter, BackgroundTasks, Depends

from dependencies import (
    AgentSkillReadServiceDep,
    AgentSkillServiceDep,
    ApiMetaDep,
    CurrentUserIdDep,
    FilterDep,
    PaginationDep,
    SkillSyncJobDep,
    SortDep,
    TagFilterDep,
    WorkflowDesignServiceDep,
    WorkflowGenerationJobDep,
    require_roles,
)
from models.agent_skill import AgentSkillCreate, AgentSkillRead, AgentSkillUpdate
from models.response import ApiResponse
from models.tag import TagIdsUpdate
from models.user import Role
from models.workflow import GenerateWorkflowRequest, WorkflowRead

router = APIRouter(prefix="/agent-skills", tags=["agent-skills"])

#: Route dependency gating agent-skill writes behind the ``developer`` role.
_requires_developer = [Depends(require_roles(Role.developer))]


@router.post(
    "",
    response_model=ApiResponse[AgentSkillRead],
    status_code=201,
    dependencies=_requires_developer,
)
async def create_agent_skill(
    body: AgentSkillCreate,
    background: BackgroundTasks,
    service: AgentSkillServiceDep,
    sync_job: SkillSyncJobDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[AgentSkillRead]:
    """Register a skill and start cloning its repository in the background.

    Returns as soon as the row exists (``syncStatus: "pending"``, no
    ``commitSha``) rather than holding the request open for a network clone of
    an arbitrary repository. The clone's outcome lands on the row, which the
    admin UI polls; a repository that cannot be cloned leaves the skill
    ``failed`` with the reason, still editable and re-pullable, instead of
    losing the caller's input to an error response.
    """
    skill = await service.create(body, user_id=user_id)
    background.add_task(sync_job, skill.id, user_id=user_id)
    return ApiResponse(meta=meta, data=await service.to_read(skill))


@router.post(
    "/{skill_id}/pull",
    response_model=ApiResponse[AgentSkillRead],
    status_code=202,
    dependencies=_requires_developer,
)
async def pull_agent_skill(
    skill_id: str,
    background: BackgroundTasks,
    service: AgentSkillServiceDep,
    sync_job: SkillSyncJobDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[AgentSkillRead]:
    """Re-clone a skill's repository at its configured ref, or the default branch.

    The way a skill picks up upstream changes, and the way a failed
    registration clone is retried. Accepted and run in the background like the
    registration clone; the returned row is already marked ``pending``.

    A pull that fails leaves the skill's published revision alone, so it keeps
    running at the revision it had. A pull that succeeds publishes a new
    revision — sessions already running stay pinned to the one they started
    with, and only new runs pick the new one up.
    """
    skill = await service.mark_pending(skill_id, user_id=user_id)
    background.add_task(sync_job, skill.id, user_id=user_id)
    return ApiResponse(meta=meta, data=await service.to_read(skill))


@router.post(
    "/{skill_id}/workflows",
    response_model=ApiResponse[WorkflowRead],
    status_code=201,
    dependencies=_requires_developer,
)
async def generate_workflow(
    skill_id: str,
    body: GenerateWorkflowRequest,
    background: BackgroundTasks,
    service: WorkflowDesignServiceDep,
    generation_job: WorkflowGenerationJobDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[WorkflowRead]:
    """Generate a draft Workflow from this skill ("Generate workflow").

    Registers the workflow (``status: "generating"``) and its design session
    immediately, then breaks ``prompt`` into the workflow's task templates in a
    background agent run rather than holding the request open for an LLM
    round trip. The outcome lands on the row, which the admin UI polls:
    success leaves a ``draft`` with templates and a summarized description,
    failure leaves ``failed`` with the reason — the design chat stays usable
    to fix the task templates by hand. Requires the skill to have a published revision
    (HTTP 409 ``SKILL_NOT_READY`` otherwise).
    """
    workflow = await service.generate(skill_id, body.name, user_id=user_id)
    background.add_task(generation_job, workflow.id, body.prompt, user_id=user_id)
    return ApiResponse(meta=meta, data=await service.to_read(workflow))


@router.get("", response_model=ApiResponse[list[AgentSkillRead]])
async def list_agent_skills(
    service: AgentSkillReadServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    tags: TagFilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[AgentSkillRead]]:
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
        tag_ids=tags.tag_ids,
    )
    return ApiResponse(meta=meta, data=await service.to_read_many(items))


@router.get("/{skill_id}", response_model=ApiResponse[AgentSkillRead])
async def get_agent_skill(
    skill_id: str,
    service: AgentSkillReadServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[AgentSkillRead]:
    skill = await service.get(skill_id)
    return ApiResponse(meta=meta, data=await service.to_read(skill))


@router.patch(
    "/{skill_id}",
    response_model=ApiResponse[AgentSkillRead],
    dependencies=_requires_developer,
)
async def update_agent_skill(
    skill_id: str,
    body: AgentSkillUpdate,
    service: AgentSkillServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[AgentSkillRead]:
    skill = await service.update(skill_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=await service.to_read(skill))


@router.delete(
    "/{skill_id}",
    response_model=ApiResponse[None],
    dependencies=_requires_developer,
)
async def delete_agent_skill(
    skill_id: str,
    service: AgentSkillServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    await service.delete(skill_id)
    return ApiResponse(meta=meta, data=None)


@router.put(
    "/{skill_id}/tags",
    response_model=ApiResponse[AgentSkillRead],
    dependencies=_requires_developer,
)
async def set_agent_skill_tags(
    skill_id: str,
    body: TagIdsUpdate,
    service: AgentSkillServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[AgentSkillRead]:
    skill = await service.set_tags(skill_id, body.tag_ids)
    return ApiResponse(meta=meta, data=await service.to_read(skill))
