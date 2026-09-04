from fastapi import APIRouter, Depends

from dependencies import get_current_user, verify_csrf
from routers import (
    agent,
    agent_skills,
    approvals,
    auth,
    health,
    impersonation_events,
    mcp_registry,
    mcp_servers,
    mcp_tool_certificates,
    mcp_tool_invocations,
    mcp_tool_mocks,
    metrics,
    notifications,
    outbound_emails,
    secrets,
    sessions,
    system_settings,
    tags,
    tenant,
    user,
    user_groups,
    workflow_executions,
    workflow_task_templates,
    workflow_tasks,
    workflows,
)

api_router = APIRouter(prefix="/api/v1")

#: Dependencies applied to every protected resource router: a valid session is
#: required (``get_current_user``) and state-changing requests must pass CSRF
#: validation (``verify_csrf``). The auth and health routers are intentionally
#: left unguarded so login and liveness probes work without a session.
_protected = [Depends(get_current_user), Depends(verify_csrf)]

# Public routers (no auth/CSRF guard).
api_router.include_router(auth.router)
api_router.include_router(health.router)

# Protected resource routers.
api_router.include_router(agent.router, dependencies=_protected)
api_router.include_router(agent_skills.router, dependencies=_protected)
api_router.include_router(mcp_tool_certificates.router, dependencies=_protected)
api_router.include_router(approvals.router, dependencies=_protected)
api_router.include_router(impersonation_events.router, dependencies=_protected)
api_router.include_router(mcp_registry.router, dependencies=_protected)
api_router.include_router(mcp_servers.router, dependencies=_protected)
api_router.include_router(mcp_tool_invocations.router, dependencies=_protected)
api_router.include_router(mcp_tool_mocks.router, dependencies=_protected)
api_router.include_router(metrics.router, dependencies=_protected)
api_router.include_router(notifications.router, dependencies=_protected)
api_router.include_router(outbound_emails.router, dependencies=_protected)
api_router.include_router(secrets.router, dependencies=_protected)
api_router.include_router(sessions.router, dependencies=_protected)
api_router.include_router(system_settings.router, dependencies=_protected)
api_router.include_router(tags.router, dependencies=_protected)
api_router.include_router(tenant.router, dependencies=_protected)
api_router.include_router(user.router, dependencies=_protected)
api_router.include_router(user_groups.router, dependencies=_protected)
api_router.include_router(workflow_executions.router, dependencies=_protected)
api_router.include_router(workflow_task_templates.router, dependencies=_protected)
api_router.include_router(workflow_tasks.router, dependencies=_protected)
api_router.include_router(workflows.router, dependencies=_protected)
