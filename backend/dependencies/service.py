"""Per-request service (use case) dependencies wiring repositories and singletons.

Each service is constructed from the request-scoped repositories it operates on,
plus any singletons it needs (the skill manager, the agent registry). These are
the dependencies routers inject to invoke business logic.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends

from config import get_settings
from infrastructure.secret_resolver import SecretResolver
from services import (
    AgentSkillService,
    ApprovalService,
    ApproverGroupResolver,
    ImpersonationEventService,
    MCPRegistryService,
    MCPServerService,
    McpToolCertificateService,
    McpToolInvocationService,
    MCPToolMockService,
    MetricsService,
    NotificationDispatcher,
    NotificationService,
    OutboundEmailService,
    SecretService,
    SystemSettingsService,
    TagService,
    TenantService,
    UserAvatarService,
    UserGroupService,
    UserService,
    WorkflowDesignService,
    WorkflowExecutionAccessPolicy,
    WorkflowExecutionService,
    WorkflowService,
    WorkflowTaskService,
    WorkflowTaskTemplateService,
    generate_workflow_design,
    sync_agent_skill,
)

from .context import APP_NAME
from .repository import (
    AgentSkillReadRepositoryDep,
    AgentSkillRepositoryDep,
    ApprovalReadRepositoryDep,
    ApprovalRepositoryDep,
    DBSessionDep,
    EffectiveRoleRepositoryDep,
    ImpersonationEventReadRepositoryDep,
    McpCertificateAuthorityRepositoryDep,
    MCPServerReadRepositoryDep,
    MCPServerRepositoryDep,
    McpToolCertificateReadRepositoryDep,
    McpToolCertificateRepositoryDep,
    McpToolInvocationReadRepositoryDep,
    McpToolInvocationRepositoryDep,
    MCPToolMockReadRepositoryDep,
    MCPToolMockRepositoryDep,
    MessageMetaReadRepositoryDep,
    MessageMetaRepositoryDep,
    MetricsRepositoryDep,
    NotificationReadRepositoryDep,
    NotificationRepositoryDep,
    OutboundEmailReadRepositoryDep,
    OutboundEmailRepositoryDep,
    SecretReadRepositoryDep,
    SecretRepositoryDep,
    SystemSettingsRepositoryDep,
    TagReadRepositoryDep,
    TagRepositoryDep,
    TenantRepositoryDep,
    UserAvatarRepositoryDep,
    UserGroupReadRepositoryDep,
    UserGroupRepositoryDep,
    UserRepositoryDep,
    WorkflowExecutionReadRepositoryDep,
    WorkflowExecutionRepositoryDep,
    WorkflowPublishedVersionReadRepositoryDep,
    WorkflowPublishedVersionRepositoryDep,
    WorkflowReadRepositoryDep,
    WorkflowRepositoryDep,
    WorkflowTaskReadRepositoryDep,
    WorkflowTaskRepositoryDep,
    WorkflowTaskTemplateReadRepositoryDep,
    WorkflowTaskTemplateRepositoryDep,
)
from .singletons import (
    AgentRegistryDep,
    SecretCipherDep,
    SessionServiceDep,
    SkillManagerDep,
    VaultClientDep,
)


def get_agent_skill_service(
    repo: AgentSkillRepositoryDep, secrets: SecretRepositoryDep
) -> AgentSkillService:
    """Create an AgentSkillService backed by the request's repositories."""
    return AgentSkillService(repo, secrets)


AgentSkillServiceDep = Annotated[AgentSkillService, Depends(get_agent_skill_service)]


def get_agent_skill_read_service(
    repo: AgentSkillReadRepositoryDep, secrets: SecretReadRepositoryDep
) -> AgentSkillService:
    """Create an AgentSkillService for a read route, possibly across all tenants.

    Backs only ``GET`` routes. ``secrets`` must be the read repository even
    though ``AgentSkillService.get``/``list`` never call it: merely resolving
    the strict ``SecretRepositoryDep`` would itself raise in all-tenants mode,
    since it depends on ``CurrentTenantIdDep``.
    """
    return AgentSkillService(repo, secrets)


AgentSkillReadServiceDep = Annotated[
    AgentSkillService, Depends(get_agent_skill_read_service)
]

