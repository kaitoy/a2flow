"""Tests for the Approval agent tools in ``infrastructure.approval_tools``.

Like the WorkflowTask tools, these open their own ``AsyncSession`` on
``infrastructure.database.engine``; each test monkeypatches that engine to an
isolated in-memory SQLite database and drives the tools with a lightweight fake
ToolContext exposing only ``session.id`` and ``user_id``.
"""

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.approval_tools import get_approval, list_users, request_approval
from infrastructure.workflow_task_tools import create_workflow_task
from models.approval import ApprovalStatus
from models.notification import Notification, NotificationType
from models.user import Role
from models.workflow_session import WorkflowSession
from repositories import SqlApprovalRepository, SqlNotificationRepository
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users


@pytest_asyncio.fixture()
async def engine(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[AsyncEngine, None]:
    """Yield an in-memory engine and point the tools' module-level engine at it."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

    @sa_event.listens_for(eng.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await seed_users(eng, ids=())  # system user only; Tenant FKs to it
    await seed_tenant(eng)
    await seed_users(eng, tenant_id=DEFAULT_TEST_TENANT_ID)

    monkeypatch.setattr("infrastructure.database.engine", eng)
    yield eng
    await eng.dispose()


async def _seed_session(
    eng: AsyncEngine, *, session_id: str = "sess-abc", user_id: str = "owner"
) -> str:
    """Insert a WorkflowSession with the given ADK session id and return its PK."""
    async with AsyncSession(eng) as db:
        ws = WorkflowSession(
            session_id=session_id,
            workflow_name="wf",
            workflow_prompt="do it",
            agent_skill_id="skill-1",
            agent_skill_name="skill",
            agent_skill_repo_url="https://example.com/repo",
            agent_skill_repo_path=".",
            skill_dir="/tmp/skill",
            user_id=user_id,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(ws)
        await db.commit()
        await db.refresh(ws)
        return ws.id


def _ctx(session_id: str = "sess-abc", user_id: str = "owner") -> Any:
    """Build a fake ToolContext exposing ``session.id`` and ``user_id``."""
    return SimpleNamespace(session=SimpleNamespace(id=session_id), user_id=user_id)


async def _notifications_for(eng: AsyncEngine, user_id: str) -> list[Notification]:
    """Return all notifications addressed to ``user_id`` via the repository."""
    async with AsyncSession(eng) as db:
        repo = SqlNotificationRepository(db, tenant_id=DEFAULT_TEST_TENANT_ID)
        return await repo.list(user_id=user_id, limit=100, offset=0)


async def test_request_approval_creates_pending_record(engine: AsyncEngine) -> None:
    await _seed_session(engine, user_id="owner")
    result = await request_approval(
        "Deploy to prod", _ctx(), approver="alice", description="Are you sure?"
    )
    assert "error" not in result
    assert result["status"] == "pending"

    fetched = await get_approval(result["approval_id"], _ctx())
    assert fetched["title"] == "Deploy to prod"
    assert fetched["status"] == ApprovalStatus.pending.value


async def test_request_approval_notifies_approver(engine: AsyncEngine) -> None:
    await _seed_session(engine, user_id="owner")
    await request_approval(
        "Need sign-off", _ctx(), approver="alice", description="please review"
    )
    # The notification is addressed to the designated approver, not the owner.
    assert await _notifications_for(engine, "owner") == []
    notifs = await _notifications_for(engine, "alice")
    assert len(notifs) == 1
    assert notifs[0].type is NotificationType.approval_request
    assert notifs[0].title == "Need sign-off"
    assert notifs[0].user_id == "alice"


async def test_request_approval_requires_approver(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    result = await request_approval("No approver", _ctx(), approver="")
    assert "error" in result


async def test_request_approval_without_session_errors(engine: AsyncEngine) -> None:
    result = await request_approval("X", _ctx("unknown-session"), approver="alice")
    assert "error" in result


async def test_request_approval_links_valid_task(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    task = await create_workflow_task("A task", _ctx())
    result = await request_approval(
        "Approve task", _ctx(), approver="alice", workflow_task_id=task["id"]
    )
    assert "error" not in result
    fetched = await get_approval(result["approval_id"], _ctx())
    assert fetched["workflow_task_id"] == task["id"]


async def test_request_approval_records_approver(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    result = await request_approval("Approve me", _ctx(), approver="alice")
    assert "error" not in result
    fetched = await get_approval(result["approval_id"], _ctx())
    assert fetched["approver"] == "alice"


async def test_request_approval_rejects_unknown_approver(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    result = await request_approval("Approve me", _ctx(), approver="nobody")
    assert "error" in result


async def test_request_approval_rejects_foreign_task(engine: AsyncEngine) -> None:
    await _seed_session(engine, session_id="sess-a")
    await _seed_session(engine, session_id="sess-b")
    task = await create_workflow_task("In A", _ctx("sess-a"))
    result = await request_approval(
        "Approve", _ctx("sess-b"), approver="alice", workflow_task_id=task["id"]
    )
    assert "error" in result


async def test_get_approval_cross_session_guard(engine: AsyncEngine) -> None:
    await _seed_session(engine, session_id="sess-a")
    await _seed_session(engine, session_id="sess-b")
    created = await request_approval("Owned by A", _ctx("sess-a"), approver="alice")
    approval_id = created["approval_id"]

    blocked = await get_approval(approval_id, _ctx("sess-b"))
    assert "error" in blocked
    allowed = await get_approval(approval_id, _ctx("sess-a"))
    assert allowed["approval_id"] == approval_id


async def test_get_approval_reflects_resolution(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    created = await request_approval("Decide", _ctx(), approver="alice")
    # Resolve directly through the repository (the frontend's PATCH path).
    async with AsyncSession(engine) as db:
        repo = SqlApprovalRepository(db, _ws_repo(db), tenant_id=DEFAULT_TEST_TENANT_ID)
        from models.approval import ApprovalUpdate

        await repo.update(
            created["approval_id"],
            ApprovalUpdate(status=ApprovalStatus.approved, response="ok"),
            user_id="owner",
        )
    fetched = await get_approval(created["approval_id"], _ctx())
    assert fetched["status"] == ApprovalStatus.approved.value
    assert fetched["response"] == "ok"


async def test_list_users_returns_seeded_users(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    result = await list_users(_ctx())
    assert "error" not in result
    usernames = {u["username"] for u in result["users"]}
    assert {"alice", "bob", "carol", "owner", "tester"} <= usernames
    alice = next(u for u in result["users"] if u["username"] == "alice")
    assert alice["id"] == "alice"
    assert alice["email"] == "alice@test.local"
    assert set(alice) == {"id", "username", "first_name", "last_name", "email"}


async def test_list_users_excludes_system_user(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    result = await list_users(_ctx())
    from models.user import SYSTEM_USER_ID

    assert all(u["id"] != SYSTEM_USER_ID for u in result["users"])


async def test_list_users_excludes_other_tenant_users(engine: AsyncEngine) -> None:
    await seed_tenant(engine, tenant_id="tenant-other")
    await seed_users(engine, ids=("dave",), tenant_id="tenant-other")
    await _seed_session(engine)
    result = await list_users(_ctx())
    usernames = {u["username"] for u in result["users"]}
    assert "dave" not in usernames
    assert {"alice", "bob", "carol", "owner", "tester"} <= usernames


async def test_list_users_without_session_errors(engine: AsyncEngine) -> None:
    result = await list_users(_ctx("unknown-session"))
    assert "error" in result


async def test_list_users_id_usable_as_approver(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    users = await list_users(_ctx())
    approver_id = users["users"][0]["id"]
    result = await request_approval("Approve me", _ctx(), approver=approver_id)
    assert "error" not in result
    fetched = await get_approval(result["approval_id"], _ctx())
    assert fetched["approver"] == approver_id


def _ws_repo(db: AsyncSession) -> Any:
    """Build a WorkflowSession repository for the approval repository's FK check."""
    from repositories import SqlWorkflowSessionRepository

    return SqlWorkflowSessionRepository(db, tenant_id=DEFAULT_TEST_TENANT_ID)


# ---------- approver eligibility (roles) ----------


async def test_request_approval_rejects_approver_without_role(
    engine: AsyncEngine,
) -> None:
    """A user without the approver role cannot be designated as an approver."""
    await seed_users(
        engine, ids=("norole",), roles=(), tenant_id=DEFAULT_TEST_TENANT_ID
    )
    await _seed_session(engine)
    result = await request_approval("Approve me", _ctx(), approver="norole")
    assert "error" in result
    assert "approver role" in result["error"]


async def test_request_approval_rejects_super_admin_approver_without_tenant(
    engine: AsyncEngine,
) -> None:
    """A super admin cannot be designated approver for a tenant-scoped session.

    A super admin can never carry a ``tenant_id`` (see the
    ``ck_users_super_admin_no_tenant`` constraint on ``User``), so it can
    never satisfy the tenant-membership half of approver eligibility -- there
    is no platform-scoped bypass, matching ``_is_eligible_approver``'s
    "no cross-tenant bypass" rule.
    """
    await seed_users(
        engine,
        ids=("boss",),
        roles=(Role.super_admin,),
    )
    await _seed_session(engine)
    result = await request_approval("Approve me", _ctx(), approver="boss")
    assert "error" in result


async def test_request_approval_rejects_other_tenant_approver(
    engine: AsyncEngine,
) -> None:
    """An approver belonging to a different tenant cannot be designated."""
    await seed_tenant(engine, tenant_id="tenant-other")
    await seed_users(engine, ids=("dave",), tenant_id="tenant-other")
    await _seed_session(engine)
    result = await request_approval("Approve me", _ctx(), approver="dave")
    assert "error" in result


async def test_list_users_excludes_users_without_approver_role(
    engine: AsyncEngine,
) -> None:
    """The approver-selection tool omits users lacking the approver role."""
    await seed_users(
        engine, ids=("norole",), roles=(), tenant_id=DEFAULT_TEST_TENANT_ID
    )
    await _seed_session(engine)
    result = await list_users(_ctx())
    usernames = {u["username"] for u in result["users"]}
    assert "norole" not in usernames
    # The default seeded actors hold the approver role and stay listed.
    assert {"alice", "bob", "carol", "owner", "tester"} <= usernames
