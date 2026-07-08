"""Per-request service (use case) dependencies wiring repositories and singletons.

Each service is constructed from the request-scoped repositories it operates on,
plus any singletons it needs (the skill manager, the agent registry). These are
the dependencies routers inject to invoke business logic.
"""

from typing import Annotated

from fastapi import Depends

from infrastructure.secret_resolver import SecretResolver
from services import (
    AgentSkillService,
    ApprovalService,
    AuthService,
    MCPRegistryService,
    MCPServerService,
    NotificationService,
    SecretService,
    UserAvatarService,
    UserService,
    WorkflowService,
    WorkflowSessionService,
    WorkflowTaskService,
)

from .context import APP_NAME
from .repository import (
    AgentSkillRepositoryDep,
    ApprovalRepositoryDep,
    AuthSessionRepositoryDep,
    MCPServerRepositoryDep,
    MessageMetaRepositoryDep,
    NotificationRepositoryDep,
    SecretRepositoryDep,
    UserAvatarRepositoryDep,
    UserRepositoryDep,
    WorkflowRepositoryDep,
    WorkflowSessionRepositoryDep,
    WorkflowTaskRepositoryDep,
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


def get_auth_service(
    users: UserRepositoryDep,
    sessions: AuthSessionRepositoryDep,
) -> AuthService:
    """Create an AuthService wiring the user and auth-session repositories."""
    return AuthService(users, sessions)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_secret_service(
    repo: SecretRepositoryDep, cipher: SecretCipherDep
) -> SecretService:
    """Create a SecretService wiring the repository and the cipher singleton."""
    return SecretService(repo, cipher)


SecretServiceDep = Annotated[SecretService, Depends(get_secret_service)]


def get_secret_resolver(
    repo: SecretRepositoryDep,
    cipher: SecretCipherDep,
    vault: VaultClientDep,
) -> SecretResolver:
    """Create a SecretResolver wiring the repository, cipher, and optional Vault client."""
    return SecretResolver(repo, cipher, vault)


SecretResolverDep = Annotated[SecretResolver, Depends(get_secret_resolver)]


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
    skill_manager: SkillManagerDep,
    ws_repo: WorkflowSessionRepositoryDep,
    resolver: SecretResolverDep,
) -> WorkflowService:
    """Create a WorkflowService wiring the repositories, SkillManager, and resolver."""
    return WorkflowService(workflows, skills, skill_manager, ws_repo, resolver)


WorkflowServiceDep = Annotated[WorkflowService, Depends(get_workflow_service)]


def get_workflow_session_service(
    ws_repo: WorkflowSessionRepositoryDep,
    tasks: WorkflowTaskRepositoryDep,
    meta: MessageMetaRepositoryDep,
    registry: AgentRegistryDep,
    session_service: SessionServiceDep,
) -> WorkflowSessionService:
    """Create a WorkflowSessionService wiring the repositories, agent registry, and session store."""
    return WorkflowSessionService(
        ws_repo, tasks, meta, registry, session_service, APP_NAME
    )


WorkflowSessionServiceDep = Annotated[
    WorkflowSessionService, Depends(get_workflow_session_service)
]


def get_workflow_task_service(repo: WorkflowTaskRepositoryDep) -> WorkflowTaskService:
    """Create a WorkflowTaskService backed by the request's repository."""
    return WorkflowTaskService(repo)


WorkflowTaskServiceDep = Annotated[
    WorkflowTaskService, Depends(get_workflow_task_service)
]


def get_approval_service(repo: ApprovalRepositoryDep) -> ApprovalService:
    """Create an ApprovalService backed by the request's repository."""
    return ApprovalService(repo)


ApprovalServiceDep = Annotated[ApprovalService, Depends(get_approval_service)]
