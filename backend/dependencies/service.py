"""Per-request service (use case) dependencies wiring repositories and singletons.

Each service is constructed from the request-scoped repositories it operates on,
plus any singletons it needs (the skill manager, the agent registry). These are
the dependencies routers inject to invoke business logic.
"""

from typing import Annotated

from fastapi import Depends

from services import (
    AgentSkillService,
    WorkflowService,
    WorkflowSessionService,
    WorkflowTaskService,
)

from .repository import (
    AgentSkillRepositoryDep,
    WorkflowRepositoryDep,
    WorkflowSessionRepositoryDep,
    WorkflowTaskRepositoryDep,
)
from .singletons import AgentRegistryDep, SkillManagerDep


def get_agent_skill_service(repo: AgentSkillRepositoryDep) -> AgentSkillService:
    """Create an AgentSkillService backed by the request's repository."""
    return AgentSkillService(repo)


AgentSkillServiceDep = Annotated[AgentSkillService, Depends(get_agent_skill_service)]


def get_workflow_service(
    workflows: WorkflowRepositoryDep,
    skills: AgentSkillRepositoryDep,
    skill_manager: SkillManagerDep,
    ws_repo: WorkflowSessionRepositoryDep,
) -> WorkflowService:
    """Create a WorkflowService wiring the repositories and SkillManager."""
    return WorkflowService(workflows, skills, skill_manager, ws_repo)


WorkflowServiceDep = Annotated[WorkflowService, Depends(get_workflow_service)]


def get_workflow_session_service(
    ws_repo: WorkflowSessionRepositoryDep,
    tasks: WorkflowTaskRepositoryDep,
    registry: AgentRegistryDep,
) -> WorkflowSessionService:
    """Create a WorkflowSessionService wiring the repositories and agent registry."""
    return WorkflowSessionService(ws_repo, tasks, registry)


WorkflowSessionServiceDep = Annotated[
    WorkflowSessionService, Depends(get_workflow_session_service)
]


def get_workflow_task_service(repo: WorkflowTaskRepositoryDep) -> WorkflowTaskService:
    """Create a WorkflowTaskService backed by the request's repository."""
    return WorkflowTaskService(repo)


WorkflowTaskServiceDep = Annotated[
    WorkflowTaskService, Depends(get_workflow_task_service)
]
