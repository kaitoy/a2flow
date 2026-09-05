"""Tests for the Approval agent tools in ``infrastructure.approval_tools``.

Like the WorkflowTask tools, these open their own ``AsyncSession`` on
``infrastructure.database.engine``; each test monkeypatches that engine to an
throwaway database and drives the tools with a lightweight fake
ToolContext exposing only ``session.id`` and ``user_id``.
"""

from collections.abc import AsyncGenerator, Sequence
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.approval_tools import (
    get_approval,
    list_user_groups,
    list_users,
    request_approval,
)
from infrastructure.workflow_task_tools import ACTING_USER_STATE_KEY
from models.approval import Approval, ApprovalStatus
from models.mcp_tool_certificate import McpToolCertificate, RevocationReason
from models.notification import Notification, NotificationType
from models.user import SYSTEM_USER_ID, Role
from models.user_group import UserGroup, UserGroupMember
from models.workflow_execution import WorkflowExecution
from models.workflow_task import WorkflowTaskStatus
from repositories import (
    SqlApprovalRepository,
    SqlNotificationRepository,
    SqlUserGroupRepository,
    SqlUserRepository,
)
from tests._engine import make_test_engine
from tests._seed import (
    DEFAULT_TEST_TENANT_ID,
    grant_tool_certificate,
    seed_tenant,
    seed_users,
    seed_workflow_task,
)


