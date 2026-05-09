from fastapi import APIRouter, HTTPException

from dependencies import CurrentUserIdDep, WorkflowRepositoryDep
from models.workflow import Workflow, WorkflowCreate, WorkflowUpdate
from repositories.exceptions import ForeignKeyViolationError, NotFoundError

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("", response_model=Workflow, status_code=201)
async def create_workflow(
    body: WorkflowCreate,
    repo: WorkflowRepositoryDep,
    user_id: CurrentUserIdDep,
) -> Workflow:
    try:
        return await repo.create(body, user_id=user_id)
    except ForeignKeyViolationError as e:
        raise HTTPException(
            status_code=422, detail=f"AgentSkill {e.id!r} not found"
        ) from e


@router.get("", response_model=list[Workflow])
async def list_workflows(
    repo: WorkflowRepositoryDep,
    limit: int = 20,
    offset: int = 0,
) -> list[Workflow]:
    return await repo.list(limit=limit, offset=offset)


@router.get("/{workflow_id}", response_model=Workflow)
async def get_workflow(workflow_id: str, repo: WorkflowRepositoryDep) -> Workflow:
    workflow = await repo.get(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.patch("/{workflow_id}", response_model=Workflow)
async def update_workflow(
    workflow_id: str,
    body: WorkflowUpdate,
    repo: WorkflowRepositoryDep,
    user_id: CurrentUserIdDep,
) -> Workflow:
    try:
        return await repo.update(workflow_id, body, user_id=user_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail="Workflow not found") from e
    except ForeignKeyViolationError as e:
        raise HTTPException(
            status_code=422, detail=f"AgentSkill {e.id!r} not found"
        ) from e


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: str, repo: WorkflowRepositoryDep) -> None:
    try:
        await repo.delete(workflow_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail="Workflow not found") from e
