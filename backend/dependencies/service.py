"""Per-request service (use case) dependencies wiring repositories and singletons.

Each service is constructed from the request-scoped repositories it operates on,
plus any singletons it needs (the skill manager, the agent registry). These are
the dependencies routers inject to invoke business logic.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends

from infrastructure.secret_resolver import SecretResolver
from services import (
    AgentSkillService,
    ApprovalService,
    MCPRegistryService,
    MCPServerService,
    NotificationService,
    SecretService,
    TenantService,
    UserAvatarService,
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
    AgentSkillRepositoryDep,
    ApprovalRepositoryDep,
    MCPServerRepositoryDep,
    MessageMetaRepositoryDep,
    NotificationRepositoryDep,
    SecretRepositoryDep,
    TenantRepositoryDep,
    UserAvatarRepositoryDep,
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
    repo: AgentSkillRepositoryDep, secrets: SecretRepositoryDep
) -> AgentSkillService:
    """Create an AgentSkillService backed by the request's repositories."""
    return AgentSkillService(repo, secrets)


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


def get_mcp_server_service(
    repo: MCPServerRepositoryDep, resolver: SecretResolverDep
) -> MCPServerService:
    """Create an MCPServerService backed by the request's repository and resolver."""
    return MCPServerService(repo, resolver)


MCPServerServiceDep = Annotated[MCPServerService, Depends(get_mcp_server_service)]


def get_mcp_registry_service() -> MCPRegistryService:
    """Create an MCPRegistryService for official-registry discovery."""
    return MCPRegistryService()


MCPRegistryServiceDep = Annotated[MCPRegistryService, Depends(get_mcp_registry_service)]


def get_notification_service(repo: NotificationRepositoryDep) -> NotificationService:
    """Create a NotificationService backed by the request's repository."""
    return NotificationService(repo)


NotificationServiceDep = Annotated[
    NotificationService, Depends(get_notification_service)
]


def get_tenant_service(repo: TenantRepositoryDep) -> TenantService:
    """Create a TenantService backed by the request's repository."""
    return TenantService(repo)


TenantServiceDep = Annotated[TenantService, Depends(get_tenant_service)]


def get_user_service(repo: UserRepositoryDep) -> UserService:
    """Create a UserService backed by the request's repository."""
    return UserService(repo)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


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


def get_workflow_execution_access_policy(
    approvals: ApprovalRepositoryDep,
) -> WorkflowExecutionAccessPolicy:
    """Create the access policy for workflow-execution-scoped operations."""
    return WorkflowExecutionAccessPolicy(approvals)


WorkflowExecutionAccessPolicyDep = Annotated[
    WorkflowExecutionAccessPolicy, Depends(get_workflow_execution_access_policy)
]


def get_workflow_execution_service(
    execution_repo: WorkflowExecutionRepositoryDep,
    tasks: WorkflowTaskRepositoryDep,
    meta: MessageMetaRepositoryDep,
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


def get_workflow_task_service(
    repo: WorkflowTaskRepositoryDep,
    execution_repo: WorkflowExecutionRepositoryDep,
    access: WorkflowExecutionAccessPolicyDep,
    approvals: ApprovalRepositoryDep,
) -> WorkflowTaskService:
    """Create a WorkflowTaskService wiring the task, session, and approval repositories and the access policy."""
    return WorkflowTaskService(repo, execution_repo, access, approvals)


WorkflowTaskServiceDep = Annotated[
    WorkflowTaskService, Depends(get_workflow_task_service)
]


def get_workflow_task_template_service(
    repo: WorkflowTaskTemplateRepositoryDep,
    workflows: WorkflowRepositoryDep,
) -> WorkflowTaskTemplateService:
    """Create a WorkflowTaskTemplateService wiring the template and workflow repositories."""
    return WorkflowTaskTemplateService(repo, workflows)


WorkflowTaskTemplateServiceDep = Annotated[
    WorkflowTaskTemplateService, Depends(get_workflow_task_template_service)
]


def get_approval_service(repo: ApprovalRepositoryDep) -> ApprovalService:
    """Create an ApprovalService backed by the request's repository."""
    return ApprovalService(repo)


ApprovalServiceDep = Annotated[ApprovalService, Depends(get_approval_service)]