@pytest_asyncio.fixture()
async def engine(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[AsyncEngine, None]:
    """Yield a throwaway engine and point the tools' module-level engine at it."""
    eng = await make_test_engine()
    await seed_users(eng, ids=())  # system user only; Tenant FKs to it
    await seed_tenant(eng)
    await seed_users(eng, tenant_id=DEFAULT_TEST_TENANT_ID)

    monkeypatch.setattr("infrastructure.database.engine", eng)
    yield eng
    await eng.dispose()


async def _seed_session(
    eng: AsyncEngine, *, session_id: str = "sess-abc", user_id: str = "owner"
) -> str:
    """Insert a WorkflowExecution with the given ADK session id and return its PK."""
    async with AsyncSession(eng) as db:
        execution = WorkflowExecution(
            session_id=session_id,
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


def _ctx(
    session_id: str = "sess-abc",
    user_id: str = "owner",
    *,
    state: dict[str, Any] | None = None,
) -> Any:
    """Build a fake ToolContext exposing ``session.id``, ``user_id``, and ``state``."""
    return SimpleNamespace(
        session=SimpleNamespace(id=session_id), user_id=user_id, state=state
    )


async def _seed_task(
    ctx: Any = None,
    *,
    title: str = "Act",
    depends_on_ids: Sequence[str] = (),
    tool_bindings: Sequence[tuple[str, str]] = (),
    input_approval_exempt: Sequence[tuple[str, str]] = (),
    status: WorkflowTaskStatus = WorkflowTaskStatus.pending,
    grant: bool = False,
) -> str:
    """Seed a WorkflowTask in the current session and return its id.

    ``request_approval`` requires the id of the task the approval authorizes, so
    almost every test needs one even when the task itself is not what is being
    exercised. The execution agent can no longer create tasks, so this inserts
    straight into the table via :func:`tests._seed.seed_workflow_task`, reading
    the monkeypatched engine the tools themselves use.
    """
    from infrastructure import database

    session_id = (ctx if ctx is not None else _ctx()).session.id
    async with AsyncSession(database.engine) as db:
        execution = await _execution_repo(db).get_by_session_id(session_id)
        assert execution is not None
        execution_id = execution.id
    task_id = await seed_workflow_task(
        database.engine,
        execution_id,
        title=title,
        status=status,
        depends_on_ids=depends_on_ids,
        tool_bindings=tool_bindings,
        input_approval_exempt=input_approval_exempt,
    )
    if grant:
        await grant_tool_certificate(database.engine, execution_id, task_id)
    return task_id


async def _notifications_for(eng: AsyncEngine, user_id: str) -> list[Notification]:
    """Return all notifications addressed to ``user_id`` via the repository."""
    async with AsyncSession(eng) as db:
        repo = SqlNotificationRepository(db, tenant_id=DEFAULT_TEST_TENANT_ID)
        return await repo.list(user_id=user_id, limit=100, offset=0)


async def test_request_approval_attributes_to_acting_user(engine: AsyncEngine) -> None:
    """The router-stamped acting user, not the session's fixed owner, is recorded.

    ``owner`` is the ADK session's ``tool_context.user_id`` (the execution's
    initiator), but ``alice`` is the per-turn acting user impersonation would
    stamp into state -- ``created_by``/``updated_by`` on the Approval must
    follow ``alice``.
    """
    await _seed_session(engine, user_id="owner")
    task_id = await _seed_task()
    result = await request_approval(
        "Deploy to prod",
        _ctx(user_id="owner", state={ACTING_USER_STATE_KEY: "alice"}),
        task_id,
        approver="bob",
    )
    assert "error" not in result
    async with AsyncSession(engine) as db:
        approval = await db.get(Approval, result["approval_id"])
    assert approval is not None
    assert approval.created_by == "alice"
    assert approval.updated_by == "alice"


async def test_request_approval_creates_pending_record(engine: AsyncEngine) -> None:
    await _seed_session(engine, user_id="owner")
    task_id = await _seed_task()
    result = await request_approval(
        "Deploy to prod", _ctx(), task_id, approver="alice", description="Are you sure?"
    )
    assert "error" not in result
    assert result["status"] == "pending"

    fetched = await get_approval(result["approval_id"], _ctx())
    assert fetched["title"] == "Deploy to prod"
    assert fetched["status"] == ApprovalStatus.pending.value


async def test_request_approval_notifies_approver(engine: AsyncEngine) -> None:
    await _seed_session(engine, user_id="owner")
    task_id = await _seed_task()
    await request_approval(
        "Need sign-off", _ctx(), task_id, approver="alice", description="please review"
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
    task_id = await _seed_task()
    result = await request_approval("No approver", _ctx(), task_id, approver="")
    assert "error" in result


async def test_request_approval_without_session_errors(engine: AsyncEngine) -> None:
    result = await request_approval(
        "X", _ctx("unknown-session"), "task-1", approver="alice"
    )
    assert "error" in result


async def test_request_approval_links_valid_task(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    task_id = await _seed_task(title="A task")
    result = await request_approval(
        "Approve task", _ctx(), approver="alice", workflow_task_id=task_id
    )
    assert "error" not in result
    fetched = await get_approval(result["approval_id"], _ctx())
    assert fetched["workflow_task_id"] == task_id


async def test_request_approval_records_approver(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    task_id = await _seed_task()
    result = await request_approval("Approve me", _ctx(), task_id, approver="alice")
    assert "error" not in result
    fetched = await get_approval(result["approval_id"], _ctx())
    assert fetched["approver"] == "alice"


async def test_request_approval_rejects_unknown_approver(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    task_id = await _seed_task()
    result = await request_approval("Approve me", _ctx(), task_id, approver="nobody")
    assert "error" in result


async def test_request_approval_rejects_foreign_task(engine: AsyncEngine) -> None:
    await _seed_session(engine, session_id="sess-a")
    await _seed_session(engine, session_id="sess-b")
    task_id = await _seed_task(_ctx("sess-a"), title="In A")
    result = await request_approval(
        "Approve", _ctx("sess-b"), approver="alice", workflow_task_id=task_id
    )
    assert "error" in result


async def test_get_approval_cross_session_guard(engine: AsyncEngine) -> None:
    await _seed_session(engine, session_id="sess-a")
    await _seed_session(engine, session_id="sess-b")
    task_id = await _seed_task(_ctx("sess-a"))
    created = await request_approval(
        "Owned by A", _ctx("sess-a"), task_id, approver="alice"
    )
    approval_id = created["approval_id"]

    blocked = await get_approval(approval_id, _ctx("sess-b"))
    assert "error" in blocked
    allowed = await get_approval(approval_id, _ctx("sess-a"))
    assert allowed["approval_id"] == approval_id


async def test_get_approval_reflects_resolution(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    task_id = await _seed_task()
    created = await request_approval("Decide", _ctx(), task_id, approver="alice")
    # Resolve directly through the repository (the frontend's PATCH path).
    async with AsyncSession(engine) as db:
        repo = SqlApprovalRepository(
            db,
            _execution_repo(db),
            SqlUserGroupRepository(
                db, SqlUserRepository(db), tenant_id=DEFAULT_TEST_TENANT_ID
            ),
            tenant_id=DEFAULT_TEST_TENANT_ID,
        )
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
    task_id = await _seed_task()
    result = await request_approval("Approve me", _ctx(), task_id, approver=approver_id)
    assert "error" not in result
    fetched = await get_approval(result["approval_id"], _ctx())
    assert fetched["approver"] == approver_id


def _execution_repo(db: AsyncSession) -> Any:
    """Build a WorkflowExecution repository for the approval repository's FK check."""
    from repositories import SqlWorkflowExecutionRepository

    return SqlWorkflowExecutionRepository(db, tenant_id=DEFAULT_TEST_TENANT_ID)


# ---------- approver eligibility (roles) ----------


async def test_request_approval_rejects_approver_without_role(
    engine: AsyncEngine,
) -> None:
    """A user without the approver role cannot be designated as an approver."""
    await seed_users(
        engine, ids=("norole",), roles=(), tenant_id=DEFAULT_TEST_TENANT_ID
    )
    await _seed_session(engine)
    task_id = await _seed_task()
    result = await request_approval("Approve me", _ctx(), task_id, approver="norole")
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
    task_id = await _seed_task()
    result = await request_approval("Approve me", _ctx(), task_id, approver="boss")
    assert "error" in result


async def test_request_approval_rejects_other_tenant_approver(
    engine: AsyncEngine,
) -> None:
    """An approver belonging to a different tenant cannot be designated."""
    await seed_tenant(engine, tenant_id="tenant-other")
    await seed_users(engine, ids=("dave",), tenant_id="tenant-other")
    await _seed_session(engine)
    task_id = await _seed_task()
    result = await request_approval("Approve me", _ctx(), task_id, approver="dave")
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


# ---------- approver eligibility via a user group ----------


async def _put_in_group(
    eng: AsyncEngine,
    *,
    user_id: str,
    roles: list[str],
    group_id: str = "group-1",
    name: str = "Approvers",
) -> None:
    """Create a user group granting ``roles`` and place ``user_id`` in it."""
    async with AsyncSession(eng) as db:
        db.add(
            UserGroup(
                id=group_id,
                tenant_id=DEFAULT_TEST_TENANT_ID,
                name=name,
                roles=roles,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        db.add(UserGroupMember(group_id=group_id, user_id=user_id))
        await db.commit()


async def test_group_inherited_approver_is_eligible(engine: AsyncEngine) -> None:
    """A user whose only ``approver`` grant comes from a group can be designated.

    This is the demo dataset's shape: ``demo-approver-1`` holds no direct role
    and inherits ``approver`` from the ``Demo Approvers`` group.
    """
    await seed_users(
        engine, ids=("grouped",), roles=(), tenant_id=DEFAULT_TEST_TENANT_ID
    )
    await _put_in_group(engine, user_id="grouped", roles=[Role.approver.value])
    await _seed_session(engine)
    task_id = await _seed_task()
    result = await request_approval("Approve me", _ctx(), task_id, approver="grouped")
    assert "error" not in result, result
    assert result["status"] == ApprovalStatus.pending.value


async def test_group_inherited_approver_appears_in_list_users(
    engine: AsyncEngine,
) -> None:
    await seed_users(
        engine, ids=("grouped",), roles=(), tenant_id=DEFAULT_TEST_TENANT_ID
    )
    await _put_in_group(engine, user_id="grouped", roles=[Role.approver.value])
    await _seed_session(engine)
    result = await list_users(_ctx())
    assert "grouped" in {user["id"] for user in result["users"]}


async def test_a_group_granting_another_role_does_not_make_an_approver(
    engine: AsyncEngine,
) -> None:
    await seed_users(
        engine, ids=("grouped",), roles=(), tenant_id=DEFAULT_TEST_TENANT_ID
    )
    await _put_in_group(
        engine, user_id="grouped", roles=[Role.developer.value], name="Developers"
    )
    await _seed_session(engine)
    task_id = await _seed_task()
    result = await request_approval("Approve me", _ctx(), task_id, approver="grouped")
    assert "error" in result
    assert "grouped" not in {user["id"] for user in (await list_users(_ctx()))["users"]}


# ---------- addressing a request to a user group ----------


async def _group_with_members(
    eng: AsyncEngine,
    *,
    members: dict[str, list[str]],
    group_roles: list[str],
    group_id: str = "team-1",
    name: str = "Approver Team",
) -> str:
    """Create a group granting ``group_roles`` and seed ``members`` into it.

    Args:
        eng: The engine backing the test database.
        members: User id mapped to the roles that user holds *directly*.
        group_roles: Roles the group itself grants every member.
        group_id: Primary key to give the group.
        name: The group's name.

    Returns:
        The group's id.
    """
    for user_id, roles in members.items():
        await seed_users(
            eng,
            ids=(user_id,),
            roles=tuple(Role(r) for r in roles),
            tenant_id=DEFAULT_TEST_TENANT_ID,
        )
    async with AsyncSession(eng) as db:
        db.add(
            UserGroup(
                id=group_id,
                tenant_id=DEFAULT_TEST_TENANT_ID,
                name=name,
                roles=group_roles,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        for user_id in members:
            db.add(UserGroupMember(group_id=group_id, user_id=user_id))
        await db.commit()
    return group_id


async def test_request_approval_requires_a_destination(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    task_id = await _seed_task()
    result = await request_approval("Decide", _ctx(), task_id)
    assert "exactly one" in result["error"]


async def test_request_approval_rejects_two_destinations(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    task_id = await _seed_task()
    group_id = await _group_with_members(
        engine, members={"m1": []}, group_roles=[Role.approver.value]
    )
    result = await request_approval(
        "Decide", _ctx(), task_id, approver="alice", approver_group_id=group_id
    )
    assert "exactly one" in result["error"]


async def test_request_approval_to_a_group_succeeds(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    task_id = await _seed_task()
    group_id = await _group_with_members(
        engine, members={"m1": [], "m2": []}, group_roles=[Role.approver.value]
    )
    result = await request_approval(
        "Decide", _ctx(), task_id, approver_group_id=group_id
    )
    assert "error" not in result, result
    assert result["status"] == ApprovalStatus.pending.value

    fetched = await get_approval(result["approval_id"], _ctx())
    assert fetched["approver"] is None
    assert fetched["approver_group_id"] == group_id
    assert fetched["decided_by"] is None


async def test_request_approval_to_an_unknown_group_is_rejected(
    engine: AsyncEngine,
) -> None:
    await _seed_session(engine)
    task_id = await _seed_task()
    result = await request_approval("Decide", _ctx(), task_id, approver_group_id="nope")
    assert "not found" in result["error"]


async def test_request_approval_rejects_a_group_with_no_eligible_member(
    engine: AsyncEngine,
) -> None:
    """A group nobody can approve for would wedge the run, so it is refused."""
    await _seed_session(engine)
    task_id = await _seed_task()
    group_id = await _group_with_members(
        engine, members={"m1": [], "m2": []}, group_roles=[Role.developer.value]
    )
    result = await request_approval(
        "Decide", _ctx(), task_id, approver_group_id=group_id
    )
    assert "no member who can approve" in result["error"]


async def test_group_request_notifies_every_eligible_member(
    engine: AsyncEngine,
) -> None:
    await _seed_session(engine)
    # m1 and m2 qualify through the group grant; m3 is in no group and must not
    # be notified even though it holds approver directly.
    group_id = await _group_with_members(
        engine, members={"m1": [], "m2": []}, group_roles=[Role.approver.value]
    )
    await seed_users(
        engine,
        ids=("m3",),
        roles=(Role.approver,),
        tenant_id=DEFAULT_TEST_TENANT_ID,
    )

    result = await request_approval(
        "Decide", _ctx(), await _seed_task(), approver_group_id=group_id
    )
    assert "error" not in result, result

    for member in ("m1", "m2"):
        notes = await _notifications_for(engine, member)
        assert [n.type for n in notes] == [NotificationType.approval_request]
    assert await _notifications_for(engine, "m3") == []


async def test_group_request_skips_members_without_the_approver_role(
    engine: AsyncEngine,
) -> None:
    await _seed_session(engine)
    # The group grants nothing; only m1 qualifies, through a direct grant.
    group_id = await _group_with_members(
        engine,
        members={"m1": [Role.approver.value], "m2": []},
        group_roles=[],
    )
    result = await request_approval(
        "Decide", _ctx(), await _seed_task(), approver_group_id=group_id
    )
    assert "error" not in result, result
    assert len(await _notifications_for(engine, "m1")) == 1
    assert await _notifications_for(engine, "m2") == []


async def test_list_user_groups_returns_groups_with_an_eligible_member(
    engine: AsyncEngine,
) -> None:
    await _seed_session(engine)
    await _group_with_members(
        engine,
        members={"m1": [], "m2": []},
        group_roles=[Role.approver.value],
        group_id="team-ok",
        name="Can Approve",
    )
    await _group_with_members(
        engine,
        members={"m3": []},
        group_roles=[Role.developer.value],
        group_id="team-no",
        name="Cannot Approve",
    )

    result = await list_user_groups(_ctx())
    listed = {g["id"]: g for g in result["groups"]}
    assert set(listed) == {"team-ok"}
    assert listed["team-ok"]["name"] == "Can Approve"
    assert listed["team-ok"]["eligible_approver_count"] == 2


async def test_list_user_groups_excludes_other_tenants(engine: AsyncEngine) -> None:
    await _seed_session(engine)
    await seed_tenant(engine, "other-tenant")
    await seed_users(
        engine, ids=("outsider",), roles=(Role.approver,), tenant_id="other-tenant"
    )
    async with AsyncSession(engine) as db:
        db.add(
            UserGroup(
                id="foreign-team",
                tenant_id="other-tenant",
                name="Foreign",
                roles=[Role.approver.value],
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        db.add(UserGroupMember(group_id="foreign-team", user_id="outsider"))
        await db.commit()

    result = await list_user_groups(_ctx())
    assert result["groups"] == []


# ---------- the tasks an approval authorizes ----------


async def _seed_mcp_server(eng: AsyncEngine, *, name: str = "srv") -> str:
    """Insert an MCPServer owned by the seeded system user and return its id."""
    from models.mcp_server import MCPServer

    async with AsyncSession(eng) as db:
        server = MCPServer(
            name=name,
            url="https://mcp.example.com/mcp",
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server.id


def _declare(
    server_id: str, tool_name: str, **arguments: dict[str, object]
) -> list[dict[str, object]]:
    """Build the one-tool declaration a request over that tool must carry.

    Args:
        server_id: The MCP server the declared call targets.
        tool_name: The tool the declared call targets.
        **arguments: Argument name to its constraint object.

    Returns:
        The ``approved_calls`` payload.
    """
    return [
        {
            "mcp_server_id": server_id,
            "tool_name": tool_name,
            "arguments": arguments,
        }
    ]


async def test_request_approval_accepts_the_asking_step(engine: AsyncEngine) -> None:
    """A step whose whole job is to ask for a go-ahead is a valid gate.

    This is the shape a design agent naturally produces: "Request approval"
    followed by the task that actually calls the tool. The approval takes effect
    from the step it names and covers everything after it, so naming the asking
    step is the intended usage rather than a mistake to refuse.
    """
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    asking = await _seed_task(title="Request approval")
    await _seed_task(
        title="Launch instance",
        depends_on_ids=[asking],
        tool_bindings=[(server_id, "launch")],
    )
    result = await request_approval(
        "Approve the launch",
        _ctx(),
        asking,
        approved_calls=_declare(server_id, "launch"),
        approver="alice",
    )
    assert "error" not in result, result
    fetched = await get_approval(result["approval_id"], _ctx())
    assert fetched["workflow_task_id"] == asking


async def test_request_approval_accepts_the_acting_task(engine: AsyncEngine) -> None:
    """Naming the task that binds the tools gates that task and its descendants."""
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    asking = await _seed_task(title="Request approval")
    acting = await _seed_task(
        title="Launch instance",
        depends_on_ids=[asking],
        tool_bindings=[(server_id, "launch")],
    )
    result = await request_approval(
        "Approve the launch",
        _ctx(),
        acting,
        approved_calls=_declare(server_id, "launch"),
        approver="alice",
    )
    assert "error" not in result, result
    fetched = await get_approval(result["approval_id"], _ctx())
    assert fetched["workflow_task_id"] == acting


async def test_request_approval_allows_a_task_with_no_tools_anywhere_downstream(
    engine: AsyncEngine,
) -> None:
    """An approval may gate an action that uses no MCP tool at all."""
    await _seed_session(engine)
    asking = await _seed_task(title="Draft the notice")
    await _seed_task(title="Publish it", depends_on_ids=[asking])
    result = await request_approval(
        "Approve the wording", _ctx(), asking, approver="alice"
    )
    assert "error" not in result, result


async def test_request_approval_stands_down_grants_across_its_new_scope(
    engine: AsyncEngine,
) -> None:
    """A downstream task already running loses the grant it was running on.

    The approval takes the task over the moment it is requested, so the run
    initiator's own grant -- taken out when the task started, before anyone was
    asked to approve anything -- must stop counting.
    """
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    asking = await _seed_task(title="Request approval")
    acting = await _seed_task(
        title="Launch instance",
        depends_on_ids=[asking],
        tool_bindings=[(server_id, "launch")],
        status=WorkflowTaskStatus.in_progress,
        grant=True,
    )

    async with AsyncSession(engine) as db:
        before = (await db.exec(select(McpToolCertificate))).all()
    assert [c.workflow_task_id for c in before] == [acting]
    assert before[0].revoked_at is None

    result = await request_approval(
        "Approve the launch",
        _ctx(),
        asking,
        approved_calls=_declare(server_id, "launch"),
        approver="alice",
    )
    assert "error" not in result, result

    async with AsyncSession(engine) as db:
        after = (await db.exec(select(McpToolCertificate))).all()
    assert after[0].revoked_at is not None
    assert after[0].revocation_reason is RevocationReason.superseded_by_approval


async def test_request_approval_leaves_grants_outside_its_scope_alone(
    engine: AsyncEngine,
) -> None:
    """A task the approval does not reach keeps running on its own authority."""
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    unrelated = await _seed_task(
        title="Gather sources",
        tool_bindings=[(server_id, "search")],
        status=WorkflowTaskStatus.in_progress,
        grant=True,
    )
    asking = await _seed_task(title="Request approval")

    result = await request_approval(
        "Approve the launch", _ctx(), asking, approver="alice"
    )
    assert "error" not in result, result

    async with AsyncSession(engine) as db:
        certificates = (await db.exec(select(McpToolCertificate))).all()
    assert [c.workflow_task_id for c in certificates] == [unrelated]
    assert certificates[0].revoked_at is None


async def test_request_approval_ignores_tools_bound_upstream(
    engine: AsyncEngine,
) -> None:
    """A tool-bearing task *above* the named one does not affect the request.

    An approval reaches forward, never back: a task that already ran its tools
    before this approval was asked for is not what the approval authorizes.
    """
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    earlier = await _seed_task(
        title="Gather sources",
        tool_bindings=[(server_id, "search")],
    )
    named = await _seed_task(title="Approve the summary", depends_on_ids=[earlier])
    result = await request_approval(
        "Approve the summary", _ctx(), named, approver="alice"
    )
    assert "error" not in result, result


# ---------- the calls an approval declares ----------


async def test_request_approval_requires_a_declaration_over_the_bound_tools(
    engine: AsyncEngine,
) -> None:
    """Declaring nothing over a task that binds a tool is refused.

    Without this the gate has a hole the agent can walk through: an approval
    with no declaration constrains no argument, so omitting one would buy back
    exactly the authority the declaration exists to bound.
    """
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    task_id = await _seed_task(
        title="Launch instance", tool_bindings=[(server_id, "launch")]
    )
    result = await request_approval(
        "Approve the launch", _ctx(), task_id, approver="alice"
    )
    assert "error" in result
    assert "launch" in result["error"]


async def test_request_approval_requires_a_declaration_for_downstream_tools(
    engine: AsyncEngine,
) -> None:
    """The declaration follows the approval's scope, not just the named task."""
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    asking = await _seed_task(title="Request approval")
    await _seed_task(
        title="Launch instance",
        depends_on_ids=[asking],
        tool_bindings=[(server_id, "launch")],
    )
    result = await request_approval(
        "Approve the launch",
        _ctx(),
        asking,
        approved_calls=[],
        approver="alice",
    )
    assert "error" in result
    assert "launch" in result["error"]


async def test_request_approval_rejects_a_declaration_naming_an_unbound_tool(
    engine: AsyncEngine,
) -> None:
    """Showing the approver a call that can never happen is refused too."""
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    task_id = await _seed_task(
        title="Launch instance", tool_bindings=[(server_id, "launch")]
    )
    result = await request_approval(
        "Approve the launch",
        _ctx(),
        task_id,
        approved_calls=_declare(server_id, "launch") + _declare(server_id, "terminate"),
        approver="alice",
    )
    assert "error" in result
    assert "terminate" in result["error"]


async def test_request_approval_ignores_tools_bound_upstream_when_declaring(
    engine: AsyncEngine,
) -> None:
    """An approval reaches forward only, so upstream tools need no declaration."""
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    upstream = await _seed_task(
        title="Gather sources", tool_bindings=[(server_id, "search")]
    )
    asking = await _seed_task(title="Request approval", depends_on_ids=[upstream])
    result = await request_approval(
        "Approve the wording", _ctx(), asking, approver="alice"
    )
    assert "error" not in result, result


async def test_request_approval_rejects_a_malformed_constraint(
    engine: AsyncEngine,
) -> None:
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    task_id = await _seed_task(
        title="Launch instance", tool_bindings=[(server_id, "launch")]
    )
    result = await request_approval(
        "Approve the launch",
        _ctx(),
        task_id,
        approved_calls=_declare(server_id, "launch", region={"eq": "a", "in": ["a"]}),
        approver="alice",
    )
    assert "error" in result
    assert "exactly one" in result["error"]


async def test_request_approval_reports_every_malformed_constraint_at_once(
    engine: AsyncEngine,
) -> None:
    """One round trip should be enough for the agent to fix the whole thing."""
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    task_id = await _seed_task(
        title="Launch instance", tool_bindings=[(server_id, "launch")]
    )
    result = await request_approval(
        "Approve the launch",
        _ctx(),
        task_id,
        approved_calls=_declare(server_id, "launch", region={}, count={"lte": "many"}),
        approver="alice",
    )
    assert "error" in result
    assert "region" in result["error"]
    assert "count" in result["error"]


async def test_request_approval_rejects_a_declaration_of_the_wrong_shape(
    engine: AsyncEngine,
) -> None:
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    task_id = await _seed_task(
        title="Launch instance", tool_bindings=[(server_id, "launch")]
    )
    result = await request_approval(
        "Approve the launch",
        _ctx(),
        task_id,
        approved_calls=[{"tool_name": "launch"}],  # no mcp_server_id
        approver="alice",
    )
    assert "error" in result


async def test_request_approval_stores_the_declaration(engine: AsyncEngine) -> None:
    """What the approver reads and what the gate enforces are the same bytes."""
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    task_id = await _seed_task(
        title="Launch instance", tool_bindings=[(server_id, "launch")]
    )
    result = await request_approval(
        "Approve the launch",
        _ctx(),
        task_id,
        approved_calls=_declare(
            server_id, "launch", region={"eq": "ap-northeast-1"}, count={"lte": 2}
        ),
        approver="alice",
    )
    assert "error" not in result, result

    async with AsyncSession(engine) as db:
        approval = await db.get(Approval, result["approval_id"])
    assert approval is not None
    assert approval.approved_calls == [
        {
            "mcp_server_id": server_id,
            "tool_name": "launch",
            "arguments": {"region": {"eq": "ap-northeast-1"}, "count": {"lte": 2}},
            "unconstrained_arguments": False,
        }
    ]


# ---------- tools the design exempted from input approval ----------


async def test_request_approval_does_not_require_an_exempt_tool_to_be_declared(
    engine: AsyncEngine,
) -> None:
    """A read-only tool has no arguments worth an approver's agreement.

    This is the whole point of the exemption: the agent may still be exploring
    when it asks, so there is no honest declaration it could write for such a
    tool, and demanding one would only produce a made-up bound.
    """
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    task_id = await _seed_task(
        title="Look and launch",
        tool_bindings=[(server_id, "launch"), (server_id, "list_instances")],
        input_approval_exempt=[(server_id, "list_instances")],
    )
    result = await request_approval(
        "Approve the launch",
        _ctx(),
        task_id,
        approved_calls=_declare(server_id, "launch", region={"eq": "ap-northeast-1"}),
        approver="alice",
    )
    assert "error" not in result, result


async def test_request_approval_records_an_exempt_tool_as_unconstrained(
    engine: AsyncEngine,
) -> None:
    """Left out of the request, the tool is still named in what was approved.

    The approver reads one list, and the gate matches against that same list, so
    a covered tool missing from it would be a hole in both.
    """
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    task_id = await _seed_task(
        title="Look and launch",
        tool_bindings=[(server_id, "launch"), (server_id, "list_instances")],
        input_approval_exempt=[(server_id, "list_instances")],
    )
    result = await request_approval(
        "Approve the launch",
        _ctx(),
        task_id,
        approved_calls=_declare(server_id, "launch", region={"eq": "ap-northeast-1"}),
        approver="alice",
    )
    assert "error" not in result, result

    async with AsyncSession(engine) as db:
        approval = await db.get(Approval, result["approval_id"])
    assert approval is not None
    assert approval.approved_calls == [
        {
            "mcp_server_id": server_id,
            "tool_name": "launch",
            "arguments": {"region": {"eq": "ap-northeast-1"}},
            "unconstrained_arguments": False,
        },
        {
            "mcp_server_id": server_id,
            "tool_name": "list_instances",
            "arguments": {},
            "unconstrained_arguments": True,
        },
    ]


async def test_request_approval_rejects_a_declaration_naming_an_exempt_tool(
    engine: AsyncEngine,
) -> None:
    """One rule, both ways: the declaration names the constrained tools exactly.

    The error has to say *why* this one is extra — the tool really is bound to a
    covered task, so the ordinary "nothing binds it" message would read as wrong.
    """
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    task_id = await _seed_task(
        title="Look and launch",
        tool_bindings=[(server_id, "launch"), (server_id, "list_instances")],
        input_approval_exempt=[(server_id, "list_instances")],
    )
    result = await request_approval(
        "Approve the launch",
        _ctx(),
        task_id,
        approved_calls=_declare(server_id, "launch")
        + _declare(server_id, "list_instances"),
        approver="alice",
    )
    assert "error" in result
    assert "list_instances" in result["error"]
    assert "exempted from input approval" in result["error"]


async def test_request_approval_refuses_a_run_that_exempts_itself(
    engine: AsyncEngine,
) -> None:
    """Which tools go unbounded is the design's call, never the requesting run's."""
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    task_id = await _seed_task(
        title="Launch instance", tool_bindings=[(server_id, "launch")]
    )
    result = await request_approval(
        "Approve the launch",
        _ctx(),
        task_id,
        approved_calls=[
            {
                "mcp_server_id": server_id,
                "tool_name": "launch",
                "arguments": {},
                "unconstrained_arguments": True,
            }
        ],
        approver="alice",
    )
    assert "error" in result
    assert "unconstrained_arguments" in result["error"]


async def test_request_approval_lets_the_stricter_covered_task_decide(
    engine: AsyncEngine,
) -> None:
    """One approval, two steps disagreeing: the one wanting bounds wins.

    The decision covers both steps at once, so the laxer binding must not speak
    for the stricter one.
    """
    await _seed_session(engine)
    server_id = await _seed_mcp_server(engine)
    asking = await _seed_task(
        title="Read only",
        tool_bindings=[(server_id, "run")],
        input_approval_exempt=[(server_id, "run")],
    )
    await _seed_task(
        title="Run for real",
        depends_on_ids=[asking],
        tool_bindings=[(server_id, "run")],
    )
    omitted = await request_approval(
        "Approve the run", _ctx(), asking, approved_calls=[], approver="alice"
    )
    assert "error" in omitted
    assert "run" in omitted["error"]

    declared = await request_approval(
        "Approve the run",
        _ctx(),
        asking,
        approved_calls=_declare(server_id, "run", target={"eq": "job-1"}),
        approver="alice",
    )
    assert "error" not in declared, declared
