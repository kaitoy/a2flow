from fastapi import APIRouter, Depends

from dependencies import get_current_user, verify_csrf
from routers import (
    agent,
    agent_skills,
    approvals,
    auth,
    health,
    mcp_registry,
    mcp_servers,
    notifications,
    planning_sessions,
    secrets,
    sessions,
    tenant,
    user,
    workflow_sessions,
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
api_router.include_router(approvals.router, dependencies=_protected)
api_router.include_router(mcp_registry.router, dependencies=_protected)
api_router.include_router(mcp_servers.router, dependencies=_protected)
api_router.include_router(notifications.router, dependencies=_protected)
api_router.include_router(planning_sessions.router, dependencies=_protected)
api_router.include_router(secrets.router, dependencies=_protected)
api_router.include_router(sessions.router, dependencies=_protected)
api_router.include_router(tenant.router, dependencies=_protected)
api_router.include_router(user.router, dependencies=_protected)
api_router.include_router(workflow_sessions.router, dependencies=_protected)
api_router.include_router(workflow_task_templates.router, dependencies=_protected)
api_router.include_router(workflow_tasks.router, dependencies=_protected)
api_router.include_router(workflows.router, dependencies=_protected)