#: The background clone/pull job, as the agent-skills router hands it to
#: ``BackgroundTasks``.
SkillSyncJob = Callable[..., Awaitable[None]]


def get_skill_sync_job() -> SkillSyncJob:
    """Return the background job that clones a skill's repository into the store.

    Injected rather than called by name so tests can override it: the real job
    opens a database session of its own on the application engine, which a test
    driving the router over an in-memory database has no way to redirect.
    """
    return sync_agent_skill


SkillSyncJobDep = Annotated[SkillSyncJob, Depends(get_skill_sync_job)]


def get_secret_resolver(
    repo: SecretRepositoryDep,
    cipher: SecretCipherDep,
    vault: VaultClientDep,
) -> SecretResolver:
    """Create a SecretResolver wiring the repository, cipher, and optional Vault client."""
    return SecretResolver(repo, cipher, vault)


SecretResolverDep = Annotated[SecretResolver, Depends(get_secret_resolver)]


def get_secret_resolver_read(
    repo: SecretReadRepositoryDep,
    cipher: SecretCipherDep,
    vault: VaultClientDep,
) -> SecretResolver:
    """Create a SecretResolver for a read route, possibly across all tenants.

    The collaborator any other read service must use in place of
    :data:`SecretResolverDep` -- e.g. ``MCPServerService.list_tools`` resolves
    ``${secret:NAME/KEY}`` placeholders through this on a read route.
    """
    return SecretResolver(repo, cipher, vault)


SecretResolverReadDep = Annotated[SecretResolver, Depends(get_secret_resolver_read)]


def get_secret_service(
    repo: SecretRepositoryDep, cipher: SecretCipherDep, resolver: SecretResolverDep
) -> SecretService:
    """Create a SecretService wiring the repository, cipher, and resolver.

    Declared after :func:`get_secret_resolver` because it annotates against
    ``SecretResolverDep``. FastAPI caches ``Depends()`` per request, so the
    resolver's repository is the very same tenant-scoped instance the service
    holds.
    """
    return SecretService(repo, cipher, resolver)


SecretServiceDep = Annotated[SecretService, Depends(get_secret_service)]


def get_secret_read_service(
    repo: SecretReadRepositoryDep,
    cipher: SecretCipherDep,
    resolver: SecretResolverReadDep,
) -> SecretService:
    """Create a SecretService for a read route, possibly across all tenants.

    Backs ``GET`` routes, including ``list_secret_keys``, which does call
    ``resolver.list_keys`` -- unlike AgentSkill's collaborator, this one is
    actually exercised on the read path, not just resolved and ignored.
    """
    return SecretService(repo, cipher, resolver)


SecretReadServiceDep = Annotated[SecretService, Depends(get_secret_read_service)]


def get_tag_service(repo: TagRepositoryDep) -> TagService:
    """Create a TagService backed by the request's tenant-scoped repository."""
    return TagService(repo)


TagServiceDep = Annotated[TagService, Depends(get_tag_service)]


def get_tag_read_service(repo: TagReadRepositoryDep) -> TagService:
    """Create a TagService for a read route, possibly across all tenants."""
    return TagService(repo)


TagReadServiceDep = Annotated[TagService, Depends(get_tag_read_service)]


def get_mcp_server_service(
    repo: MCPServerRepositoryDep, resolver: SecretResolverDep
) -> MCPServerService:
    """Create an MCPServerService backed by the request's repository and resolver."""
    return MCPServerService(repo, resolver)


MCPServerServiceDep = Annotated[MCPServerService, Depends(get_mcp_server_service)]


def get_mcp_server_read_service(
    repo: MCPServerReadRepositoryDep, resolver: SecretResolverReadDep
) -> MCPServerService:
    """Create an MCPServerService for a read route, possibly across all tenants.

    Backs ``GET`` routes, including ``list_tools``, which resolves
    ``${secret:NAME/KEY}`` placeholders through ``resolver`` before connecting.
    """
    return MCPServerService(repo, resolver)


MCPServerReadServiceDep = Annotated[
    MCPServerService, Depends(get_mcp_server_read_service)
]


def get_mcp_tool_mock_service(repo: MCPToolMockRepositoryDep) -> MCPToolMockService:
    """Create an MCPToolMockService backed by the request's repository."""
    return MCPToolMockService(repo)


