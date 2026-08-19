"""Tests for the approvals API (``GET``/``PATCH /api/v1/approvals``).

``GET`` list is scoped to the caller: a super admin or a plain admin sees
every approval in the tenant, everyone else sees only approvals addressed to
them or belonging to a WorkflowExecution they initiated. ``GET`` by id
remains unscoped (admin browsing), while ``PATCH`` records the requesting
user as the approver -- and admits only the designated approver, with no
bypass for a super admin or a plain admin. Approvals reference a workflow
execution via a foreign key, so each test seeds a session before inserting
approvals.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from models.approval import Approval, ApprovalStatus
from models.user import User
from models.user_group import UserGroup, UserGroupMember
from models.workflow_execution import WorkflowExecution
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users
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
    await seed_tenant(mem_engine)

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
    """Insert a WorkflowExecution and return its primary key."""
    async with AsyncSession(eng) as db:
        execution = WorkflowExecution(
            session_id="sess-1",
            name="wf",
            workflow_prompt="do it",
            agent_skill_id="skill-1",
            agent_skill_name="skill",
            agent_skill_repo_url="https://example.com/repo",
            agent_skill_repo_path=".",
            skill_dir="/tmp/skill",
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
    title: str = "Approve me",
    status: ApprovalStatus = ApprovalStatus.pending,
    user_id: str = "owner",
    approver: str | None = None,
    approver_group_id: str | None = None,
) -> str:
    """Insert an Approval for the given session and return its id."""
    async with AsyncSession(eng) as db:
        approval = Approval(
            workflow_execution_id=workflow_execution_id,
            title=title,
            status=status,
            approver=approver,
            approver_group_id=approver_group_id,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        return approval.id


async def _seed_group(
    eng: AsyncEngine,
    *,
    group_id: str = "group-1",
    name: str = "Approvers",
    roles: list[str] | None = None,
    member_ids: tuple[str, ...] = (),
) -> str:
    """Insert a UserGroup with the given members and return its id.

    Rows are written directly rather than through the repository so a test can
    build a group whose members deliberately hold no ``approver`` role, which
    the repository's own validation would otherwise be irrelevant to.
    """
    async with AsyncSession(eng) as db:
        db.add(
            UserGroup(
                id=group_id,
                name=name,
                roles=["approver"] if roles is None else roles,
                tenant_id=DEFAULT_TEST_TENANT_ID,
                created_by="owner",
                updated_by="owner",
            )
        )
        for member_id in member_ids:
            db.add(UserGroupMember(group_id=group_id, user_id=member_id))
        await db.commit()
    return group_id


async def test_list_returns_approvals(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng)
    await _insert_approval(eng, workflow_execution_id=execution_id, title="First")
    await _insert_approval(eng, workflow_execution_id=execution_id, title="Second")

    res = await client.get("/api/v1/approvals", headers={"X-User-Id": "owner"})
    data = assert_ok(res)
    assert {a["title"] for a in data} == {"First", "Second"}


async def test_owner_sees_approval_on_own_execution_in_list(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng, user_id="owner")
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver="bob"
    )
    res = await client.get(
        "/api/v1/approvals",
        headers={"X-User-Id": "owner", "X-User-Roles": "requester"},
    )
    ids = {a["id"] for a in assert_ok(res)}
    assert approval_id in ids


async def test_unrelated_user_does_not_see_others_approval_in_list(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng, user_id="owner")
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver="bob"
    )
    res = await client.get(
        "/api/v1/approvals",
        headers={"X-User-Id": "alice", "X-User-Roles": "requester"},
    )
    ids = {a["id"] for a in assert_ok(res)}
    assert approval_id not in ids


@pytest.mark.parametrize(
    "status",
    [
        ApprovalStatus.pending,
        ApprovalStatus.approved,
        ApprovalStatus.rejected,
        ApprovalStatus.returned,
    ],
)
async def test_designated_approver_sees_addressed_approval_in_list(
    approval_env: tuple[AsyncClient, AsyncEngine], status: ApprovalStatus
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng, user_id="owner")
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver="bob", status=status
    )
    res = await client.get(
        "/api/v1/approvals",
        headers={"X-User-Id": "bob", "X-User-Roles": "approver"},
    )
    ids = {a["id"] for a in assert_ok(res)}
    assert approval_id in ids


async def test_super_admin_sees_all_approvals_in_list(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng, user_id="owner")
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver="bob"
    )
    res = await client.get(
        "/api/v1/approvals",
        headers={"X-User-Id": "alice", "X-User-Roles": "super_admin"},
    )
    ids = {a["id"] for a in assert_ok(res)}
    assert approval_id in ids


async def test_admin_sees_all_approvals_in_list(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng, user_id="owner")
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver="bob"
    )
    res = await client.get(
        "/api/v1/approvals",
        headers={"X-User-Id": "dave", "X-User-Roles": "admin"},
    )
    ids = {a["id"] for a in assert_ok(res)}
    assert approval_id in ids


async def test_get_approval(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng)
    approval_id = await _insert_approval(eng, workflow_execution_id=execution_id)

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
    execution_id = await _seed_session(eng)
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver="alice"
    )

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


async def test_resolve_by_non_approver_is_forbidden(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng)
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver="bob"
    )

    # alice is not the designated approver, so she cannot resolve it — even
    # while holding the approver role (the test auth stub defaults to
    # super_admin, which would bypass the check, so roles are set explicitly).
    res = await client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"status": "approved"},
        headers={"X-User-Id": "alice", "X-User-Roles": "approver"},
    )
    assert_err(res, "FORBIDDEN", 403)

    # The approval remains pending.
    res = await client.get(
        f"/api/v1/approvals/{approval_id}", headers={"X-User-Id": "owner"}
    )
    assert assert_ok(res)["status"] == ApprovalStatus.pending.value


async def test_resolve_by_super_admin_who_is_not_approver_is_forbidden(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A super admin who is not the designated approver still cannot resolve it."""
    client, eng = approval_env
    execution_id = await _seed_session(eng)
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver="bob"
    )

    res = await client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"status": "approved"},
        headers={"X-User-Id": "alice", "X-User-Roles": "super_admin"},
    )
    assert_err(res, "FORBIDDEN", 403)

    # The approval remains pending.
    res = await client.get(
        f"/api/v1/approvals/{approval_id}", headers={"X-User-Id": "owner"}
    )
    assert assert_ok(res)["status"] == ApprovalStatus.pending.value


