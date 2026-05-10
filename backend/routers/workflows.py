from fastapi import APIRouter

from dependencies import CurrentUserIdDep, PaginationDep, WorkflowRepositoryDep
from models.workflow import Workflow, WorkflowCreate, WorkflowUpdate
from repositories.exceptions import NotFoundError

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("", response_model=Workflow, status_code=201)
async def create_workflow(
    body: WorkflowCreate,
    repo: WorkflowRepositoryDep,
    user_id: CurrentUserIdDep,
) -> Workflow:
    return await repo.create(body, user_id=user_id)


@router.get("", response_model=list[Workflow])
async def list_workflows(
    repo: WorkflowRepositoryDep,
    pagination: PaginationDep,
) -> list[Workflow]:
    return await repo.list(limit=pagination.limit, offset=pagination.offset)


@router.get("/{workflow_id}", response_model=Workflow)
async def get_workflow(workflow_id: str, repo: WorkflowRepositoryDep) -> Workflow:
    workflow = await repo.get(workflow_id)
    if workflow is None:
        raise NotFoundError("Workflow", workflow_id)
    return workflow


@router.patch("/{workflow_id}", response_model=Workflow)
async def update_workflow(
    workflow_id: str,
    body: WorkflowUpdate,
    repo: WorkflowRepositoryDep,
    user_id: CurrentUserIdDep,
) -> Workflow:
    return await repo.update(workflow_id, body, user_id=user_id)


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str, repo: WorkflowRepositoryDep) -> None:
    await repo.delete(workflow_id)
