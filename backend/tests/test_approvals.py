"""Tests for the approvals API (``GET``/``PATCH /api/v1/approvals``).

The list and get endpoints are unscoped (admin browsing), while ``PATCH`` records
the requesting user as the approver. Approvals reference a workflow session via a
foreign key, so each test seeds a session before inserting approvals.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from models.approval import Approval, ApprovalStatus
from models.workflow_session import WorkflowSession
from tests._envelope import assert_err, assert_ok
from tests._seed import seed_users
from tests.conftest import _install_auth_overrides


@pytest_asyncio.fixture()
async def approval_env() -> AsyncGenerator[tuple[AsyncClient, AsyncEngine], None]:
    """Yield an API client and the engine backing it, with users seeded."""
    from infrastructure.database import get_session
    from main import app

    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(mem_engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await seed_users(mem_engine)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    _install_auth_overrides(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac, mem_engine
    finally:
        app.dependency_overrides.clear()
        await mem_engine.dispose()


async def _seed_session(eng: AsyncEngine, *, user_id: str = "owner") -> str:
    """Insert a WorkflowSession and return its primary key."""
    async with AsyncSession(eng) as db:
        ws = WorkflowSession(
            session_id="sess-1",
            workflow_name="wf",
            workflow_prompt="do it",
            agent_skill_id="skill-1",
            agent_skill_name="skill",
            agent_skill_repo_url="https://example.com/repo",
            agent_skill_repo_path=".",
            skill_dir="/tmp/skill",
            user_id=user_id,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(ws)
        await db.commit()
        await db.refresh(ws)
        return ws.id


async def _insert_approval(
    eng: AsyncEngine,
    *,
    workflow_session_id: str,
    title: str = "Approve me",
    status: ApprovalStatus = ApprovalStatus.pending,
    user_id: str = "owner",
    approver: str | None = None,
) -> str:
    """Insert an Approval for the given session and return its id."""
    async with AsyncSession(eng) as db:
        approval = Approval(
            workflow_session_id=workflow_session_id,
            title=title,
            status=status,
            approver=approver,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        return approval.id


async def test_list_returns_approvals(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    ws_id = await _seed_session(eng)
    await _insert_approval(eng, workflow_session_id=ws_id, title="First")
    await _insert_approval(eng, workflow_session_id=ws_id, title="Second")

    res = await client.get("/api/v1/approvals", headers={"X-User-Id": "owner"})
    data = assert_ok(res)
    assert {a["title"] for a in data} == {"First", "Second"}


async def test_get_approval(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    ws_id = await _seed_session(eng)
    approval_id = await _insert_approval(eng, workflow_session_id=ws_id)

    res = await client.get(
        f"/api/v1/approvals/{approval_id}", headers={"X-User-Id": "owner"}
    )
    data = assert_ok(res)
    assert data["id"] == approval_id
    assert data["status"] == ApprovalStatus.pending.value


async def test_get_unknown_approval_is_404(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = approval_env
    res = await client.get(
        "/api/v1/approvals/does-not-exist", headers={"X-User-Id": "owner"}
    )
    assert_err(res, "NOT_FOUND", 404)


async def test_resolve_approval_approves(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    ws_id = await _seed_session(eng)
    approval_id = await _insert_approval(eng, workflow_session_id=ws_id)

    res = await client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"status": "approved", "response": "looks good"},
        headers={"X-User-Id": "alice"},
    )
    data = assert_ok(res)
    assert data["status"] == ApprovalStatus.approved.value
    assert data["response"] == "looks good"
    # The approver is recorded in the audit field.
    assert data["updatedBy"] == "alice"


async def test_resolve_keeps_designated_approver(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    ws_id = await _seed_session(eng)
    approval_id = await _insert_approval(eng, workflow_session_id=ws_id, approver="bob")

    res = await client.get(
        f"/api/v1/approvals/{approval_id}", headers={"X-User-Id": "owner"}
    )
    assert assert_ok(res)["approver"] == "bob"

    # Resolving by a different user does not change the designated approver.
    res = await client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"status": "approved"},
        headers={"X-User-Id": "alice"},
    )
    data = assert_ok(res)
    assert data["approver"] == "bob"
    assert data["updatedBy"] == "alice"


async def test_resolve_unknown_approval_is_404(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = approval_env
    res = await client.patch(
        "/api/v1/approvals/missing",
        json={"status": "rejected"},
        headers={"X-User-Id": "alice"},
    )
    assert_err(res, "NOT_FOUND", 404)