async def test_resolve_by_admin_who_is_not_approver_is_forbidden(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A plain admin who is not the designated approver still cannot resolve it."""
    client, eng = approval_env
    execution_id = await _seed_session(eng)
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver="bob"
    )

    res = await client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"status": "approved"},
        headers={"X-User-Id": "dave", "X-User-Roles": "admin"},
    )
    assert_err(res, "FORBIDDEN", 403)

    # The approval remains pending.
    res = await client.get(
        f"/api/v1/approvals/{approval_id}", headers={"X-User-Id": "owner"}
    )
    assert assert_ok(res)["status"] == ApprovalStatus.pending.value


async def test_resolve_keeps_designated_approver(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng)
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver="bob"
    )

    res = await client.get(
        f"/api/v1/approvals/{approval_id}", headers={"X-User-Id": "owner"}
    )
    assert assert_ok(res)["approver"] == "bob"

    # The designated approver resolves it; the approver field is preserved.
    # Roles are set explicitly (rather than relying on the test auth stub's
    # default super_admin) so this proves designated-approver access works
    # with no role-based bypass in play.
    res = await client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"status": "approved"},
        headers={"X-User-Id": "bob", "X-User-Roles": "approver"},
    )
    data = assert_ok(res)
    assert data["approver"] == "bob"
    assert data["updatedBy"] == "bob"


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


async def test_resolve_stamps_decided_at(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng)
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver="alice"
    )

    before = assert_ok(
        await client.get(
            f"/api/v1/approvals/{approval_id}", headers={"X-User-Id": "owner"}
        )
    )
    assert before["decidedAt"] is None

    data = assert_ok(
        await client.patch(
            f"/api/v1/approvals/{approval_id}",
            json={"status": "approved"},
            headers={"X-User-Id": "alice"},
        )
    )
    assert data["decidedAt"] is not None


async def test_decided_at_is_not_moved_by_a_later_edit(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Editing the comment afterwards must not rewrite the approver's turnaround time."""
    client, eng = approval_env
    execution_id = await _seed_session(eng)
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver="alice"
    )
    first = assert_ok(
        await client.patch(
            f"/api/v1/approvals/{approval_id}",
            json={"status": "approved"},
            headers={"X-User-Id": "alice"},
        )
    )

    second = assert_ok(
        await client.patch(
            f"/api/v1/approvals/{approval_id}",
            json={"response": "on reflection, still fine"},
            headers={"X-User-Id": "alice"},
        )
    )

    assert second["decidedAt"] == first["decidedAt"]


async def test_resolve_approval_returns_it_for_rework(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng)
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver="alice"
    )

    data = assert_ok(
        await client.patch(
            f"/api/v1/approvals/{approval_id}",
            json={"status": "returned", "response": "please add the cost breakdown"},
            headers={"X-User-Id": "alice"},
        )
    )

    assert data["status"] == ApprovalStatus.returned.value
    assert data["decidedAt"] is not None


# --- Group-addressed approvals -------------------------------------------
#
# An approval may name a UserGroup instead of one user. Any member holding the
# ``approver`` role may then resolve it, and the first decision settles it.
# ``bob`` and ``carol`` are seeded with ``approver`` (see tests/_seed.py); the
# user created by ``_seed_roleless_user`` deliberately holds none.


async def _seed_roleless_user(eng: AsyncEngine, user_id: str = "plain") -> str:
    """Insert an enabled tenant user holding no roles at all, and return its id."""
    async with AsyncSession(eng) as db:
        db.add(
            User(
                id=user_id,
                username=user_id,
                first_name="No",
                last_name="Role",
                email=f"{user_id}@example.com",
                password="x",
                roles=[],
                tenant_id=DEFAULT_TEST_TENANT_ID,
                created_by="owner",
                updated_by="owner",
            )
        )
        await db.commit()
    return user_id


