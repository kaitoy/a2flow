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
    PlanningSessionRepository,
    SecretRepository,
    SqlAgentSkillRepository,
    SqlApprovalRepository,
    SqlAuthSessionRepository,
    SqlMCPServerRepository,
    SqlMessageMetaRepository,
    SqlNotificationRepository,
    SqlPlanningSessionRepository,
    SqlSecretRepository,
    SqlTenantRepository,
    SqlUserAvatarRepository,
    SqlUserRepository,
    SqlWorkflowRepository,
    SqlWorkflowSessionRepository,
    SqlWorkflowTaskRepository,
    SqlWorkflowTaskTemplateRepository,
    TenantRepository,
    UserAvatarRepository,
    UserRepository,
    WorkflowRepository,
    WorkflowSessionRepository,
    WorkflowTaskRepository,
    WorkflowTaskTemplateRepository,
)

from .auth import CurrentTenantIdDep

DBSessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_agent_skill_repository(
    db: DBSessionDep, tenant_id: CurrentTenantIdDep
) -> AgentSkillRepository:
    """Create an AgentSkillRepository backed by the current database session."""
    return SqlAgentSkillRepository(db, tenant_id=tenant_id)


AgentSkillRepositoryDep = Annotated[
    AgentSkillRepository, Depends(get_agent_skill_repository)
]


def get_auth_session_repository(db: DBSessionDep) -> AuthSessionRepository:
    """Create an AuthSessionRepository backed by the current database session."""
    return SqlAuthSessionRepository(db)


AuthSessionRepositoryDep = Annotated[
    AuthSessionRepository, Depends(get_auth_session_repository)
]


def get_mcp_server_repository(
    db: DBSessionDep, tenant_id: CurrentTenantIdDep
) -> MCPServerRepository:
    """Create an MCPServerRepository backed by the current database session."""
    return SqlMCPServerRepository(db, tenant_id=tenant_id)


MCPServerRepositoryDep = Annotated[
    MCPServerRepository, Depends(get_mcp_server_repository)
]


def get_notification_repository(
    db: DBSessionDep, tenant_id: CurrentTenantIdDep
) -> NotificationRepository:
    """Create a NotificationRepository backed by the current database session."""
    return SqlNotificationRepository(db, tenant_id=tenant_id)


NotificationRepositoryDep = Annotated[
    NotificationRepository, Depends(get_notification_repository)
]


def get_secret_repository(
    db: DBSessionDep, tenant_id: CurrentTenantIdDep
) -> SecretRepository:
    """Create a SecretRepository backed by the current database session."""
    return SqlSecretRepository(db, tenant_id=tenant_id)


SecretRepositoryDep = Annotated[SecretRepository, Depends(get_secret_repository)]


def get_tenant_repository(db: DBSessionDep) -> TenantRepository:
    """Create a TenantRepository backed by the current database session.

    Not tenant-scoped: ``Tenant`` is the tenant root itself (see
    "Tenant Isolation" in ``.claude/rules/backend-patterns.md``).
    """
    return SqlTenantRepository(db)


TenantRepositoryDep = Annotated[TenantRepository, Depends(get_tenant_repository)]


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
    tenant_id: CurrentTenantIdDep,
) -> WorkflowRepository:
    """Create a WorkflowRepository backed by the current database session."""
    return SqlWorkflowRepository(db, skills, tenant_id=tenant_id)


WorkflowRepositoryDep = Annotated[WorkflowRepository, Depends(get_workflow_repository)]


def get_workflow_session_repository(
    db: DBSessionDep, tenant_id: CurrentTenantIdDep
) -> WorkflowSessionRepository:
    """Create a WorkflowSessionRepository backed by the current database session."""
    return SqlWorkflowSessionRepository(db, tenant_id=tenant_id)


WorkflowSessionRepositoryDep = Annotated[
    WorkflowSessionRepository, Depends(get_workflow_session_repository)
]


def get_message_meta_repository(
    db: DBSessionDep, tenant_id: CurrentTenantIdDep
) -> MessageMetaRepository:
    """Create a MessageMetaRepository backed by the current database session."""
    return SqlMessageMetaRepository(db, tenant_id=tenant_id)


MessageMetaRepositoryDep = Annotated[
    MessageMetaRepository, Depends(get_message_meta_repository)
]


def get_workflow_task_repository(
    db: DBSessionDep,
    ws_repo: WorkflowSessionRepositoryDep,
    mcp_repo: MCPServerRepositoryDep,
    tenant_id: CurrentTenantIdDep,
) -> WorkflowTaskRepository:
    """Create a WorkflowTaskRepository backed by the current database session.

    The injected WorkflowSessionRepository is used to validate that the parent
    session exists when creating tasks; the MCPServerRepository validates the
    servers referenced by tool bindings.
    """
    return SqlWorkflowTaskRepository(db, ws_repo, mcp_repo, tenant_id=tenant_id)


WorkflowTaskRepositoryDep = Annotated[
    WorkflowTaskRepository, Depends(get_workflow_task_repository)
]


def get_workflow_task_template_repository(
    db: DBSessionDep,
    workflows: WorkflowRepositoryDep,
    mcp_repo: MCPServerRepositoryDep,
    tenant_id: CurrentTenantIdDep,
) -> WorkflowTaskTemplateRepository:
    """Create a WorkflowTaskTemplateRepository backed by the current database session.

    The injected WorkflowRepository is used to validate that the parent
    workflow exists when creating templates; the MCPServerRepository validates
    the servers referenced by tool bindings.
    """
    return SqlWorkflowTaskTemplateRepository(
        db, workflows, mcp_repo, tenant_id=tenant_id
    )


WorkflowTaskTemplateRepositoryDep = Annotated[
    WorkflowTaskTemplateRepository, Depends(get_workflow_task_template_repository)
]


def get_planning_session_repository(
    db: DBSessionDep, tenant_id: CurrentTenantIdDep
) -> PlanningSessionRepository:
    """Create a PlanningSessionRepository backed by the current database session."""
    return SqlPlanningSessionRepository(db, tenant_id=tenant_id)


PlanningSessionRepositoryDep = Annotated[
    PlanningSessionRepository, Depends(get_planning_session_repository)
]


def get_approval_repository(
    db: DBSessionDep,
    ws_repo: WorkflowSessionRepositoryDep,
    tenant_id: CurrentTenantIdDep,
) -> ApprovalRepository:
    """Create an ApprovalRepository backed by the current database session.

    The injected WorkflowSessionRepository is used to validate that the parent
    session exists when creating an approval.
    """
    return SqlApprovalRepository(db, ws_repo, tenant_id=tenant_id)


ApprovalRepositoryDep = Annotated[ApprovalRepository, Depends(get_approval_repository)]