MCPToolMockServiceDep = Annotated[
    MCPToolMockService, Depends(get_mcp_tool_mock_service)
]


def get_mcp_tool_mock_read_service(
    repo: MCPToolMockReadRepositoryDep,
) -> MCPToolMockService:
    """Create an MCPToolMockService for a read route, possibly across all tenants."""
    return MCPToolMockService(repo)


MCPToolMockReadServiceDep = Annotated[
    MCPToolMockService, Depends(get_mcp_tool_mock_read_service)
]


def get_mcp_tool_invocation_service(
    repo: McpToolInvocationReadRepositoryDep,
) -> McpToolInvocationService:
    """Create an McpToolInvocationService for the tenant-wide audit read routes.

    Built on the read repository because the service exposes nothing but reads,
    which a platform-scoped caller may run across every tenant at once.
    """
    return McpToolInvocationService(repo)


McpToolInvocationServiceDep = Annotated[
    McpToolInvocationService, Depends(get_mcp_tool_invocation_service)
]


def get_impersonation_event_service(
    repo: ImpersonationEventReadRepositoryDep,
) -> ImpersonationEventService:
    """Create an ImpersonationEventService for the audit read routes."""
    return ImpersonationEventService(repo)


ImpersonationEventServiceDep = Annotated[
    ImpersonationEventService, Depends(get_impersonation_event_service)
]


def get_mcp_registry_service() -> MCPRegistryService:
    """Create an MCPRegistryService for official-registry discovery."""
    return MCPRegistryService()


MCPRegistryServiceDep = Annotated[MCPRegistryService, Depends(get_mcp_registry_service)]


def get_metrics_service(
    repo: MetricsRepositoryDep, emails: OutboundEmailRepositoryDep
) -> MetricsService:
    """Create a MetricsService, resolving the day-boundary timezone from settings."""
    return MetricsService(repo, emails, timezone=get_settings().metrics_timezone)


MetricsServiceDep = Annotated[MetricsService, Depends(get_metrics_service)]


def get_notification_service(repo: NotificationRepositoryDep) -> NotificationService:
    """Create a NotificationService backed by the request's repository."""
    return NotificationService(repo)


NotificationServiceDep = Annotated[
    NotificationService, Depends(get_notification_service)
]


def get_notification_read_service(
    repo: NotificationReadRepositoryDep,
) -> NotificationService:
    """Create a NotificationService for a read route, possibly across all tenants."""
    return NotificationService(repo)


NotificationReadServiceDep = Annotated[
    NotificationService, Depends(get_notification_read_service)
]


def get_system_settings_service(
    repo: SystemSettingsRepositoryDep, cipher: SecretCipherDep
) -> SystemSettingsService:
    """Create a SystemSettingsService backed by the request's repository."""
    return SystemSettingsService(repo, cipher)


SystemSettingsServiceDep = Annotated[
    SystemSettingsService, Depends(get_system_settings_service)
]


def get_notification_dispatcher(
    db: DBSessionDep,
    notifications: NotificationRepositoryDep,
    users: UserRepositoryDep,
    settings: SystemSettingsServiceDep,
    emails: OutboundEmailRepositoryDep,
) -> NotificationDispatcher:
    """Create a NotificationDispatcher backed by the request's collaborators.

    Takes the session as well as the repositories: the dispatcher writes the
    notification and its queued email in one transaction, so it owns the commit
    (see :mod:`services.notification_dispatch`). FastAPI caches ``Depends``
    results per request, so this is the same session the repositories hold.

    Request-scoped counterpart of
    :func:`services.notification_dispatch.build_notification_dispatcher`, which
    the agent tools and background jobs use because they run outside request
    scope.
    """
    return NotificationDispatcher(db, notifications, users, settings, emails)


NotificationDispatcherDep = Annotated[
    NotificationDispatcher, Depends(get_notification_dispatcher)
]


def get_outbound_email_service(
    repo: OutboundEmailRepositoryDep,
) -> OutboundEmailService:
    """Create an OutboundEmailService backed by the request's tenant-scoped repository."""
    return OutboundEmailService(repo)


OutboundEmailServiceDep = Annotated[
    OutboundEmailService, Depends(get_outbound_email_service)
]


