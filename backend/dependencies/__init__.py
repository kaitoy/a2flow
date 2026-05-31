"""FastAPI dependency factories for singletons, database sessions, and repositories.

This package groups the application's dependency-injection wiring by concern:

- :mod:`dependencies.context` — request-scoped helpers and ``APP_NAME``
- :mod:`dependencies.singletons` — LRU-cached process-wide singletons
- :mod:`dependencies.repository` — per-request repositories and the DB session
- :mod:`dependencies.service` — per-request services (use cases)

All public ``*Dep`` aliases, factory functions, and ``APP_NAME`` are re-exported
here so callers can keep importing from ``dependencies`` directly.
"""

from .context import (
    APP_NAME,
    ApiMetaDep,
    CurrentUserIdDep,
    FilterDep,
    FilterParams,
    PaginationDep,
    PaginationParams,
    SortDep,
    SortParams,
    build_api_meta,
    get_current_user_id,
    parse_filters,
    parse_sort,
)
from .repository import (
    AgentSkillRepositoryDep,
    DBSessionDep,
    WorkflowRepositoryDep,
    WorkflowSessionRepositoryDep,
    WorkflowTaskRepositoryDep,
    get_agent_skill_repository,
    get_workflow_repository,
    get_workflow_session_repository,
    get_workflow_task_repository,
)
from .service import (
    AgentSkillServiceDep,
    WorkflowServiceDep,
    WorkflowSessionServiceDep,
    WorkflowTaskServiceDep,
    get_agent_skill_service,
    get_workflow_service,
    get_workflow_session_service,
    get_workflow_task_service,
)
from .singletons import (
    AgentRegistryDep,
    SessionServiceDep,
    SkillManagerDep,
    get_agent_registry,
    get_session_service,
    get_skill_manager,
)

__all__ = [
    "APP_NAME",
    "AgentRegistryDep",
    "AgentSkillRepositoryDep",
    "AgentSkillServiceDep",
    "ApiMetaDep",
    "CurrentUserIdDep",
    "DBSessionDep",
    "FilterDep",
    "FilterParams",
    "PaginationDep",
    "PaginationParams",
    "SessionServiceDep",
    "SortDep",
    "SortParams",
    "SkillManagerDep",
    "WorkflowRepositoryDep",
    "WorkflowServiceDep",
    "WorkflowSessionRepositoryDep",
    "WorkflowSessionServiceDep",
    "WorkflowTaskRepositoryDep",
    "WorkflowTaskServiceDep",
    "build_api_meta",
    "get_agent_registry",
    "get_agent_skill_repository",
    "get_agent_skill_service",
    "get_current_user_id",
    "get_session_service",
    "get_skill_manager",
    "get_workflow_repository",
    "get_workflow_service",
    "get_workflow_session_repository",
    "get_workflow_session_service",
    "get_workflow_task_repository",
    "get_workflow_task_service",
    "parse_filters",
    "parse_sort",
]
