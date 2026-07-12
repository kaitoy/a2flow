"""Access-control tests for workflow-session-scoped operations.

Every operation on a workflow session (get, messages, task listing, agent
stream, task CRUD) is restricted to the session owner, the designated
approvers of the session's approvals, and super admins; deletion is stricter
(owner or super admin only). The auth test stub reads roles from the
``X-User-Roles`` header (defaulting to ``super_admin``), so these tests pass
explicit role headers to model each participant.
"""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

import pytest_asyncio
from google.adk.sessions import InMemorySessionService
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from models.agent_skill import AgentSkill, SkillSyncStatus
from models.approval import Approval, ApprovalStatus
from models.workflow_session import WorkflowSession
from tests._envelope import assert_err, assert_ok
from tests._seed import seed_users
from tests.conftest import FAKE_COMMIT_SHA, _install_auth_overrides

#: Headers modeling the session owner without any role.
OWNER = {"X-User-Id": "owner", "X-User-Roles": ""}
#: Headers modeling a designated approver (see :func:`_insert_approval`).
APPROVER = {"X-User-Id": "carol", "X-User-Roles": "approver"}
#: Headers modeling an unrelated authenticated user holding non-admin roles.
UNRELATED = {"X-User-Id": "bob", "X-User-Roles": "developer,requester,approver"}
#: Headers modeling an unrelated super admin.
SUPER_ADMIN = {"X-User-Id": "alice", "X-User-Roles": "super_admin"}


#: Id and published revision of the AgentSkill every seeded session references.
SKILL_ID = "skill-1"


async def _seed_skill(eng: AsyncEngine) -> None:
    """Insert the AgentSkill the seeded sessions run on, with a published revision.

    ``resolve_agent`` reads the skill to locate its revision directory, so the
    agent-stream tests need a real row rather than a dangling id.
    """
    async with AsyncSession(eng) as db:
        db.add(
            AgentSkill(
                id=SKILL_ID,
                name="skill",
                repo_url="https://example.com/repo",
                repo_path="",
                sync_status=SkillSyncStatus.ready,
                commit_sha=FAKE_COMMIT_SHA,
                created_by="owner",
                updated_by="owner",
            )
        )
        await db.commit()


