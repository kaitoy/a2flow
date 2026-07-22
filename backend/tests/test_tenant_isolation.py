"""Repository-level tenant isolation tests.

Seeds two tenants, one row of every ``TenantScoped`` entity per tenant, and
asserts that a repository scoped to tenant A cannot read, list, or mutate
tenant B's rows. This is the fast, comprehensive regression net for the
enforcement added across ``repositories/*.py`` -- it exercises the repository
layer directly (no HTTP, no agent tools), so a gap here means the `_get_scoped`
predicate is missing or wrong on that repository, independent of which caller
(router or agent tool) would have been affected.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from models.agent_skill import AgentSkillCreate
from models.approval import ApprovalCreate
from models.mcp_server import MCPServerCreate
from models.notification import NotificationCreate, NotificationType
from models.planning_session import PlanningSessionCreate
from models.secret import SecretCreate, SecretType
from models.workflow import WorkflowCreate
from models.workflow_session import WorkflowSessionCreate
from models.workflow_task import WorkflowTaskCreate
from models.workflow_task_template import WorkflowTaskTemplateCreate
from repositories import (
    SqlAgentSkillRepository,
    SqlApprovalRepository,
    SqlMCPServerRepository,
    SqlMessageMetaRepository,
    SqlNotificationRepository,
    SqlPlanningSessionRepository,
    SqlSecretRepository,
    SqlWorkflowRepository,
    SqlWorkflowSessionRepository,
    SqlWorkflowTaskRepository,
    SqlWorkflowTaskTemplateRepository,
)
from repositories.exceptions import NotFoundError
from tests._seed import seed_tenant, seed_users

TENANT_A = "tenant-isolation-a"
TENANT_B = "tenant-isolation-b"


@pytest_asyncio.fixture()
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Yield an in-memory engine with two tenants and the default test users seeded."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(eng.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await seed_users(eng)
    await seed_tenant(eng, TENANT_A)
    await seed_tenant(eng, TENANT_B)
    yield eng
    await eng.dispose()


class _Rows:
    """The id of one seeded row of each TenantScoped entity, for one tenant."""

    def __init__(self) -> None:
        self.agent_skill = ""
        self.mcp_server = ""
        self.secret = ""
        self.workflow = ""
        self.workflow_session = ""
        self.workflow_task = ""
        self.approval = ""
        self.notification = ""
        self.planning_session = ""
        self.workflow_task_template = ""
        self.message_meta_event_id = ""


async def _seed_tenant_rows(db: AsyncSession, tenant_id: str, *, suffix: str) -> _Rows:
    """Create one row of every TenantScoped entity, scoped to ``tenant_id``."""
    rows = _Rows()

    skills = SqlAgentSkillRepository(db, tenant_id=tenant_id)
    skill = await skills.create(
        AgentSkillCreate(name=f"skill-{suffix}", repo_url="https://example.com/repo"),
        user_id="owner",
    )
    rows.agent_skill = skill.id

    mcp = SqlMCPServerRepository(db, tenant_id=tenant_id)
    server = await mcp.create(
        MCPServerCreate(name=f"srv-{suffix}", url="https://mcp.example.com/mcp"),
        user_id="owner",
    )
    rows.mcp_server = server.id

    secrets = SqlSecretRepository(db, tenant_id=tenant_id)
    secret = await secrets.create(
        SecretCreate(
            name=f"secret-{suffix}", type=SecretType.local, value="ciphertext"
        ),
        user_id="owner",
    )
    rows.secret = secret.id

    workflows = SqlWorkflowRepository(db, skills, tenant_id=tenant_id)
    workflow = await workflows.create(
        WorkflowCreate(name=f"wf-{suffix}", agent_skill_id=skill.id), user_id="owner"
    )
    rows.workflow = workflow.id

    ws_repo = SqlWorkflowSessionRepository(db, tenant_id=tenant_id)
    ws = await ws_repo.create(
        WorkflowSessionCreate(
            session_id=f"sess-{suffix}",
            workflow_name=workflow.name,
            agent_skill_id=skill.id,
            agent_skill_name=skill.name,
            agent_skill_repo_url=str(skill.repo_url),
            agent_skill_repo_path=skill.repo_path,
            user_id="owner",
        ),
        workflow_id=workflow.id,
        user_id="owner",
    )
    rows.workflow_session = ws.id

    tasks = SqlWorkflowTaskRepository(db, ws_repo, mcp, tenant_id=tenant_id)
    task = await tasks.create(
        WorkflowTaskCreate(workflow_session_id=ws.id, title=f"task-{suffix}"),
        user_id="owner",
    )
    rows.workflow_task = task.id

    approvals = SqlApprovalRepository(db, ws_repo, tenant_id=tenant_id)
    approval = await approvals.create(
        ApprovalCreate(workflow_session_id=ws.id, title=f"approve-{suffix}"),
        user_id="owner",
    )
    rows.approval = approval.id

    notifications = SqlNotificationRepository(db, tenant_id=tenant_id)
    notification = await notifications.create(
        NotificationCreate(
            user_id="owner",
            type=NotificationType.approval_request,
            title=f"notif-{suffix}",
        ),
        user_id="owner",
    )
    rows.notification = notification.id

    planning_sessions = SqlPlanningSessionRepository(db, tenant_id=tenant_id)
    ps = await planning_sessions.create(
        PlanningSessionCreate(
            session_id=f"plan-{suffix}",
            workflow_id=workflow.id,
            agent_skill_id=skill.id,
            agent_skill_commit_sha="a" * 40,
            user_id="owner",
        ),
        user_id="owner",
    )
    rows.planning_session = ps.id

    templates = SqlWorkflowTaskTemplateRepository(
        db, workflows, mcp, tenant_id=tenant_id
    )
    template = await templates.create(
        WorkflowTaskTemplateCreate(workflow_id=workflow.id, title=f"template-{suffix}"),
        user_id="owner",
    )
    rows.workflow_task_template = template.id

    meta = SqlMessageMetaRepository(db, tenant_id=tenant_id)
    rows.message_meta_event_id = f"event-{suffix}"
    await meta.set_sender(
        workflow_session_id=ws.id,
        adk_event_id=rows.message_meta_event_id,
        sender_user_id="owner",
    )

    return rows


@pytest_asyncio.fixture()
async def seeded(engine: AsyncEngine) -> tuple[_Rows, _Rows]:
    """Seed one row of every entity in each tenant and return their ids."""
    async with AsyncSession(engine, expire_on_commit=False) as db:
        a = await _seed_tenant_rows(db, TENANT_A, suffix="a")
        b = await _seed_tenant_rows(db, TENANT_B, suffix="b")
        return a, b


async def test_agent_skill_isolation(
    engine: AsyncEngine, seeded: tuple[_Rows, _Rows]
) -> None:
    a, b = seeded
    async with AsyncSession(engine, expire_on_commit=False) as db:
        repo_a = SqlAgentSkillRepository(db, tenant_id=TENANT_A)
        assert await repo_a.get(b.agent_skill) is None
        assert await repo_a.exists(b.agent_skill) is False
        listed = await repo_a.list(limit=100, offset=0)
        assert b.agent_skill not in {r.id for r in listed}
        with pytest.raises(NotFoundError):
            await repo_a.delete(b.agent_skill)


async def test_mcp_server_isolation(
    engine: AsyncEngine, seeded: tuple[_Rows, _Rows]
) -> None:
    a, b = seeded
    async with AsyncSession(engine, expire_on_commit=False) as db:
        repo_a = SqlMCPServerRepository(db, tenant_id=TENANT_A)
        assert await repo_a.get(b.mcp_server) is None
        assert await repo_a.exists(b.mcp_server) is False
        listed = await repo_a.list(limit=100, offset=0)
        assert b.mcp_server not in {r.id for r in listed}
        with pytest.raises(NotFoundError):
            await repo_a.delete(b.mcp_server)


async def test_secret_isolation(
    engine: AsyncEngine, seeded: tuple[_Rows, _Rows]
) -> None:
    a, b = seeded
    async with AsyncSession(engine, expire_on_commit=False) as db:
        repo_a = SqlSecretRepository(db, tenant_id=TENANT_A)
        assert await repo_a.get(b.secret) is None
        assert await repo_a.exists(b.secret) is False
        # By-name lookup must not cross tenants either, even with a name collision.
        assert await repo_a.get_by_name("secret-b") is None
        listed = await repo_a.list(limit=100, offset=0)
        assert b.secret not in {r.id for r in listed}
        with pytest.raises(NotFoundError):
            await repo_a.delete(b.secret)


async def test_workflow_isolation(
    engine: AsyncEngine, seeded: tuple[_Rows, _Rows]
) -> None:
    a, b = seeded
    async with AsyncSession(engine, expire_on_commit=False) as db:
        skills_a = SqlAgentSkillRepository(db, tenant_id=TENANT_A)
        repo_a = SqlWorkflowRepository(db, skills_a, tenant_id=TENANT_A)
        assert await repo_a.get(b.workflow) is None
        listed = await repo_a.list(limit=100, offset=0)
        assert b.workflow not in {r.id for r in listed}
        with pytest.raises(NotFoundError):
            await repo_a.delete(b.workflow)


async def test_workflow_session_isolation(
    engine: AsyncEngine, seeded: tuple[_Rows, _Rows]
) -> None:
    a, b = seeded
    async with AsyncSession(engine, expire_on_commit=False) as db:
        repo_a = SqlWorkflowSessionRepository(db, tenant_id=TENANT_A)
        assert await repo_a.get(b.workflow_session) is None
        # get_by_session_id must not resolve another tenant's ADK session id.
        assert await repo_a.get_by_session_id("sess-b") is None
        listed = await repo_a.list(limit=100, offset=0)
        assert b.workflow_session not in {r.id for r in listed}
        with pytest.raises(NotFoundError):
            await repo_a.delete(b.workflow_session)


async def test_workflow_task_isolation(
    engine: AsyncEngine, seeded: tuple[_Rows, _Rows]
) -> None:
    a, b = seeded
    async with AsyncSession(engine, expire_on_commit=False) as db:
        ws_repo_a = SqlWorkflowSessionRepository(db, tenant_id=TENANT_A)
        mcp_a = SqlMCPServerRepository(db, tenant_id=TENANT_A)
        repo_a = SqlWorkflowTaskRepository(db, ws_repo_a, mcp_a, tenant_id=TENANT_A)
        assert await repo_a.get(b.workflow_task) is None
        listed = await repo_a.list(limit=100, offset=0)
        assert b.workflow_task not in {t.id for t in listed}
        with pytest.raises(NotFoundError):
            await repo_a.delete(b.workflow_task)


async def test_approval_isolation(
    engine: AsyncEngine, seeded: tuple[_Rows, _Rows]
) -> None:
    a, b = seeded
    async with AsyncSession(engine, expire_on_commit=False) as db:
        ws_repo_a = SqlWorkflowSessionRepository(db, tenant_id=TENANT_A)
        repo_a = SqlApprovalRepository(db, ws_repo_a, tenant_id=TENANT_A)
        assert await repo_a.get(b.approval) is None
        assert await repo_a.exists(b.approval) is False
        listed = await repo_a.list(limit=100, offset=0)
        assert b.approval not in {r.id for r in listed}


async def test_notification_isolation(
    engine: AsyncEngine, seeded: tuple[_Rows, _Rows]
) -> None:
    """Same recipient (``owner``) in both tenants -- isolation must still hold."""
    a, b = seeded
    async with AsyncSession(engine, expire_on_commit=False) as db:
        repo_a = SqlNotificationRepository(db, tenant_id=TENANT_A)
        assert await repo_a.get(b.notification) is None
        listed = await repo_a.list(user_id="owner", limit=100, offset=0)
        assert b.notification not in {n.id for n in listed}
        assert a.notification in {n.id for n in listed}
        with pytest.raises(NotFoundError):
            await repo_a.delete(b.notification)


async def test_planning_session_isolation(
    engine: AsyncEngine, seeded: tuple[_Rows, _Rows]
) -> None:
    a, b = seeded
    async with AsyncSession(engine, expire_on_commit=False) as db:
        repo_a = SqlPlanningSessionRepository(db, tenant_id=TENANT_A)
        assert await repo_a.get(b.planning_session) is None
        assert await repo_a.get_by_session_id("plan-b") is None
        assert await repo_a.get_by_workflow_id(b.workflow) is None
        with pytest.raises(NotFoundError):
            await repo_a.delete(b.planning_session)


async def test_workflow_task_template_isolation(
    engine: AsyncEngine, seeded: tuple[_Rows, _Rows]
) -> None:
    a, b = seeded
    async with AsyncSession(engine, expire_on_commit=False) as db:
        skills_a = SqlAgentSkillRepository(db, tenant_id=TENANT_A)
        workflows_a = SqlWorkflowRepository(db, skills_a, tenant_id=TENANT_A)
        mcp_a = SqlMCPServerRepository(db, tenant_id=TENANT_A)
        repo_a = SqlWorkflowTaskTemplateRepository(
            db, workflows_a, mcp_a, tenant_id=TENANT_A
        )
        assert await repo_a.get(b.workflow_task_template) is None
        listed = await repo_a.list(limit=100, offset=0)
        assert b.workflow_task_template not in {t.id for t in listed}
        with pytest.raises(NotFoundError):
            await repo_a.delete(b.workflow_task_template)


async def test_message_meta_isolation(
    engine: AsyncEngine, seeded: tuple[_Rows, _Rows]
) -> None:
    a, b = seeded
    async with AsyncSession(engine, expire_on_commit=False) as db:
        repo_a = SqlMessageMetaRepository(db, tenant_id=TENANT_A)
        # Tenant A's repo, queried against tenant B's workflow_session_id, must
        # see no metadata rows even though the row itself exists in tenant B.
        assert await repo_a.meta_for_session(b.workflow_session) == {}
        own = await repo_a.meta_for_session(a.workflow_session)
        assert a.message_meta_event_id in own