def get_outbound_email_read_service(
    repo: OutboundEmailReadRepositoryDep,
) -> OutboundEmailService:
    """Create an OutboundEmailService for a read route, possibly across all tenants.

    Backs only ``GET`` routes (list/get); ``delete`` stays on
    :func:`get_outbound_email_service`, so it can never run with no concrete
    tenant selected.
    """
    return OutboundEmailService(repo)


OutboundEmailReadServiceDep = Annotated[
    OutboundEmailService, Depends(get_outbound_email_read_service)
]


def get_notification_dispatcher_read(
    db: DBSessionDep,
    notifications: NotificationReadRepositoryDep,
    users: UserRepositoryDep,
    settings: SystemSettingsServiceDep,
    emails: OutboundEmailReadRepositoryDep,
) -> NotificationDispatcher:
    """Create a NotificationDispatcher for a read route.

    Not exercised by any read route today -- exists only so a write-oriented
    service with a read variant (e.g. ``WorkflowTaskService``) can be
    constructed without resolving the strict, all-tenants-incompatible
    dependency this collaborator would otherwise pull in.
    """
    return NotificationDispatcher(db, notifications, users, settings, emails)


NotificationDispatcherReadDep = Annotated[
    NotificationDispatcher, Depends(get_notification_dispatcher_read)
]


def get_tenant_service(repo: TenantRepositoryDep) -> TenantService:
    """Create a TenantService backed by the request's repository."""
    return TenantService(repo)


TenantServiceDep = Annotated[TenantService, Depends(get_tenant_service)]


def get_user_service(
    repo: UserRepositoryDep, effective_roles: EffectiveRoleRepositoryDep
) -> UserService:
    """Create a UserService backed by the request's repositories.

    Deliberately takes no tenant-scoped repository: ``CurrentTenantIdDep``
    raises for a platform-scoped caller who has selected no tenant, which
    would lock a tenant-less super admin out of every user route -- including
    their own profile page. ``EffectiveRoleRepositoryDep`` is tenant-unscoped
    and therefore safe to pull in here.
    """
    return UserService(repo, effective_roles)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


def get_user_group_service(repo: UserGroupRepositoryDep) -> UserGroupService:
    """Create a UserGroupService backed by the request's repository."""
    return UserGroupService(repo)


UserGroupServiceDep = Annotated[UserGroupService, Depends(get_user_group_service)]


def get_user_group_read_service(repo: UserGroupReadRepositoryDep) -> UserGroupService:
    """Create a UserGroupService for a read route, possibly across all tenants."""
    return UserGroupService(repo)


UserGroupReadServiceDep = Annotated[
    UserGroupService, Depends(get_user_group_read_service)
]


def get_user_avatar_service(repo: UserAvatarRepositoryDep) -> UserAvatarService:
    """Create a UserAvatarService backed by the request's repository."""
    return UserAvatarService(repo)


UserAvatarServiceDep = Annotated[UserAvatarService, Depends(get_user_avatar_service)]


def get_workflow_service(
    workflows: WorkflowRepositoryDep,
    skills: AgentSkillRepositoryDep,
    execution_repo: WorkflowExecutionRepositoryDep,
    templates: WorkflowTaskTemplateRepositoryDep,
    tasks: WorkflowTaskRepositoryDep,
    versions: WorkflowPublishedVersionRepositoryDep,
    meta: MessageMetaRepositoryDep,
    mocks: MCPToolMockRepositoryDep,
    skills_store: SkillManagerDep,
    registry: AgentRegistryDep,
    session_service: SessionServiceDep,
) -> WorkflowService:
    """Create a WorkflowService wiring its repositories, skill store, agent registry, and session store.

    The last five collaborators serve the workflow's design session: the store
    and registry resolve the design agent, the session store holds its chat
    history, and the metadata repository records which developer sent each
    message in that shared chat.
    """
    return WorkflowService(
        workflows,
        skills,
        execution_repo,
        templates,
        tasks,
        versions,
        meta,
        mocks,
        skills_store,
        registry,
        session_service,
        APP_NAME,
    )


WorkflowServiceDep = Annotated[WorkflowService, Depends(get_workflow_service)]