@pytest_asyncio.fixture()
async def access_env(
    mock_agent_registry: MagicMock,
    mock_skill_manager: MagicMock,
    real_session_service: InMemorySessionService,
) -> AsyncGenerator[tuple[AsyncClient, AsyncEngine], None]:
    """Yield an API client and its engine, with users seeded and agents mocked."""
    from dependencies import get_agent_registry, get_session_service, get_skill_manager
    from infrastructure.database import get_session
    from main import app

    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(mem_engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await seed_users(mem_engine)
    await _seed_skill(mem_engine)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_agent_registry] = lambda: mock_agent_registry
    app.dependency_overrides[get_session_service] = lambda: real_session_service
    app.dependency_overrides[get_skill_manager] = lambda: mock_skill_manager
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
    """Insert a WorkflowSession owned by ``user_id`` and return its primary key."""
    async with AsyncSession(eng) as db:
        ws = WorkflowSession(
            session_id="sess-1",
            workflow_name="wf",
            workflow_prompt="do it",
            agent_skill_id=SKILL_ID,
            agent_skill_name="skill",
            agent_skill_repo_url="https://example.com/repo",
            agent_skill_repo_path="",
            agent_skill_commit_sha=FAKE_COMMIT_SHA,
            user_id=user_id,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(ws)
        await db.commit()
        await db.refresh(ws)
        return ws.id


async def _insert_approval(
    eng: AsyncEngine, *, workflow_session_id: str, approver: str = "carol"
) -> str:
    """Insert a pending Approval addressed to ``approver`` and return its id."""
    async with AsyncSession(eng) as db:
        approval = Approval(
            workflow_session_id=workflow_session_id,
            title="Approve me",
            status=ApprovalStatus.pending,
            approver=approver,
            created_by="owner",
            updated_by="owner",
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        return approval.id


async def _create_task(client: AsyncClient, ws_id: str, headers: dict[str, str]) -> Any:
    """POST a WorkflowTask into the session and return the raw response."""
    return await client.post(
        "/api/v1/workflow-tasks",
        json={"workflowSessionId": ws_id, "title": "Step 1"},
        headers=headers,
    )


def _run_agent_input() -> dict[str, Any]:
    """Build a minimal RunAgentInput payload for the agent stream endpoint."""
    return {
        "threadId": "thread-001",
        "runId": "run-001",
        "state": {},
        "messages": [],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }


# ---------- session read access ----------


async def test_owner_without_roles_can_get_session(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    ws_id = await _seed_session(eng)
    assert_ok(await client.get(f"/api/v1/workflow-sessions/{ws_id}", headers=OWNER))


async def test_unrelated_user_cannot_get_session(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    ws_id = await _seed_session(eng)
    res = await client.get(f"/api/v1/workflow-sessions/{ws_id}", headers=UNRELATED)
    assert_err(res, "FORBIDDEN", 403)


async def test_designated_approver_can_get_session(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    ws_id = await _seed_session(eng)
    await _insert_approval(eng, workflow_session_id=ws_id, approver="carol")
    assert_ok(await client.get(f"/api/v1/workflow-sessions/{ws_id}", headers=APPROVER))


async def test_approver_of_other_session_cannot_get_session(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    ws_id = await _seed_session(eng)
    other_ws = await _seed_session(eng)
    # carol approves in *another* session only.
    await _insert_approval(eng, workflow_session_id=other_ws, approver="carol")
    res = await client.get(f"/api/v1/workflow-sessions/{ws_id}", headers=APPROVER)
    assert_err(res, "FORBIDDEN", 403)


async def test_super_admin_can_get_any_session(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    ws_id = await _seed_session(eng)
    assert_ok(
        await client.get(f"/api/v1/workflow-sessions/{ws_id}", headers=SUPER_ADMIN)
    )


async def test_missing_session_is_404_even_for_unrelated_user(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = access_env
    res = await client.get("/api/v1/workflow-sessions/nonexistent", headers=UNRELATED)
    assert_err(res, "NOT_FOUND", 404)


async def test_session_list_stays_open(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    await _seed_session(eng)
    assert_ok(await client.get("/api/v1/workflow-sessions", headers=UNRELATED))


# ---------- messages / tasks / agent ----------


async def test_unrelated_user_cannot_get_messages(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    ws_id = await _seed_session(eng)
    res = await client.get(
        f"/api/v1/workflow-sessions/{ws_id}/messages", headers=UNRELATED
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_approver_can_get_messages(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    ws_id = await _seed_session(eng)
    await _insert_approval(eng, workflow_session_id=ws_id)
    assert_ok(
        await client.get(
            f"/api/v1/workflow-sessions/{ws_id}/messages", headers=APPROVER
        )
    )


async def test_unrelated_user_cannot_list_session_tasks(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    ws_id = await _seed_session(eng)
    res = await client.get(
        f"/api/v1/workflow-sessions/{ws_id}/workflow-tasks", headers=UNRELATED
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_unrelated_user_cannot_stream_agent(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    ws_id = await _seed_session(eng)
    res = await client.post(
        f"/api/v1/workflow-sessions/{ws_id}/agent",
        json=_run_agent_input(),
        headers=UNRELATED,
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_approver_can_stream_agent(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    ws_id = await _seed_session(eng)
    await _insert_approval(eng, workflow_session_id=ws_id)
    res = await client.post(
        f"/api/v1/workflow-sessions/{ws_id}/agent",
        json=_run_agent_input(),
        headers=APPROVER,
    )
    assert res.status_code == 200


# ---------- task CRUD ----------


async def test_unrelated_user_cannot_create_task(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    ws_id = await _seed_session(eng)
    assert_err(await _create_task(client, ws_id, UNRELATED), "FORBIDDEN", 403)


async def test_approver_can_create_and_update_task(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    ws_id = await _seed_session(eng)
    await _insert_approval(eng, workflow_session_id=ws_id)
    task = assert_ok(await _create_task(client, ws_id, APPROVER), status=201)
    res = await client.patch(
        f"/api/v1/workflow-tasks/{task['id']}",
        json={"status": "in_progress"},
        headers=APPROVER,
    )
    assert_ok(res)


async def test_unrelated_user_cannot_read_or_delete_task(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    ws_id = await _seed_session(eng)
    task = assert_ok(await _create_task(client, ws_id, OWNER), status=201)
    res = await client.get(f"/api/v1/workflow-tasks/{task['id']}", headers=UNRELATED)
    assert_err(res, "FORBIDDEN", 403)
    res = await client.delete(f"/api/v1/workflow-tasks/{task['id']}", headers=UNRELATED)
    assert_err(res, "FORBIDDEN", 403)


# ---------- deletion is owner-or-super-admin only ----------


async def test_approver_cannot_delete_session(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    ws_id = await _seed_session(eng)
    await _insert_approval(eng, workflow_session_id=ws_id)
    res = await client.delete(f"/api/v1/workflow-sessions/{ws_id}", headers=APPROVER)
    assert_err(res, "FORBIDDEN", 403)


async def test_owner_can_delete_session(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    ws_id = await _seed_session(eng)
    assert_ok(await client.delete(f"/api/v1/workflow-sessions/{ws_id}", headers=OWNER))


async def test_super_admin_can_delete_session(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    ws_id = await _seed_session(eng)
    assert_ok(
        await client.delete(f"/api/v1/workflow-sessions/{ws_id}", headers=SUPER_ADMIN)
    )
