from fastapi import APIRouter

from routers import agent, agent_skills, health, sessions, workflow_sessions, workflows

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(agent.router)
api_router.include_router(agent_skills.router)
api_router.include_router(sessions.router)
api_router.include_router(workflow_sessions.router)
api_router.include_router(workflows.router)
api_router.include_router(health.router)
