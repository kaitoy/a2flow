"""CRUD endpoints for AgentSkill resources, plus the repository pull."""

from fastapi import APIRouter, BackgroundTasks, Depends

from dependencies import (
    AgentSkillServiceDep,
    ApiMetaDep,
    CurrentUserIdDep,
    FilterDep,
    PaginationDep,
    SkillSyncJobDep,
    SortDep,
    require_roles,
)
from models.agent_skill import AgentSkill, AgentSkillCreate, AgentSkillUpdate
from models.response import ApiResponse
from models.user import Role

router = APIRouter(prefix="/agent-skills", tags=["agent-skills"])

#: Route dependency gating agent-skill writes behind the ``developer`` role.
_requires_developer = [Depends(require_roles(Role.developer))]


@router.post(
    "",
    response_model=ApiResponse[AgentSkill],
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
) -> ApiResponse[AgentSkill]:
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
    return ApiResponse(meta=meta, data=skill)


@router.post(
    "/{skill_id}/pull",
    response_model=ApiResponse[AgentSkill],
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
) -> ApiResponse[AgentSkill]:
    """Re-clone a skill's repository at its current remote HEAD.

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
    return ApiResponse(meta=meta, data=skill)


@router.get("", response_model=ApiResponse[list[AgentSkill]])
async def list_agent_skills(
    service: AgentSkillServiceDep,
    pagination: PaginationDep,
    sort: SortDep,
    filters: FilterDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[AgentSkill]]:
    items = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        sort=sort.sort,
        filters=filters.filters,
    )
    return ApiResponse(meta=meta, data=items)


@router.get("/{skill_id}", response_model=ApiResponse[AgentSkill])
async def get_agent_skill(
    skill_id: str,
    service: AgentSkillServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[AgentSkill]:
    skill = await service.get(skill_id)
    return ApiResponse(meta=meta, data=skill)


@router.patch(
    "/{skill_id}",
    response_model=ApiResponse[AgentSkill],
    dependencies=_requires_developer,
)
async def update_agent_skill(
    skill_id: str,
    body: AgentSkillUpdate,
    service: AgentSkillServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[AgentSkill]:
    skill = await service.update(skill_id, body, user_id=user_id)
    return ApiResponse(meta=meta, data=skill)


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
