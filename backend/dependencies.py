from functools import lru_cache
from typing import Annotated

from ag_ui_adk import ADKAgent
from fastapi import Depends, Header
from google.adk.sessions import BaseSessionService
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from sqlmodel.ext.asyncio.session import AsyncSession

from agent import create_agent
from database import DB_URL, get_session
from repositories import (
    AgentSkillRepository,
    SqlAgentSkillRepository,
    SqlWorkflowRepository,
    WorkflowRepository,
)

APP_NAME = "A2Flow"


def get_current_user_id(
    x_user_id: Annotated[str | None, Header()] = None,
) -> str:
    return x_user_id or ""


CurrentUserIdDep = Annotated[str, Depends(get_current_user_id)]


@lru_cache(maxsize=1)
def get_session_service() -> BaseSessionService:
    return SqliteSessionService(DB_URL)


@lru_cache(maxsize=1)
def get_adk_agent() -> ADKAgent:
    return ADKAgent(
        adk_agent=create_agent(),
        app_name=APP_NAME,
        user_id_extractor=lambda input: input.forwarded_props.get("userId", "user"),
        session_service=get_session_service(),
        use_thread_id_as_session_id=True,
        emit_messages_snapshot=True,
    )


SessionServiceDep = Annotated[BaseSessionService, Depends(get_session_service)]
ADKAgentDep = Annotated[ADKAgent, Depends(get_adk_agent)]
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