async def test_group_member_can_resolve_group_approval(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng)
    group_id = await _seed_group(eng, member_ids=("bob", "carol"))
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver_group_id=group_id
    )

    res = await client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"status": "approved", "response": "fine by me"},
        headers={"X-User-Id": "carol", "X-User-Roles": "approver"},
    )
    data = assert_ok(res)
    assert data["status"] == "approved"
    # The point of decidedBy: the group alone does not say who acted.
    assert data["decidedBy"] == "carol"
    assert data["decidedAt"] is not None


async def test_group_member_without_approver_role_cannot_resolve(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng)
    plain = await _seed_roleless_user(eng)
    # The group itself grants nothing, so membership alone confers nothing.
    group_id = await _seed_group(eng, roles=[], member_ids=(plain,))
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver_group_id=group_id
    )

    res = await client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"status": "approved"},
        headers={"X-User-Id": plain, "X-User-Roles": ""},
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_group_member_inheriting_approver_role_can_resolve(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng)
    plain = await _seed_roleless_user(eng)
    # Holds no direct role; the group grants approver, so the union qualifies.
    group_id = await _seed_group(eng, roles=["approver"], member_ids=(plain,))
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver_group_id=group_id
    )

    res = await client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"status": "approved"},
        headers={"X-User-Id": plain, "X-User-Roles": ""},
    )
    assert assert_ok(res)["decidedBy"] == plain


async def test_non_member_with_approver_role_cannot_resolve_group_approval(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng)
    group_id = await _seed_group(eng, member_ids=("bob",))
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver_group_id=group_id
    )

    # carol holds approver but is not in the group.
    res = await client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"status": "approved"},
        headers={"X-User-Id": "carol", "X-User-Roles": "approver"},
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_super_admin_cannot_resolve_group_approval(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng)
    group_id = await _seed_group(eng, member_ids=("bob",))
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver_group_id=group_id
    )

    res = await client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"status": "approved"},
        headers={"X-User-Id": "alice", "X-User-Roles": "super_admin"},
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_second_member_cannot_overwrite_a_recorded_decision(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng)
    group_id = await _seed_group(eng, member_ids=("bob", "carol"))
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver_group_id=group_id
    )

    first = await client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"status": "approved"},
        headers={"X-User-Id": "bob", "X-User-Roles": "approver"},
    )
    assert assert_ok(first)["decidedBy"] == "bob"

    second = await client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"status": "rejected"},
        headers={"X-User-Id": "carol", "X-User-Roles": "approver"},
    )
    assert_err(second, "APPROVAL_ALREADY_RESOLVED", 409)

    after = assert_ok(
        await client.get(
            f"/api/v1/approvals/{approval_id}", headers={"X-User-Id": "bob"}
        )
    )
    assert after["status"] == "approved"
    assert after["decidedBy"] == "bob"


async def test_comment_can_still_be_edited_after_a_decision(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng)
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver="bob"
    )
    await client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"status": "approved"},
        headers={"X-User-Id": "bob"},
    )
    decided_at = assert_ok(
        await client.get(
            f"/api/v1/approvals/{approval_id}", headers={"X-User-Id": "bob"}
        )
    )["decidedAt"]

    res = await client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"response": "adding context afterwards"},
        headers={"X-User-Id": "bob"},
    )
    data = assert_ok(res)
    assert data["response"] == "adding context afterwards"
    # Neither decision stamp moves on a comment-only edit.
    assert data["decidedAt"] == decided_at
    assert data["decidedBy"] == "bob"


async def test_group_member_sees_group_approval_in_list(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng)
    group_id = await _seed_group(eng, member_ids=("bob",))
    await _insert_approval(
        eng,
        workflow_execution_id=execution_id,
        title="For the group",
        approver_group_id=group_id,
    )

    visible = assert_ok(
        await client.get(
            "/api/v1/approvals",
            headers={"X-User-Id": "bob", "X-User-Roles": "approver"},
        )
    )
    assert {a["title"] for a in visible} == {"For the group"}

    # carol holds approver but is not a member, and did not initiate the run.
    hidden = assert_ok(
        await client.get(
            "/api/v1/approvals",
            headers={"X-User-Id": "carol", "X-User-Roles": "approver"},
        )
    )
    assert hidden == []


async def test_decided_by_cannot_be_set_through_the_patch_body(
    approval_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = approval_env
    execution_id = await _seed_session(eng)
    approval_id = await _insert_approval(
        eng, workflow_execution_id=execution_id, approver="bob"
    )

    res = await client.patch(
        f"/api/v1/approvals/{approval_id}",
        json={"status": "approved", "decidedBy": "carol"},
        headers={"X-User-Id": "bob"},
    )
    # decidedBy is declared on the table class only, so the payload field is
    # ignored rather than honoured.
    assert assert_ok(res)["decidedBy"] == "bob"