def get_workflow_read_service(
    workflows: WorkflowReadRepositoryDep,
    skills: AgentSkillReadRepositoryDep,
    execution_repo: WorkflowExecutionReadRepositoryDep,
    templates: WorkflowTaskTemplateReadRepositoryDep,
    tasks: WorkflowTaskReadRepositoryDep,
    versions: WorkflowPublishedVersionReadRepositoryDep,
    meta: MessageMetaReadRepositoryDep,
    mocks: MCPToolMockReadRepositoryDep,
    skills_store: SkillManagerDep,
    registry: AgentRegistryDep,
    session_service: SessionServiceDep,
) -> WorkflowService:
    """Create a WorkflowService for a read route, possibly across all tenants.

    Backs ``list_workflows``, ``get_workflow``, and
    ``get_design_session_messages`` (``list_workflow_task_templates`` is
    served by ``WorkflowTaskTemplateReadServiceDep`` instead, not this one).
    Only ``get_design_session_messages`` touches a collaborator beyond
    ``workflows`` -- its ``meta`` read for the design session's per-message
    attribution -- but every other collaborator here must still be the read
    repository (not the strict one) regardless, since merely resolving a
    strict, tenant-scoped dependency would itself raise in all-tenants mode
    even for the two methods that never call into it.
    """
    return WorkflowService(
        workflows,
        skills,
        execution_repo,
        templates,
        tasks,
        versions,
        meta,
        mocks,
        skills_store,
        registry,
        session_service,
        APP_NAME,
    )


WorkflowReadServiceDep = Annotated[WorkflowService, Depends(get_workflow_read_service)]


def get_workflow_design_service(
    workflows: WorkflowRepositoryDep,
    skills: AgentSkillRepositoryDep,
    templates: WorkflowTaskTemplateRepositoryDep,
    versions: WorkflowPublishedVersionRepositoryDep,
    session_service: SessionServiceDep,
) -> WorkflowDesignService:
    """Create a WorkflowDesignService wiring the repositories and the session store."""
    return WorkflowDesignService(
        workflows, skills, templates, versions, session_service, APP_NAME
    )


WorkflowDesignServiceDep = Annotated[
    WorkflowDesignService, Depends(get_workflow_design_service)
]

#: The background design job, as the agent-skills router hands it to
#: ``BackgroundTasks``.
WorkflowGenerationJob = Callable[..., Awaitable[None]]


def get_workflow_generation_job(
    registry: AgentRegistryDep,
    session_service: SessionServiceDep,
    skills_store: SkillManagerDep,
) -> WorkflowGenerationJob:
    """Return the background job that generates a workflow's initial task templates.

    Injected rather than called by name so tests can override it: the real job
    runs a full agent turn against an LLM and opens database sessions of its
    own on the application engine. The process-wide singletons the job needs
    are captured here, where DI can resolve them, because the job itself runs
    after the request scope is gone.
    """

    async def job(workflow_id: str, prompt: str, *, user_id: str) -> None:
        await generate_workflow_design(
            workflow_id,
            prompt,
            user_id=user_id,
            registry=registry,
            session_service=session_service,
            skills_store=skills_store,
            app_name=APP_NAME,
        )

    return job


WorkflowGenerationJobDep = Annotated[
    WorkflowGenerationJob, Depends(get_workflow_generation_job)
]


def get_approver_group_resolver(
    groups: UserGroupRepositoryDep,
    effective_roles: EffectiveRoleRepositoryDep,
) -> ApproverGroupResolver:
    """Create the resolver for the groups a caller may approve for."""
    return ApproverGroupResolver(groups, effective_roles)


ApproverGroupResolverDep = Annotated[
    ApproverGroupResolver, Depends(get_approver_group_resolver)
]


def get_approver_group_resolver_read(
    groups: UserGroupReadRepositoryDep,
    effective_roles: EffectiveRoleRepositoryDep,
) -> ApproverGroupResolver:
    """Create the approver-group resolver for a read route, possibly across all tenants."""
    return ApproverGroupResolver(groups, effective_roles)


ApproverGroupResolverReadDep = Annotated[
    ApproverGroupResolver, Depends(get_approver_group_resolver_read)
]


