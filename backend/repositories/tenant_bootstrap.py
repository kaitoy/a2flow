"""Deliberately tenant-unscoped lookups.

Code that runs outside FastAPI's request-scoped DI -- the ADK agent tools in
``infrastructure/*_tools.py`` and the background jobs in
``services/workflow_planning.py`` / ``services/agent_skill_sync.py`` -- opens
its own database session and has no ``CurrentTenantIdDep`` to construct a
tenant-scoped repository with. Each entry point is handed a single opaque id
(an ADK session id set when the run was dispatched, or a bare workflow_id /
skill_id already minted inside a tenant-scoped request) and must discover
which tenant that id belongs to before any other query can be tenant-scoped.

This module is the complete, audited list of every query in the codebase that
intentionally has no tenant_id predicate. Nothing outside this module should
read a TenantScoped row without one.
"""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.agent_skill import AgentSkill
from models.planning_session import PlanningSession
from models.workflow import Workflow
from models.workflow_session import WorkflowSession


class NoTenantSessionError(Exception):
    """Raised when an agent tool's ADK session id maps to no known tenant."""


async def resolve_workflow_session_tenant(
    db: AsyncSession, session_id: str
) -> tuple[str, str] | None:
    """Return ``(workflow_session_id, tenant_id)`` for an ADK session id, or ``None``."""
    stmt = (
        select(WorkflowSession.id, WorkflowSession.tenant_id)
        .where(col(WorkflowSession.session_id) == session_id)
        .limit(1)
    )
    row = (await db.exec(stmt)).first()
    return (row[0], row[1]) if row is not None else None


async def resolve_planning_session_tenant(
    db: AsyncSession, session_id: str
) -> tuple[str, str] | None:
    """Return ``(workflow_id, tenant_id)`` for an ADK session id, or ``None``."""
    stmt = (
        select(PlanningSession.workflow_id, PlanningSession.tenant_id)
        .where(col(PlanningSession.session_id) == session_id)
        .limit(1)
    )
    row = (await db.exec(stmt)).first()
    return (row[0], row[1]) if row is not None else None


async def resolve_workflow_tenant(db: AsyncSession, workflow_id: str) -> str | None:
    """Return the tenant_id of a Workflow, or ``None`` if it does not exist."""
    stmt = select(Workflow.tenant_id).where(Workflow.id == workflow_id)
    return (await db.exec(stmt)).first()


async def resolve_agent_skill_tenant(db: AsyncSession, skill_id: str) -> str | None:
    """Return the tenant_id of an AgentSkill, or ``None`` if it does not exist."""
    stmt = select(AgentSkill.tenant_id).where(AgentSkill.id == skill_id)
    return (await db.exec(stmt)).first()
