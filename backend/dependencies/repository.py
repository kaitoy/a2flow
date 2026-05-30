"""Per-request repository dependencies backed by the database session.

Wires each repository to the request-scoped ``AsyncSession``. Repositories that
enforce foreign-key relationships receive the repositories they validate against
as further dependencies (e.g. workflows depend on agent skills).
"""

from typing import Annotated

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.database import get_session
from repositories import (
    AgentSkillRepository,
    SqlAgentSkillRepository,
    SqlWorkflowRepository,
    SqlWorkflowSessionRepository,
    SqlWorkflowTaskRepository,
    WorkflowRepository,
    WorkflowSessionRepository,
    WorkflowTaskRepository,
)

DBSessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_agent_skill_repository(db: DBSessionDep) -> AgentSkillRepository:
    """Create an AgentSkillRepository backed by the current database session."""
    return SqlAgentSkillRepository(db)


AgentSkillRepositoryDep = Annotated[
    AgentSkillRepository, Depends(get_agent_skill_repository)
]


def get_workflow_repository(
    db: DBSessionDep,
    skills: AgentSkillRepositoryDep,
) -> WorkflowRepository:
    """Create a WorkflowRepository backed by the current database session."""
    return SqlWorkflowRepository(db, skills)


WorkflowRepositoryDep = Annotated[WorkflowRepository, Depends(get_workflow_repository)]


def get_workflow_session_repository(db: DBSessionDep) -> WorkflowSessionRepository:
    """Create a WorkflowSessionRepository backed by the current database session."""
    return SqlWorkflowSessionRepository(db)


WorkflowSessionRepositoryDep = Annotated[
    WorkflowSessionRepository, Depends(get_workflow_session_repository)
]


def get_workflow_task_repository(
    db: DBSessionDep,
    ws_repo: WorkflowSessionRepositoryDep,
) -> WorkflowTaskRepository:
    """Create a WorkflowTaskRepository backed by the current database session.

    The injected WorkflowSessionRepository is used to validate that the parent
    session exists when creating tasks.
    """
    return SqlWorkflowTaskRepository(db, ws_repo)


WorkflowTaskRepositoryDep = Annotated[
    WorkflowTaskRepository, Depends(get_workflow_task_repository)
]