def get_workflow_execution_access_policy(
    approvals: ApprovalRepositoryDep,
    approver_groups: ApproverGroupResolverDep,
) -> WorkflowExecutionAccessPolicy:
    """Create the access policy for workflow-execution-scoped operations."""
    return WorkflowExecutionAccessPolicy(approvals, approver_groups)


WorkflowExecutionAccessPolicyDep = Annotated[
    WorkflowExecutionAccessPolicy, Depends(get_workflow_execution_access_policy)
]


def get_workflow_execution_access_policy_read(
    approvals: ApprovalReadRepositoryDep,
    approver_groups: ApproverGroupResolverReadDep,
) -> WorkflowExecutionAccessPolicy:
    """Create the access policy for a read route, possibly across all tenants.

    A super_admin (the only caller who can reach all-tenants mode) always
    passes ``assert_read_access``'s role bypass before ``approvals`` is ever
    queried, but this must still be the read repository: merely resolving the
    strict one would raise regardless.
    """
    return WorkflowExecutionAccessPolicy(approvals, approver_groups)


WorkflowExecutionAccessPolicyReadDep = Annotated[
    WorkflowExecutionAccessPolicy, Depends(get_workflow_execution_access_policy_read)
]


def get_workflow_execution_service(
    execution_repo: WorkflowExecutionRepositoryDep,
    tasks: WorkflowTaskRepositoryDep,
    meta: MessageMetaRepositoryDep,
    invocations: McpToolInvocationRepositoryDep,
    skills: AgentSkillRepositoryDep,
    skills_store: SkillManagerDep,
    registry: AgentRegistryDep,
    session_service: SessionServiceDep,
    access: WorkflowExecutionAccessPolicyDep,
) -> WorkflowExecutionService:
    """Create a WorkflowExecutionService wiring the repositories, skill store, agent registry, session store, and access policy."""
    return WorkflowExecutionService(
        execution_repo,
        tasks,
        meta,
        invocations,
        skills,
        skills_store,
        registry,
        session_service,
        APP_NAME,
        access,
    )


WorkflowExecutionServiceDep = Annotated[
    WorkflowExecutionService, Depends(get_workflow_execution_service)
]


def get_workflow_execution_read_service(
    execution_repo: WorkflowExecutionReadRepositoryDep,
    tasks: WorkflowTaskReadRepositoryDep,
    meta: MessageMetaReadRepositoryDep,
    invocations: McpToolInvocationReadRepositoryDep,
    skills: AgentSkillReadRepositoryDep,
    skills_store: SkillManagerDep,
    registry: AgentRegistryDep,
    session_service: SessionServiceDep,
    access: WorkflowExecutionAccessPolicyReadDep,
) -> WorkflowExecutionService:
    """Create a WorkflowExecutionService for a read route, possibly across all tenants."""
    return WorkflowExecutionService(
        execution_repo,
        tasks,
        meta,
        invocations,
        skills,
        skills_store,
        registry,
        session_service,
        APP_NAME,
        access,
    )


WorkflowExecutionReadServiceDep = Annotated[
    WorkflowExecutionService, Depends(get_workflow_execution_read_service)
]


def get_mcp_tool_certificate_service(
    certificates: McpToolCertificateRepositoryDep,
    tasks: WorkflowTaskRepositoryDep,
    authorities: McpCertificateAuthorityRepositoryDep,
    cipher: SecretCipherDep,
    approvals: ApprovalRepositoryDep,
) -> McpToolCertificateService:
    """Create an McpToolCertificateService backed by the request's repositories."""
    return McpToolCertificateService(
        certificates, tasks, authorities, cipher, approvals
    )


McpToolCertificateServiceDep = Annotated[
    McpToolCertificateService, Depends(get_mcp_tool_certificate_service)
]


def get_mcp_tool_certificate_read_service(
    certificates: McpToolCertificateReadRepositoryDep,
    tasks: WorkflowTaskReadRepositoryDep,
    authorities: McpCertificateAuthorityRepositoryDep,
    cipher: SecretCipherDep,
    approvals: ApprovalReadRepositoryDep,
) -> McpToolCertificateService:
    """Create an McpToolCertificateService for a read route, possibly across all tenants.

    Backs only ``read_for_approval`` (``GET /approvals/{id}/certificate``),
    which touches only ``certificates`` -- every other collaborator here must
    still be a read repository, since merely resolving a strict one would itself
    raise regardless of whether this service calls into it.
    """
    return McpToolCertificateService(
        certificates, tasks, authorities, cipher, approvals
    )


