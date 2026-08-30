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
    ApprovalCertificateRepository,
    ApprovalRepository,
    AuthSessionRepository,
    EffectiveRoleRepository,
    ImpersonationEventRepository,
    McpCertificateAuthorityRepository,
    MCPServerRepository,
    McpToolInvocationRepository,
    MCPToolMockRepository,
    MessageMetaRepository,
    MetricsRepository,
    NotificationRepository,
    OutboundEmailRepository,
    SecretRepository,
    SqlAgentSkillRepository,
    SqlApprovalCertificateRepository,
    SqlApprovalRepository,
    SqlAuthSessionRepository,
    SqlEffectiveRoleRepository,
    SqlImpersonationEventRepository,
    SqlMcpCertificateAuthorityRepository,
    SqlMCPServerRepository,
    SqlMcpToolInvocationRepository,
    SqlMcpToolMockRepository,
    SqlMessageMetaRepository,
    SqlMetricsRepository,
    SqlNotificationRepository,
    SqlOutboundEmailRepository,
    SqlSecretRepository,
    SqlSystemSettingsRepository,
    SqlTagRepository,
    SqlTenantRepository,
    SqlUserAvatarRepository,
    SqlUserGroupRepository,
    SqlUserRepository,
    SqlWorkflowExecutionRepository,
    SqlWorkflowPublishedVersionRepository,
    SqlWorkflowRepository,
    SqlWorkflowTaskRepository,
    SqlWorkflowTaskTemplateRepository,
    SystemSettingsRepository,
    TagRepository,
    TenantRepository,
    UserAvatarRepository,
    UserGroupRepository,
    UserRepository,
    WorkflowExecutionRepository,
    WorkflowPublishedVersionRepository,
    WorkflowRepository,
    WorkflowTaskRepository,
    WorkflowTaskTemplateRepository,
)

from .auth import CurrentTenantIdDep, CurrentTenantScopeDep

DBSessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_agent_skill_repository(
    db: DBSessionDep, tenant_id: CurrentTenantIdDep
) -> AgentSkillRepository:
    """Create an AgentSkillRepository backed by the current database session."""
    return SqlAgentSkillRepository(db, tenant_id=tenant_id)


AgentSkillRepositoryDep = Annotated[
    AgentSkillRepository, Depends(get_agent_skill_repository)
]


def get_agent_skill_read_repository(
    db: DBSessionDep, tenant_id: CurrentTenantScopeDep
) -> AgentSkillRepository:
    """Create an AgentSkillRepository for a read route, possibly across all tenants.

    Backs only ``GET`` routes (list/get); every write route stays on
    :func:`get_agent_skill_repository`, so a mutation can never run with
    ``tenant_id=None``.
    """
    return SqlAgentSkillRepository(db, tenant_id=tenant_id)


