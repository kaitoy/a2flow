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
from repositories.session_file import SessionFileRepository
from services.agent_skill import AgentSkillService
from services.agent_skill_sync import sync_agent_skill
from services.approval import ApprovalService
from services.approver_groups import ApproverGroupResolver
from services.impersonation_event import ImpersonationEventService
from services.mcp_registry import MCPRegistryService
from services.mcp_server import MCPServerService
from services.mcp_tool_certificate import McpToolCertificateService
from services.mcp_tool_invocation import McpToolInvocationService
from services.mcp_tool_mock import MCPToolMockService
from services.metrics import MetricsService
from services.notification import NotificationService
from services.notification_dispatch import NotificationDispatcher
from services.outbound_email import OutboundEmailService
from services.secret import SecretService
from services.session_file import SessionFileService, SessionFileStore
from services.system_settings import SystemSettingsService
from services.tag import TagService
from services.tenant import TenantService
from services.user import UserService
from services.user_avatar import UserAvatarService
from services.user_group import UserGroupService
from services.workflow import WorkflowService
from services.workflow_design import WorkflowDesignService, generate_workflow_design
from services.workflow_execution import WorkflowExecutionService
from services.workflow_execution_access import WorkflowExecutionAccessPolicy
from services.workflow_task import WorkflowTaskService
from services.workflow_task_template import WorkflowTaskTemplateService

from .context import APP_NAME
from .repository import (
    AgentSkillRepositoryDep,
    ApprovalRepositoryDep,
    DBSessionDep,
    EffectiveRoleRepositoryDep,
    ImpersonationEventRepositoryDep,
    McpCertificateAuthorityRepositoryDep,
    MCPServerRepositoryDep,
    McpToolCertificateRepositoryDep,
    McpToolInvocationRepositoryDep,
    MCPToolMockRepositoryDep,
    MessageMetaRepositoryDep,
    MetricsRepositoryDep,
    NotificationRepositoryDep,
    OutboundEmailRepositoryDep,
    SecretRepositoryDep,
    SessionFileRepositoryDep,
    SystemSettingsRepositoryDep,
    TagRepositoryDep,
    TenantRepositoryDep,
    UserAvatarRepositoryDep,
    UserGroupRepositoryDep,
    UserRepositoryDep,
    WorkflowExecutionRepositoryDep,
    WorkflowPublishedVersionRepositoryDep,
    WorkflowRepositoryDep,
    WorkflowTaskRepositoryDep,
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
    repo: AgentSkillRepositoryDep,
    secrets: SecretRepositoryDep,
    skill_manager: SkillManagerDep,
) -> AgentSkillService:
    """Create an AgentSkillService backed by the request's repositories."""
    return AgentSkillService(repo, secrets, skill_manager)


AgentSkillServiceDep = Annotated[AgentSkillService, Depends(get_agent_skill_service)]

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


def get_tag_service(repo: TagRepositoryDep) -> TagService:
    """Create a TagService backed by the request's tenant-scoped repository."""
    return TagService(repo)


TagServiceDep = Annotated[TagService, Depends(get_tag_service)]


def get_mcp_server_service(
    repo: MCPServerRepositoryDep, resolver: SecretResolverDep
) -> MCPServerService:
    """Create an MCPServerService backed by the request's repository and resolver."""
    return MCPServerService(repo, resolver)


MCPServerServiceDep = Annotated[MCPServerService, Depends(get_mcp_server_service)]


def get_mcp_tool_mock_service(repo: MCPToolMockRepositoryDep) -> MCPToolMockService:
    """Create an MCPToolMockService backed by the request's repository."""
    return MCPToolMockService(repo)


MCPToolMockServiceDep = Annotated[
    MCPToolMockService, Depends(get_mcp_tool_mock_service)
]


def get_mcp_tool_invocation_service(
    repo: McpToolInvocationRepositoryDep,
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
    repo: ImpersonationEventRepositoryDep,
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


def get_workflow_execution_access_policy(
    approvals: ApprovalRepositoryDep,
    approver_groups: ApproverGroupResolverDep,
) -> WorkflowExecutionAccessPolicy:
    """Create the access policy for workflow-execution-scoped operations."""
    return WorkflowExecutionAccessPolicy(approvals, approver_groups)


WorkflowExecutionAccessPolicyDep = Annotated[
    WorkflowExecutionAccessPolicy, Depends(get_workflow_execution_access_policy)
]


def _session_file_store(files: SessionFileRepository) -> SessionFileStore:
    """Build the validating session-file store both service factories wrap.

    The size limits come from settings rather than from a route, so the two
    scopes cannot drift into enforcing different caps.
    """
    settings = get_settings()
    return SessionFileStore(
        files,
        max_file_bytes=settings.session_file_max_bytes,
        max_total_bytes=settings.session_files_max_total_bytes,
    )


def get_session_file_service(
    files: SessionFileRepositoryDep,
    executions: WorkflowExecutionRepositoryDep,
    access: WorkflowExecutionAccessPolicyDep,
) -> SessionFileService:
    """Create a SessionFileService for a route that acts on a run's files."""
    return SessionFileService(_session_file_store(files), executions, access)


SessionFileServiceDep = Annotated[SessionFileService, Depends(get_session_file_service)]


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


def get_approval_service(
    repo: ApprovalRepositoryDep,
    approver_groups: ApproverGroupResolverDep,
    certificates: McpToolCertificateServiceDep,
) -> ApprovalService:
    """Create an ApprovalService backed by the request's repository."""
    return ApprovalService(repo, approver_groups, certificates)


ApprovalServiceDep = Annotated[ApprovalService, Depends(get_approval_service)]
