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
    ApprovalRepository,
    AuthSessionRepository,
    MCPServerRepository,
    MessageMetaRepository,
    NotificationRepository,
    SecretRepository,
    SqlAgentSkillRepository,
    SqlApprovalRepository,
    SqlAuthSessionRepository,
    SqlMCPServerRepository,
    SqlMessageMetaRepository,
    SqlNotificationRepository,
    SqlSecretRepository,
    SqlUserAvatarRepository,
    SqlUserRepository,
    SqlWorkflowRepository,
    SqlWorkflowSessionRepository,
    SqlWorkflowTaskRepository,
    UserAvatarRepository,
    UserRepository,
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


def get_auth_session_repository(db: DBSessionDep) -> AuthSessionRepository:
    """Create an AuthSessionRepository backed by the current database session."""
    return SqlAuthSessionRepository(db)


AuthSessionRepositoryDep = Annotated[
    AuthSessionRepository, Depends(get_auth_session_repository)
]


def get_mcp_server_repository(db: DBSessionDep) -> MCPServerRepository:
    """Create an MCPServerRepository backed by the current database session."""
    return SqlMCPServerRepository(db)


MCPServerRepositoryDep = Annotated[
    MCPServerRepository, Depends(get_mcp_server_repository)
]


def get_notification_repository(db: DBSessionDep) -> NotificationRepository:
    """Create a NotificationRepository backed by the current database session."""
    return SqlNotificationRepository(db)


NotificationRepositoryDep = Annotated[
    NotificationRepository, Depends(get_notification_repository)
]


def get_secret_repository(db: DBSessionDep) -> SecretRepository:
    """Create a SecretRepository backed by the current database session."""
    return SqlSecretRepository(db)


SecretRepositoryDep = Annotated[SecretRepository, Depends(get_secret_repository)]


def get_user_repository(db: DBSessionDep) -> UserRepository:
    """Create a UserRepository backed by the current database session."""
    return SqlUserRepository(db)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]


def get_user_avatar_repository(db: DBSessionDep) -> UserAvatarRepository:
    """Create a UserAvatarRepository backed by the current database session."""
    return SqlUserAvatarRepository(db)


UserAvatarRepositoryDep = Annotated[
    UserAvatarRepository, Depends(get_user_avatar_repository)
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


def get_message_meta_repository(db: DBSessionDep) -> MessageMetaRepository:
    """Create a MessageMetaRepository backed by the current database session."""
    return SqlMessageMetaRepository(db)


MessageMetaRepositoryDep = Annotated[
    MessageMetaRepository, Depends(get_message_meta_repository)
]


def get_workflow_task_repository(
    db: DBSessionDep,
    ws_repo: WorkflowSessionRepositoryDep,
    mcp_repo: MCPServerRepositoryDep,
) -> WorkflowTaskRepository:
    """Create a WorkflowTaskRepository backed by the current database session.

    The injected WorkflowSessionRepository is used to validate that the parent
    session exists when creating tasks; the MCPServerRepository validates the
    servers referenced by tool bindings.
    """
    return SqlWorkflowTaskRepository(db, ws_repo, mcp_repo)


WorkflowTaskRepositoryDep = Annotated[
    WorkflowTaskRepository, Depends(get_workflow_task_repository)
]


def get_approval_repository(
    db: DBSessionDep,
    ws_repo: WorkflowSessionRepositoryDep,
) -> ApprovalRepository:
    """Create an ApprovalRepository backed by the current database session.

    The injected WorkflowSessionRepository is used to validate that the parent
    session exists when creating an approval.
    """
    return SqlApprovalRepository(db, ws_repo)


ApprovalRepositoryDep = Annotated[ApprovalRepository, Depends(get_approval_repository)]