AgentSkillReadRepositoryDep = Annotated[
    AgentSkillRepository, Depends(get_agent_skill_read_repository)
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


def get_mcp_server_read_repository(
    db: DBSessionDep, tenant_id: CurrentTenantScopeDep
) -> MCPServerRepository:
    """Create an MCPServerRepository for a read route, possibly across all tenants.

    Backs only ``GET`` routes; every write route stays on
    :func:`get_mcp_server_repository`.
    """
    return SqlMCPServerRepository(db, tenant_id=tenant_id)


MCPServerReadRepositoryDep = Annotated[
    MCPServerRepository, Depends(get_mcp_server_read_repository)
]


def get_mcp_tool_mock_repository(
    db: DBSessionDep,
    servers: MCPServerRepositoryDep,
    tenant_id: CurrentTenantIdDep,
) -> MCPToolMockRepository:
    """Create an MCPToolMockRepository backed by the current database session."""
    return SqlMcpToolMockRepository(db, servers, tenant_id=tenant_id)


MCPToolMockRepositoryDep = Annotated[
    MCPToolMockRepository, Depends(get_mcp_tool_mock_repository)
]


def get_mcp_tool_mock_read_repository(
    db: DBSessionDep,
    servers: MCPServerReadRepositoryDep,
    tenant_id: CurrentTenantScopeDep,
) -> MCPToolMockRepository:
    """Create an MCPToolMockRepository for a read route, possibly across all tenants.

    Backs only ``GET`` routes; every write route stays on
    :func:`get_mcp_tool_mock_repository`.
    """
    return SqlMcpToolMockRepository(db, servers, tenant_id=tenant_id)


MCPToolMockReadRepositoryDep = Annotated[
    MCPToolMockRepository, Depends(get_mcp_tool_mock_read_repository)
]


def get_impersonation_event_read_repository(
    db: DBSessionDep, tenant_id: CurrentTenantScopeDep
) -> ImpersonationEventRepository:
    """Create an ImpersonationEventRepository for the audit read routes.

    The write half of this repository (used by the impersonation flow in
    ``dependencies/auth.py``) is constructed with the session alone: the table
    has no ``tenant_id``, and scoping applies only to the reads, which narrow by
    the impersonated user's tenant. See :mod:`repositories.impersonation_event`.
    """
    return SqlImpersonationEventRepository(db, tenant_id=tenant_id)


ImpersonationEventReadRepositoryDep = Annotated[
    ImpersonationEventRepository, Depends(get_impersonation_event_read_repository)
]


def get_mcp_tool_invocation_repository(
    db: DBSessionDep, tenant_id: CurrentTenantIdDep
) -> McpToolInvocationRepository:
    """Create an McpToolInvocationRepository backed by the current database session."""
    return SqlMcpToolInvocationRepository(db, tenant_id=tenant_id)


McpToolInvocationRepositoryDep = Annotated[
    McpToolInvocationRepository, Depends(get_mcp_tool_invocation_repository)
]


def get_mcp_tool_invocation_read_repository(
    db: DBSessionDep, tenant_id: CurrentTenantScopeDep
) -> McpToolInvocationRepository:
    """Create an McpToolInvocationRepository for a read route, possibly across all tenants."""
    return SqlMcpToolInvocationRepository(db, tenant_id=tenant_id)


McpToolInvocationReadRepositoryDep = Annotated[
    McpToolInvocationRepository, Depends(get_mcp_tool_invocation_read_repository)
]


def get_metrics_repository(
    db: DBSessionDep, tenant_id: CurrentTenantIdDep
) -> MetricsRepository:
    """Create a MetricsRepository backed by the current database session."""
    return SqlMetricsRepository(db, tenant_id=tenant_id)


MetricsRepositoryDep = Annotated[MetricsRepository, Depends(get_metrics_repository)]


def get_notification_repository(
    db: DBSessionDep, tenant_id: CurrentTenantIdDep
) -> NotificationRepository:
    """Create a NotificationRepository backed by the current database session."""
    return SqlNotificationRepository(db, tenant_id=tenant_id)


NotificationRepositoryDep = Annotated[
    NotificationRepository, Depends(get_notification_repository)
]


def get_notification_read_repository(
    db: DBSessionDep, tenant_id: CurrentTenantScopeDep
) -> NotificationRepository:
    """Create a NotificationRepository for a read route, possibly across all tenants."""
    return SqlNotificationRepository(db, tenant_id=tenant_id)


NotificationReadRepositoryDep = Annotated[
    NotificationRepository, Depends(get_notification_read_repository)
]


def get_outbound_email_repository(
    db: DBSessionDep, tenant_id: CurrentTenantIdDep
) -> OutboundEmailRepository:
    """Create an OutboundEmailRepository backed by the current database session."""
    return SqlOutboundEmailRepository(db, tenant_id=tenant_id)


OutboundEmailRepositoryDep = Annotated[
    OutboundEmailRepository, Depends(get_outbound_email_repository)
]


def get_outbound_email_read_repository(
    db: DBSessionDep, tenant_id: CurrentTenantScopeDep
) -> OutboundEmailRepository:
    """Create an OutboundEmailRepository for a read route, possibly across all tenants.

    Backs the ``/outbound-emails`` list/get routes (``delete`` stays on
    :func:`get_outbound_email_repository`), and also lets a read
    ``NotificationDispatcher`` (a collaborator of write-oriented services with
    a read variant, e.g. ``WorkflowTaskService``) be constructed without
    resolving the strict, all-tenants-incompatible dependency.
    """
    return SqlOutboundEmailRepository(db, tenant_id=tenant_id)


OutboundEmailReadRepositoryDep = Annotated[
    OutboundEmailRepository, Depends(get_outbound_email_read_repository)
]


def get_approval_certificate_repository(
    db: DBSessionDep, tenant_id: CurrentTenantIdDep
) -> ApprovalCertificateRepository:
    """Create an ApprovalCertificateRepository backed by the current session."""
    return SqlApprovalCertificateRepository(db, tenant_id=tenant_id)


ApprovalCertificateRepositoryDep = Annotated[
    ApprovalCertificateRepository, Depends(get_approval_certificate_repository)
]


def get_approval_certificate_read_repository(
    db: DBSessionDep, tenant_id: CurrentTenantScopeDep
) -> ApprovalCertificateRepository:
    """Create an ApprovalCertificateRepository for a read route, possibly across all tenants."""
    return SqlApprovalCertificateRepository(db, tenant_id=tenant_id)


ApprovalCertificateReadRepositoryDep = Annotated[
    ApprovalCertificateRepository, Depends(get_approval_certificate_read_repository)
]


def get_mcp_certificate_authority_repository(
    db: DBSessionDep,
) -> McpCertificateAuthorityRepository:
    """Create an McpCertificateAuthorityRepository backed by the current session.

    Not tenant-scoped: one root CA signs for the whole platform (see
    :mod:`models.mcp_ca` for why a per-tenant root would add key material
    without adding a boundary).
    """
    return SqlMcpCertificateAuthorityRepository(db)


McpCertificateAuthorityRepositoryDep = Annotated[
    McpCertificateAuthorityRepository, Depends(get_mcp_certificate_authority_repository)
]


def get_secret_repository(
    db: DBSessionDep, tenant_id: CurrentTenantIdDep
) -> SecretRepository:
    """Create a SecretRepository backed by the current database session."""
    return SqlSecretRepository(db, tenant_id=tenant_id)


SecretRepositoryDep = Annotated[SecretRepository, Depends(get_secret_repository)]


def get_secret_read_repository(
    db: DBSessionDep, tenant_id: CurrentTenantScopeDep
) -> SecretRepository:
    """Create a SecretRepository for a read route, possibly across all tenants.

    Backs only ``GET`` routes; every write route stays on
    :func:`get_secret_repository`. Also the collaborator any other read
    repository must use in place of :data:`SecretRepositoryDep` when it needs
    Secret only for FK/lookup checks -- see the module docstring pattern in
    ``dependencies.repository``.
    """
    return SqlSecretRepository(db, tenant_id=tenant_id)


SecretReadRepositoryDep = Annotated[
    SecretRepository, Depends(get_secret_read_repository)
]


def get_system_settings_repository(db: DBSessionDep) -> SystemSettingsRepository:
    """Create a SystemSettingsRepository backed by the current database session.

    Not tenant-scoped: the settings apply to the whole platform, and only a
    ``super_admin`` — who carries no ``tenant_id`` — may reach them (see
    "Tenant Isolation" in ``.claude/rules/backend-patterns.md``). Pulling in
    ``CurrentTenantIdDep`` here would make every route 403 for exactly the
    callers they exist for.
    """
    return SqlSystemSettingsRepository(db)


SystemSettingsRepositoryDep = Annotated[
    SystemSettingsRepository, Depends(get_system_settings_repository)
]


def get_tag_repository(
    db: DBSessionDep, tenant_id: CurrentTenantIdDep
) -> TagRepository:
    """Create a TagRepository backed by the current database session."""
    return SqlTagRepository(db, tenant_id=tenant_id)


TagRepositoryDep = Annotated[TagRepository, Depends(get_tag_repository)]


def get_tag_read_repository(
    db: DBSessionDep, tenant_id: CurrentTenantScopeDep
) -> TagRepository:
    """Create a TagRepository for a read route, possibly across all tenants."""
    return SqlTagRepository(db, tenant_id=tenant_id)


TagReadRepositoryDep = Annotated[TagRepository, Depends(get_tag_read_repository)]


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


def get_user_group_repository(
    db: DBSessionDep, users: UserRepositoryDep, tenant_id: CurrentTenantIdDep
) -> UserGroupRepository:
    """Create a UserGroupRepository backed by the current database session."""
    return SqlUserGroupRepository(db, users, tenant_id=tenant_id)


UserGroupRepositoryDep = Annotated[
    UserGroupRepository, Depends(get_user_group_repository)
]


def get_user_group_read_repository(
    db: DBSessionDep, users: UserRepositoryDep, tenant_id: CurrentTenantScopeDep
) -> UserGroupRepository:
    """Create a UserGroupRepository for a read route, possibly across all tenants.

    ``users`` is reused as-is (not a "read" variant): ``SqlUserRepository``
    takes no ``tenant_id`` at all, so resolving it never depends on
    ``CurrentTenantIdDep`` and can never raise in all-tenants mode.
    """
    return SqlUserGroupRepository(db, users, tenant_id=tenant_id)


UserGroupReadRepositoryDep = Annotated[
    UserGroupRepository, Depends(get_user_group_read_repository)
]


def get_effective_role_repository(db: DBSessionDep) -> EffectiveRoleRepository:
    """Create an EffectiveRoleRepository backed by the current database session.

    Takes no ``tenant_id``: resolving a user's inherited roles has to work for
    a platform-scoped caller who has selected no tenant, and memberships are
    already tenant-validated when they are written — see
    :mod:`repositories.effective_roles`.
    """
    return SqlEffectiveRoleRepository(db)


EffectiveRoleRepositoryDep = Annotated[
    EffectiveRoleRepository, Depends(get_effective_role_repository)
]


def get_workflow_repository(
    db: DBSessionDep,
    skills: AgentSkillRepositoryDep,
    tenant_id: CurrentTenantIdDep,
) -> WorkflowRepository:
    """Create a WorkflowRepository backed by the current database session."""
    return SqlWorkflowRepository(db, skills, tenant_id=tenant_id)


WorkflowRepositoryDep = Annotated[WorkflowRepository, Depends(get_workflow_repository)]


def get_workflow_read_repository(
    db: DBSessionDep,
    skills: AgentSkillReadRepositoryDep,
    tenant_id: CurrentTenantScopeDep,
) -> WorkflowRepository:
    """Create a WorkflowRepository for a read route, possibly across all tenants.

    ``skills`` must be the read repository: merely resolving the strict
    ``AgentSkillRepositoryDep`` would itself raise in all-tenants mode.
    """
    return SqlWorkflowRepository(db, skills, tenant_id=tenant_id)


WorkflowReadRepositoryDep = Annotated[
    WorkflowRepository, Depends(get_workflow_read_repository)
]


def get_workflow_published_version_repository(
    db: DBSessionDep, tenant_id: CurrentTenantIdDep
) -> WorkflowPublishedVersionRepository:
    """Create a WorkflowPublishedVersionRepository backed by the current database session."""
    return SqlWorkflowPublishedVersionRepository(db, tenant_id=tenant_id)


WorkflowPublishedVersionRepositoryDep = Annotated[
    WorkflowPublishedVersionRepository,
    Depends(get_workflow_published_version_repository),
]


def get_workflow_published_version_read_repository(
    db: DBSessionDep, tenant_id: CurrentTenantScopeDep
) -> WorkflowPublishedVersionRepository:
    """Create a WorkflowPublishedVersionRepository for a read route.

    Not exposed through any route of its own -- exists only so
    ``WorkflowService``'s read variant can supply this collaborator without
    resolving the strict, all-tenants-incompatible dependency.
    """
    return SqlWorkflowPublishedVersionRepository(db, tenant_id=tenant_id)


WorkflowPublishedVersionReadRepositoryDep = Annotated[
    WorkflowPublishedVersionRepository,
    Depends(get_workflow_published_version_read_repository),
]


def get_workflow_execution_repository(
    db: DBSessionDep, tenant_id: CurrentTenantIdDep
) -> WorkflowExecutionRepository:
    """Create a WorkflowExecutionRepository backed by the current database session."""
    return SqlWorkflowExecutionRepository(db, tenant_id=tenant_id)


WorkflowExecutionRepositoryDep = Annotated[
    WorkflowExecutionRepository, Depends(get_workflow_execution_repository)
]


def get_workflow_execution_read_repository(
    db: DBSessionDep, tenant_id: CurrentTenantScopeDep
) -> WorkflowExecutionRepository:
    """Create a WorkflowExecutionRepository for a read route, possibly across all tenants."""
    return SqlWorkflowExecutionRepository(db, tenant_id=tenant_id)


WorkflowExecutionReadRepositoryDep = Annotated[
    WorkflowExecutionRepository, Depends(get_workflow_execution_read_repository)
]


def get_message_meta_repository(
    db: DBSessionDep, tenant_id: CurrentTenantIdDep
) -> MessageMetaRepository:
    """Create a MessageMetaRepository backed by the current database session."""
    return SqlMessageMetaRepository(db, tenant_id=tenant_id)


MessageMetaRepositoryDep = Annotated[
    MessageMetaRepository, Depends(get_message_meta_repository)
]


def get_message_meta_read_repository(
    db: DBSessionDep, tenant_id: CurrentTenantScopeDep
) -> MessageMetaRepository:
    """Create a MessageMetaRepository for a read route.

    Not exposed through any route of its own yet -- exists only so
    ``WorkflowService``'s read variant can supply this collaborator without
    resolving the strict, all-tenants-incompatible dependency.
    """
    return SqlMessageMetaRepository(db, tenant_id=tenant_id)


MessageMetaReadRepositoryDep = Annotated[
    MessageMetaRepository, Depends(get_message_meta_read_repository)
]


def get_workflow_task_repository(
    db: DBSessionDep,
    execution_repo: WorkflowExecutionRepositoryDep,
    mcp_repo: MCPServerRepositoryDep,
    tenant_id: CurrentTenantIdDep,
) -> WorkflowTaskRepository:
    """Create a WorkflowTaskRepository backed by the current database session.

    The injected WorkflowExecutionRepository is used to validate that the parent
    session exists when creating tasks; the MCPServerRepository validates the
    servers referenced by tool bindings.
    """
    return SqlWorkflowTaskRepository(db, execution_repo, mcp_repo, tenant_id=tenant_id)


WorkflowTaskRepositoryDep = Annotated[
    WorkflowTaskRepository, Depends(get_workflow_task_repository)
]


def get_workflow_task_read_repository(
    db: DBSessionDep,
    execution_repo: WorkflowExecutionReadRepositoryDep,
    mcp_repo: MCPServerReadRepositoryDep,
    tenant_id: CurrentTenantScopeDep,
) -> WorkflowTaskRepository:
    """Create a WorkflowTaskRepository for a read route, possibly across all tenants.

    Both collaborators must be the read repositories: merely resolving either
    strict dependency would itself raise in all-tenants mode.
    """
    return SqlWorkflowTaskRepository(db, execution_repo, mcp_repo, tenant_id=tenant_id)


WorkflowTaskReadRepositoryDep = Annotated[
    WorkflowTaskRepository, Depends(get_workflow_task_read_repository)
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


def get_workflow_task_template_read_repository(
    db: DBSessionDep,
    workflows: WorkflowReadRepositoryDep,
    mcp_repo: MCPServerReadRepositoryDep,
    tenant_id: CurrentTenantScopeDep,
) -> WorkflowTaskTemplateRepository:
    """Create a WorkflowTaskTemplateRepository for a read route, possibly across all tenants.

    Both collaborators must be the read repositories: merely resolving either
    strict dependency would itself raise in all-tenants mode.
    """
    return SqlWorkflowTaskTemplateRepository(
        db, workflows, mcp_repo, tenant_id=tenant_id
    )


WorkflowTaskTemplateReadRepositoryDep = Annotated[
    WorkflowTaskTemplateRepository, Depends(get_workflow_task_template_read_repository)
]


def get_approval_repository(
    db: DBSessionDep,
    execution_repo: WorkflowExecutionRepositoryDep,
    group_repo: UserGroupRepositoryDep,
    tenant_id: CurrentTenantIdDep,
) -> ApprovalRepository:
    """Create an ApprovalRepository backed by the current database session.

    The injected WorkflowExecutionRepository is used to validate that the parent
    session exists when creating an approval, and the UserGroupRepository that a
    group destination exists. Both arrive from the same request-cached factories
    as this one, so all three share the acting ``tenant_id``.
    """
    return SqlApprovalRepository(db, execution_repo, group_repo, tenant_id=tenant_id)


ApprovalRepositoryDep = Annotated[ApprovalRepository, Depends(get_approval_repository)]


def get_approval_read_repository(
    db: DBSessionDep,
    execution_repo: WorkflowExecutionReadRepositoryDep,
    group_repo: UserGroupReadRepositoryDep,
    tenant_id: CurrentTenantScopeDep,
) -> ApprovalRepository:
    """Create an ApprovalRepository for a read route, possibly across all tenants.

    Both collaborators must be the read repositories: merely resolving either
    strict dependency would itself raise in all-tenants mode.
    """
    return SqlApprovalRepository(db, execution_repo, group_repo, tenant_id=tenant_id)


ApprovalReadRepositoryDep = Annotated[
    ApprovalRepository, Depends(get_approval_read_repository)
]
