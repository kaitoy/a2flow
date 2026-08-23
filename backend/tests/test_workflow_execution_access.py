"""Access-control tests for workflow-execution-scoped operations.

Every operation on a workflow execution (get, list, messages, task listing,
agent stream, task CRUD) is restricted to the execution initiator, the
designated approvers of the session's approvals, and super admins; deletion is
stricter (owner or super admin only). A plain admin gets the same access as a
super admin for the read-only operations (get, list, messages, task listing,
reading a single task) but not for the ones that act (agent stream, task
create/update/delete, deletion) -- see ``services/workflow_execution_access.py``.
The auth test stub reads roles from the ``X-User-Roles`` header (defaulting to
``super_admin``), so these tests pass explicit role headers to model each
participant.
"""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from google.adk.sessions import InMemorySessionService
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from models.agent_skill import AgentSkill, SkillSyncStatus
from models.approval import Approval, ApprovalStatus
from models.user_group import UserGroup, UserGroupMember
from models.workflow_execution import WorkflowExecution
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users
from tests.conftest import FAKE_COMMIT_SHA, _install_auth_overrides

#: Headers modeling the execution initiator without any role.
OWNER = {"X-User-Id": "owner", "X-User-Roles": ""}
#: Headers modeling a designated approver (see :func:`_insert_approval`).
APPROVER = {"X-User-Id": "carol", "X-User-Roles": "approver"}
#: Headers modeling an unrelated authenticated user holding non-admin roles.
UNRELATED = {"X-User-Id": "bob", "X-User-Roles": "developer,requester,approver"}
#: Headers modeling an unrelated super admin.
SUPER_ADMIN = {"X-User-Id": "alice", "X-User-Roles": "super_admin"}
#: Headers modeling an unrelated plain admin (read-only bypass, no action bypass).
ADMIN = {"X-User-Id": "dave", "X-User-Roles": "admin"}


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
                tenant_id=DEFAULT_TEST_TENANT_ID,
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
    await seed_tenant(mem_engine)
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
    """Insert a WorkflowExecution owned by ``user_id`` and return its primary key."""
    async with AsyncSession(eng) as db:
        execution = WorkflowExecution(
            session_id="sess-1",
            name="wf",
            workflow_prompt="do it",
            agent_skill_id=SKILL_ID,
            agent_skill_name="skill",
            agent_skill_repo_url="https://example.com/repo",
            agent_skill_repo_path="",
            agent_skill_commit_sha=FAKE_COMMIT_SHA,
            initiator_id=user_id,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)
        return execution.id


