import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Header, Query
from google.adk.sessions import BaseSessionService
from sqlmodel.ext.asyncio.session import AsyncSession

from agent import AgentRegistry
from database import DB_URL, get_session
from repositories import (
    AgentSkillRepository,
    SqlAgentSkillRepository,
    SqlWorkflowRepository,
    SqlWorkflowSessionRepository,
    WorkflowRepository,
    WorkflowSessionRepository,
)
from services import SkillManager
from session_service import StaleTolerantSqliteSessionService

APP_NAME = "A2Flow"


@dataclass
class PaginationParams:
    limit: int = Query(default=20, ge=1, le=1000)
    offset: int = Query(default=0, ge=0)


PaginationDep = Annotated[PaginationParams, Depends(PaginationParams)]


def get_current_user_id(
    x_user_id: Annotated[str | None, Header()] = None,
) -> str:
    return x_user_id or ""


CurrentUserIdDep = Annotated[str, Depends(get_current_user_id)]


@lru_cache(maxsize=1)
def get_session_service() -> BaseSessionService:
    return StaleTolerantSqliteSessionService(DB_URL)


@lru_cache(maxsize=1)
def get_agent_registry() -> AgentRegistry:
    return AgentRegistry(
        session_service=get_session_service(),
        app_name=APP_NAME,
    )


@lru_cache(maxsize=1)
def get_skill_manager() -> SkillManager:
    cache_dir = Path(
        os.getenv(
            "SKILLS_CACHE_DIR",
            str(Path(__file__).parent / ".skills_cache"),
        )
    )
    return SkillManager(cache_dir=cache_dir)


SessionServiceDep = Annotated[BaseSessionService, Depends(get_session_service)]
AgentRegistryDep = Annotated[AgentRegistry, Depends(get_agent_registry)]
SkillManagerDep = Annotated[SkillManager, Depends(get_skill_manager)]
DBSessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_agent_skill_repository(db: DBSessionDep) -> AgentSkillRepository:
    return SqlAgentSkillRepository(db)


AgentSkillRepositoryDep = Annotated[
    AgentSkillRepository, Depends(get_agent_skill_repository)
]


def get_workflow_repository(
    db: DBSessionDep,
    skills: AgentSkillRepositoryDep,
) -> WorkflowRepository:
    return SqlWorkflowRepository(db, skills)


WorkflowRepositoryDep = Annotated[WorkflowRepository, Depends(get_workflow_repository)]


def get_workflow_session_repository(db: DBSessionDep) -> WorkflowSessionRepository:
    return SqlWorkflowSessionRepository(db)


WorkflowSessionRepositoryDep = Annotated[
    WorkflowSessionRepository, Depends(get_workflow_session_repository)
]