McpToolCertificateReadServiceDep = Annotated[
    McpToolCertificateService, Depends(get_mcp_tool_certificate_read_service)
]


def get_workflow_task_service(
    repo: WorkflowTaskRepositoryDep,
    execution_repo: WorkflowExecutionRepositoryDep,
    access: WorkflowExecutionAccessPolicyDep,
    approvals: ApprovalRepositoryDep,
    notifications: NotificationDispatcherDep,
    approver_groups: ApproverGroupResolverDep,
    certificates: McpToolCertificateServiceDep,
) -> WorkflowTaskService:
    """Create a WorkflowTaskService wiring the task, session, and approval repositories, the notification dispatcher, the access policy, and the approver-group resolver."""
    return WorkflowTaskService(
        repo,
        execution_repo,
        access,
        approvals,
        notifications,
        approver_groups,
        certificates,
    )


WorkflowTaskServiceDep = Annotated[
    WorkflowTaskService, Depends(get_workflow_task_service)
]


def get_workflow_task_read_service(
    repo: WorkflowTaskReadRepositoryDep,
    execution_repo: WorkflowExecutionReadRepositoryDep,
    access: WorkflowExecutionAccessPolicyReadDep,
    approvals: ApprovalReadRepositoryDep,
    notifications: NotificationDispatcherReadDep,
    approver_groups: ApproverGroupResolverReadDep,
    certificates: McpToolCertificateReadServiceDep,
) -> WorkflowTaskService:
    """Create a WorkflowTaskService for a read route, possibly across all tenants.

    Backs only ``get_workflow_task``, which touches only ``repo`` and
    ``access`` -- every other collaborator here must still be a read
    repository/service, since merely resolving a strict one would itself
    raise regardless of whether this service calls into it.
    """
    return WorkflowTaskService(
        repo,
        execution_repo,
        access,
        approvals,
        notifications,
        approver_groups,
        certificates,
    )


WorkflowTaskReadServiceDep = Annotated[
    WorkflowTaskService, Depends(get_workflow_task_read_service)
]


def get_workflow_task_template_service(
    repo: WorkflowTaskTemplateRepositoryDep,
    workflows: WorkflowRepositoryDep,
    versions: WorkflowPublishedVersionRepositoryDep,
) -> WorkflowTaskTemplateService:
    """Create a WorkflowTaskTemplateService wiring the template and workflow repositories."""
    return WorkflowTaskTemplateService(repo, workflows, versions)


WorkflowTaskTemplateServiceDep = Annotated[
    WorkflowTaskTemplateService, Depends(get_workflow_task_template_service)
]


def get_workflow_task_template_read_service(
    repo: WorkflowTaskTemplateReadRepositoryDep,
    workflows: WorkflowReadRepositoryDep,
    versions: WorkflowPublishedVersionReadRepositoryDep,
) -> WorkflowTaskTemplateService:
    """Create a WorkflowTaskTemplateService for a read route, possibly across all tenants."""
    return WorkflowTaskTemplateService(repo, workflows, versions)


WorkflowTaskTemplateReadServiceDep = Annotated[
    WorkflowTaskTemplateService, Depends(get_workflow_task_template_read_service)
]


def get_approval_service(
    repo: ApprovalRepositoryDep,
    approver_groups: ApproverGroupResolverDep,
    certificates: McpToolCertificateServiceDep,
) -> ApprovalService:
    """Create an ApprovalService backed by the request's repository."""
    return ApprovalService(repo, approver_groups, certificates)


ApprovalServiceDep = Annotated[ApprovalService, Depends(get_approval_service)]


def get_approval_read_service(
    repo: ApprovalReadRepositoryDep,
    approver_groups: ApproverGroupResolverReadDep,
    certificates: McpToolCertificateReadServiceDep,
) -> ApprovalService:
    """Create an ApprovalService for a read route, possibly across all tenants."""
    return ApprovalService(repo, approver_groups, certificates)


ApprovalReadServiceDep = Annotated[ApprovalService, Depends(get_approval_read_service)]