async def _insert_approval(
    eng: AsyncEngine,
    *,
    workflow_execution_id: str,
    approver: str = "carol",
    status: ApprovalStatus = ApprovalStatus.pending,
) -> str:
    """Insert an Approval addressed to ``approver`` and return its id."""
    async with AsyncSession(eng) as db:
        approval = Approval(
            workflow_execution_id=workflow_execution_id,
            title="Approve me",
            status=status,
            approver=approver,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by="owner",
            updated_by="owner",
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        return approval.id


async def _create_task(
    client: AsyncClient, execution_id: str, headers: dict[str, str]
) -> Any:
    """POST a WorkflowTask into the session and return the raw response."""
    return await client.post(
        "/api/v1/workflow-tasks",
        json={"workflowExecutionId": execution_id, "title": "Step 1"},
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
    execution_id = await _seed_session(eng)
    assert_ok(
        await client.get(f"/api/v1/workflow-executions/{execution_id}", headers=OWNER)
    )


async def test_unrelated_user_cannot_get_session(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    res = await client.get(
        f"/api/v1/workflow-executions/{execution_id}", headers=UNRELATED
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_designated_approver_can_get_session(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    await _insert_approval(eng, workflow_execution_id=execution_id, approver="carol")
    assert_ok(
        await client.get(
            f"/api/v1/workflow-executions/{execution_id}", headers=APPROVER
        )
    )


async def test_approver_of_other_session_cannot_get_session(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    other_execution = await _seed_session(eng)
    # carol approves in *another* session only.
    await _insert_approval(eng, workflow_execution_id=other_execution, approver="carol")
    res = await client.get(
        f"/api/v1/workflow-executions/{execution_id}", headers=APPROVER
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_super_admin_can_get_any_session(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    assert_ok(
        await client.get(
            f"/api/v1/workflow-executions/{execution_id}", headers=SUPER_ADMIN
        )
    )


async def test_admin_can_get_any_session(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    assert_ok(
        await client.get(f"/api/v1/workflow-executions/{execution_id}", headers=ADMIN)
    )


async def test_missing_session_is_404_even_for_unrelated_user(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = access_env
    res = await client.get("/api/v1/workflow-executions/nonexistent", headers=UNRELATED)
    assert_err(res, "NOT_FOUND", 404)


async def test_owner_sees_own_execution_in_list(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    res = await client.get("/api/v1/workflow-executions", headers=OWNER)
    ids = {item["id"] for item in assert_ok(res)}
    assert execution_id in ids


async def test_unrelated_user_does_not_see_others_execution_in_list(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    res = await client.get("/api/v1/workflow-executions", headers=UNRELATED)
    ids = {item["id"] for item in assert_ok(res)}
    assert execution_id not in ids


@pytest.mark.parametrize(
    "status",
    [
        ApprovalStatus.pending,
        ApprovalStatus.approved,
        ApprovalStatus.rejected,
        ApprovalStatus.returned,
    ],
)
async def test_designated_approver_sees_assigned_execution_in_list(
    access_env: tuple[AsyncClient, AsyncEngine], status: ApprovalStatus
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    await _insert_approval(eng, workflow_execution_id=execution_id, status=status)
    res = await client.get("/api/v1/workflow-executions", headers=APPROVER)
    ids = {item["id"] for item in assert_ok(res)}
    assert execution_id in ids


async def test_approver_of_other_session_does_not_see_it_in_list(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    other_execution = await _seed_session(eng)
    await _insert_approval(eng, workflow_execution_id=other_execution, approver="carol")
    res = await client.get("/api/v1/workflow-executions", headers=APPROVER)
    ids = {item["id"] for item in assert_ok(res)}
    assert execution_id not in ids


async def test_super_admin_sees_all_executions_in_list(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    id_a = await _seed_session(eng, user_id="owner")
    id_b = await _seed_session(eng, user_id="bob")
    res = await client.get("/api/v1/workflow-executions", headers=SUPER_ADMIN)
    ids = {item["id"] for item in assert_ok(res)}
    assert {id_a, id_b} <= ids


async def test_admin_sees_all_executions_in_list(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    id_a = await _seed_session(eng, user_id="owner")
    id_b = await _seed_session(eng, user_id="bob")
    res = await client.get("/api/v1/workflow-executions", headers=ADMIN)
    ids = {item["id"] for item in assert_ok(res)}
    assert {id_a, id_b} <= ids


async def test_execution_list_scoping_composes_with_filters(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    own_id = await _seed_session(eng)
    unrelated_id = await _seed_session(eng, user_id="bob")
    res = await client.get(
        "/api/v1/workflow-executions",
        params={"limit": 10, "offset": 0, "s": "-createdAt"},
        headers=OWNER,
    )
    ids = {item["id"] for item in assert_ok(res)}
    assert own_id in ids
    assert unrelated_id not in ids


# ---------- messages / tasks / agent ----------


async def test_unrelated_user_cannot_get_messages(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    res = await client.get(
        f"/api/v1/workflow-executions/{execution_id}/messages", headers=UNRELATED
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_approver_can_get_messages(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    await _insert_approval(eng, workflow_execution_id=execution_id)
    assert_ok(
        await client.get(
            f"/api/v1/workflow-executions/{execution_id}/messages", headers=APPROVER
        )
    )


async def test_admin_can_get_messages(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    assert_ok(
        await client.get(
            f"/api/v1/workflow-executions/{execution_id}/messages", headers=ADMIN
        )
    )


async def test_unrelated_user_cannot_list_session_tasks(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    res = await client.get(
        f"/api/v1/workflow-executions/{execution_id}/workflow-tasks", headers=UNRELATED
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_admin_can_list_session_tasks(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    assert_ok(
        await client.get(
            f"/api/v1/workflow-executions/{execution_id}/workflow-tasks", headers=ADMIN
        )
    )


async def test_unrelated_user_cannot_stream_agent(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    res = await client.post(
        f"/api/v1/workflow-executions/{execution_id}/agent",
        json=_run_agent_input(),
        headers=UNRELATED,
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_admin_cannot_stream_agent(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A plain admin can view an execution but must not be able to drive its agent."""
    client, eng = access_env
    execution_id = await _seed_session(eng)
    res = await client.post(
        f"/api/v1/workflow-executions/{execution_id}/agent",
        json=_run_agent_input(),
        headers=ADMIN,
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_approver_can_stream_agent(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    await _insert_approval(eng, workflow_execution_id=execution_id)
    res = await client.post(
        f"/api/v1/workflow-executions/{execution_id}/agent",
        json=_run_agent_input(),
        headers=APPROVER,
    )
    assert res.status_code == 200


# ---------- task CRUD ----------


async def test_unrelated_user_cannot_create_task(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    assert_err(await _create_task(client, execution_id, UNRELATED), "FORBIDDEN", 403)


async def test_admin_cannot_create_task(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A plain admin can read an execution's tasks but must not be able to create one."""
    client, eng = access_env
    execution_id = await _seed_session(eng)
    assert_err(await _create_task(client, execution_id, ADMIN), "FORBIDDEN", 403)


async def test_approver_can_create_and_update_task(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    await _insert_approval(eng, workflow_execution_id=execution_id)
    task = assert_ok(await _create_task(client, execution_id, APPROVER), status=201)
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
    execution_id = await _seed_session(eng)
    task = assert_ok(await _create_task(client, execution_id, OWNER), status=201)
    res = await client.get(f"/api/v1/workflow-tasks/{task['id']}", headers=UNRELATED)
    assert_err(res, "FORBIDDEN", 403)
    res = await client.delete(f"/api/v1/workflow-tasks/{task['id']}", headers=UNRELATED)
    assert_err(res, "FORBIDDEN", 403)


async def test_admin_can_read_but_not_update_or_delete_task(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A plain admin can read a single task but must not update or delete it."""
    client, eng = access_env
    execution_id = await _seed_session(eng)
    task = assert_ok(await _create_task(client, execution_id, OWNER), status=201)
    assert_ok(await client.get(f"/api/v1/workflow-tasks/{task['id']}", headers=ADMIN))
    res = await client.patch(
        f"/api/v1/workflow-tasks/{task['id']}",
        json={"status": "in_progress"},
        headers=ADMIN,
    )
    assert_err(res, "FORBIDDEN", 403)
    res = await client.delete(f"/api/v1/workflow-tasks/{task['id']}", headers=ADMIN)
    assert_err(res, "FORBIDDEN", 403)


# ---------- deletion is admin-or-super-admin only ----------
#
# Gated by the router's `require_roles(Role.admin)` dependency rather than by
# `WorkflowExecutionAccessPolicy`, so it is a flat role check with no
# ownership component: the initiator gets no special treatment.


async def test_approver_cannot_delete_session(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    await _insert_approval(eng, workflow_execution_id=execution_id)
    res = await client.delete(
        f"/api/v1/workflow-executions/{execution_id}", headers=APPROVER
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_owner_cannot_delete_session_without_admin_role(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Being the execution's own initiator is no longer sufficient to delete it."""
    client, eng = access_env
    execution_id = await _seed_session(eng)
    res = await client.delete(
        f"/api/v1/workflow-executions/{execution_id}", headers=OWNER
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_super_admin_can_delete_session(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    assert_ok(
        await client.delete(
            f"/api/v1/workflow-executions/{execution_id}", headers=SUPER_ADMIN
        )
    )


async def test_admin_can_delete_session_even_when_not_initiator(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A plain admin may delete an execution they did not initiate."""
    client, eng = access_env
    execution_id = await _seed_session(eng)
    assert_ok(
        await client.delete(
            f"/api/v1/workflow-executions/{execution_id}", headers=ADMIN
        )
    )


# ---------- access through a group-addressed approval ----------
#
# An approval addressed to a UserGroup shares the execution's chat with every
# member holding ``approver``, exactly as a user-addressed one does with its
# named user. Membership alone is not enough: the role gate in
# ``ApproverGroupResolver`` is what keeps a group's non-approver members out.

#: Headers modeling a member of the approver group who holds the role.
GROUP_APPROVER = {"X-User-Id": "carol", "X-User-Roles": "approver"}
#: Headers modeling a member of the same group who holds no role at all.
GROUP_MEMBER_NO_ROLE = {"X-User-Id": "bob", "X-User-Roles": ""}


async def _insert_group_approval(
    eng: AsyncEngine,
    *,
    workflow_execution_id: str,
    group_id: str = "approver-team",
    member_ids: tuple[str, ...] = ("carol", "bob"),
) -> str:
    """Insert a group, its members, and an Approval addressed to that group.

    Args:
        eng: Engine backing the test database.
        workflow_execution_id: The run the approval belongs to.
        group_id: Primary key to give the group.
        member_ids: Users to place in the group.

    Returns:
        The approval's id.
    """
    async with AsyncSession(eng) as db:
        db.add(
            UserGroup(
                id=group_id,
                tenant_id=DEFAULT_TEST_TENANT_ID,
                name="Approver Team",
                roles=[],
                created_by="owner",
                updated_by="owner",
            )
        )
        for member_id in member_ids:
            db.add(UserGroupMember(group_id=group_id, user_id=member_id))
        # Commit the group before the approval that references it: SQLite
        # checks foreign keys immediately, and one flush does not guarantee
        # the parent row is written first.
        await db.commit()
        approval = Approval(
            workflow_execution_id=workflow_execution_id,
            title="Approve me",
            status=ApprovalStatus.pending,
            approver_group_id=group_id,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by="owner",
            updated_by="owner",
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        return approval.id


async def test_group_approver_can_read_the_execution(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    await _insert_group_approval(eng, workflow_execution_id=execution_id)
    assert_ok(
        await client.get(
            f"/api/v1/workflow-executions/{execution_id}", headers=GROUP_APPROVER
        )
    )


async def test_group_approver_can_get_messages(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    await _insert_group_approval(eng, workflow_execution_id=execution_id)
    assert_ok(
        await client.get(
            f"/api/v1/workflow-executions/{execution_id}/messages",
            headers=GROUP_APPROVER,
        )
    )


async def test_group_member_without_the_role_is_denied(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Membership alone must not open the shared chat."""
    client, eng = access_env
    execution_id = await _seed_session(eng)
    await _insert_group_approval(eng, workflow_execution_id=execution_id)
    assert_err(
        await client.get(
            f"/api/v1/workflow-executions/{execution_id}",
            headers=GROUP_MEMBER_NO_ROLE,
        ),
        "FORBIDDEN",
        403,
    )


async def test_non_member_approver_is_denied_a_group_execution(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    # carol is the only member; bob holds approver but is left out.
    await _insert_group_approval(
        eng, workflow_execution_id=execution_id, member_ids=("carol",)
    )
    assert_err(
        await client.get(
            f"/api/v1/workflow-executions/{execution_id}",
            headers={"X-User-Id": "bob", "X-User-Roles": "approver"},
        ),
        "FORBIDDEN",
        403,
    )


async def test_group_approver_sees_the_execution_in_the_list(
    access_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = access_env
    execution_id = await _seed_session(eng)
    await _insert_group_approval(eng, workflow_execution_id=execution_id)
    listed = assert_ok(
        await client.get("/api/v1/workflow-executions", headers=GROUP_APPROVER)
    )
    assert execution_id in {row["id"] for row in listed}

    hidden = assert_ok(
        await client.get("/api/v1/workflow-executions", headers=GROUP_MEMBER_NO_ROLE)
    )
    assert hidden == []
