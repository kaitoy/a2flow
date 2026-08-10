"""Tests for the design agent tools in ``infrastructure.design_task_tools``.

The tools open their own ``AsyncSession`` on ``infrastructure.database.engine``;
each test monkeypatches that engine to an isolated in-memory SQLite database and
drives the tools with a lightweight fake ToolContext exposing only ``session.id``
and ``user_id`` (the attributes the tools read). Unlike the session-task tools,
these resolve the Workflow whose design session the run is in, and edit that
workflow's task templates.
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

from infrastructure.design_task_tools import (
    create_design_task,
    delete_design_task,
    get_design_task,
    list_design_tasks,
    register_design_tasks,
    update_design_task,
)
from models.agent_skill import AgentSkill
from models.workflow import Workflow, WorkflowStatus
from repositories.tenant_bootstrap import resolve_workflow_design_tenant
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users


async def _workflow_status(eng: AsyncEngine, workflow_id: str) -> WorkflowStatus:
    """Read a workflow's current lifecycle status straight from the database."""
    async with AsyncSession(eng) as db:
        workflow = await db.get(Workflow, workflow_id)
        assert workflow is not None
        return workflow.status


async def _set_workflow_status(
    eng: AsyncEngine, workflow_id: str, status: WorkflowStatus
) -> None:
    """Force a workflow's lifecycle status, for tests that publish after seeding."""
    async with AsyncSession(eng) as db:
        workflow = await db.get(Workflow, workflow_id)
        assert workflow is not None
        workflow.status = status
        db.add(workflow)
        await db.commit()


async def _generation_error(eng: AsyncEngine, workflow_id: str) -> str | None:
    """Read a workflow's recorded design-run failure reason."""
    async with AsyncSession(eng) as db:
        workflow = await db.get(Workflow, workflow_id)
        assert workflow is not None
        return workflow.generation_error


async def _set_generation_error(
    eng: AsyncEngine, workflow_id: str, reason: str
) -> None:
    """Record a design-run failure reason, as the generation job would."""
    async with AsyncSession(eng) as db:
        workflow = await db.get(Workflow, workflow_id)
        assert workflow is not None
        workflow.generation_error = reason
        db.add(workflow)
        await db.commit()


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
    await seed_users(eng)
    await seed_tenant(eng)

    monkeypatch.setattr("infrastructure.database.engine", eng)
    yield eng
    await eng.dispose()


async def _seed_design_session(
    eng: AsyncEngine,
    *,
    session_id: str = "design-abc",
    user_id: str = "owner",
    status: WorkflowStatus = WorkflowStatus.draft,
) -> str:
    """Insert a skill + workflow whose design session is ``session_id``.

    ``status`` seeds the workflow's lifecycle state so tests can exercise the
    ``published`` → ``modified`` transition the write tools trigger.

    Returns:
        The workflow's primary key.
    """
    async with AsyncSession(eng) as db:
        skill = AgentSkill(
            name=f"skill-{session_id}",
            repo_url="https://example.com/repo",
            repo_path="",
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(skill)
        await db.commit()
        await db.refresh(skill)

        skill_id = skill.id
        workflow = Workflow(
            name=f"wf-{session_id}",
            agent_skill_id=skill_id,
            session_id=session_id,
            agent_skill_commit_sha="a" * 40,
            status=status,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)
        return workflow.id


def _ctx(
    session_id: str = "design-abc",
    user_id: str = "tester",
    *,
    state: dict[str, Any] | None = None,
) -> Any:
    """Build a fake ToolContext exposing ``session.id``, ``user_id``, and ``state``."""
    return SimpleNamespace(
        session=SimpleNamespace(id=session_id), user_id=user_id, state=state
    )


# ---------- register ----------


async def test_register_design_tasks_creates_dag(engine: AsyncEngine) -> None:
    await _seed_design_session(engine)
    result = await register_design_tasks(
        [
            {"key": "t0", "title": "First"},
            {"key": "t1", "title": "Second", "depends_on": ["t0"]},
            {"key": "t2", "title": "Third", "depends_on": ["t0", "t1"]},
        ],
        _ctx(),
    )
    assert "error" not in result
    created = result["created"]
    assert [c["key"] for c in created] == ["t0", "t1", "t2"]
    ids = {c["key"]: c["id"] for c in created}

    listed = await list_design_tasks(_ctx())
    tasks = {t["title"]: t for t in listed["tasks"]}
    assert tasks["Second"]["depends_on_ids"] == [ids["t0"]]
    assert sorted(tasks["Third"]["depends_on_ids"]) == sorted([ids["t0"], ids["t1"]])
    # Templates are created in dependency order, and have no status — the
    # lifecycle belongs to a run.
    assert [t["title"] for t in listed["tasks"]] == ["First", "Second", "Third"]
    assert all("status" not in t for t in listed["tasks"])


async def test_register_rejects_unknown_dependency(engine: AsyncEngine) -> None:
    await _seed_design_session(engine)
    result = await register_design_tasks(
        [{"key": "a", "title": "A", "depends_on": ["missing"]}], _ctx()
    )
    assert "error" in result
    listed = await list_design_tasks(_ctx())
    assert listed["tasks"] == []


async def test_register_rejects_duplicate_key(engine: AsyncEngine) -> None:
    await _seed_design_session(engine)
    result = await register_design_tasks(
        [{"key": "a", "title": "A"}, {"key": "a", "title": "B"}], _ctx()
    )
    assert "error" in result


async def test_register_rejects_cycle(engine: AsyncEngine) -> None:
    await _seed_design_session(engine)
    result = await register_design_tasks(
        [
            {"key": "a", "title": "A", "depends_on": ["b"]},
            {"key": "b", "title": "B", "depends_on": ["a"]},
        ],
        _ctx(),
    )
    assert "error" in result
    assert "cycle" in result["error"]


async def test_register_rejects_missing_title(engine: AsyncEngine) -> None:
    await _seed_design_session(engine)
    result = await register_design_tasks([{"key": "a"}], _ctx())
    assert "error" in result


async def test_register_rejects_overlong_title(engine: AsyncEngine) -> None:
    # A title long enough to blow out the "Depends on" chip comes back as a
    # correctable error payload, with nothing written — not as a Pydantic
    # ValidationError escaping the tool and failing the whole agent run.
    await _seed_design_session(engine)
    result = await register_design_tasks(
        [
            {"key": "a", "title": "Gather sources"},
            {
                "key": "b",
                "title": "Validate the uploaded CSV schema against the contract",
            },
        ],
        _ctx(),
    )
    assert "error" in result
    assert "53 characters" in result["error"]
    listed = await list_design_tasks(_ctx())
    assert listed["tasks"] == []


async def test_register_accepts_a_title_at_the_limit(engine: AsyncEngine) -> None:
    await _seed_design_session(engine)
    at_limit = "T" * 30
    result = await register_design_tasks([{"key": "a", "title": at_limit}], _ctx())
    assert "error" not in result
    listed = await list_design_tasks(_ctx())
    assert [t["title"] for t in listed["tasks"]] == [at_limit]


async def test_create_rejects_overlong_title(engine: AsyncEngine) -> None:
    await _seed_design_session(engine)
    result = await create_design_task("T" * 31, _ctx())
    assert "error" in result
    listed = await list_design_tasks(_ctx())
    assert listed["tasks"] == []


async def test_update_rejects_overlong_title(engine: AsyncEngine) -> None:
    await _seed_design_session(engine)
    created = await create_design_task("Original", _ctx())
    result = await update_design_task(created["id"], _ctx(), title="T" * 31)
    assert "error" in result
    unchanged = await get_design_task(created["id"], _ctx())
    assert unchanged["title"] == "Original"


async def test_register_without_session_errors(engine: AsyncEngine) -> None:
    result = await register_design_tasks(
        [{"key": "a", "title": "A"}], _ctx("unknown-session")
    )
    assert "error" in result


# ---------- single-template CRUD ----------


async def test_create_design_task(engine: AsyncEngine) -> None:
    await _seed_design_session(engine)
    result = await create_design_task("Solo", _ctx())
    assert result["title"] == "Solo"
    assert "status" not in result


async def test_create_design_task_attributes_to_acting_user(
    engine: AsyncEngine,
) -> None:
    """The router-stamped acting user, not the session's fixed owner, is recorded.

    ``owner`` is the ADK session's ``tool_context.user_id`` (the workflow's
    creator), but ``alice`` is the per-turn acting user impersonation would
    stamp into state -- ``created_by``/``updated_by`` must follow ``alice``.
    """
    from infrastructure.workflow_task_tools import ACTING_USER_STATE_KEY
    from models.workflow_task_template import WorkflowTaskTemplate

    await _seed_design_session(engine, user_id="owner")
    result = await create_design_task(
        "Solo", _ctx(user_id="owner", state={ACTING_USER_STATE_KEY: "alice"})
    )
    async with AsyncSession(engine) as db:
        template = await db.get(WorkflowTaskTemplate, result["id"])
    assert template is not None
    assert template.created_by == "alice"
    assert template.updated_by == "alice"


async def test_list_isolates_workflows(engine: AsyncEngine) -> None:
    await _seed_design_session(engine, session_id="design-a")
    await _seed_design_session(engine, session_id="design-b")
    await create_design_task("In A", _ctx("design-a"))
    await create_design_task("In B", _ctx("design-b"))
    listed_a = await list_design_tasks(_ctx("design-a"))
    assert [t["title"] for t in listed_a["tasks"]] == ["In A"]


async def test_get_design_task_cross_workflow_guard(engine: AsyncEngine) -> None:
    await _seed_design_session(engine, session_id="design-a")
    await _seed_design_session(engine, session_id="design-b")
    created = await create_design_task("Owned by A", _ctx("design-a"))
    template_id = created["id"]

    blocked = await get_design_task(template_id, _ctx("design-b"))
    assert "error" in blocked
    allowed = await get_design_task(template_id, _ctx("design-a"))
    assert allowed["id"] == template_id


async def test_update_dependencies(engine: AsyncEngine) -> None:
    await _seed_design_session(engine)
    a = await create_design_task("A", _ctx())
    b = await create_design_task("B", _ctx())
    updated = await update_design_task(b["id"], _ctx(), depends_on_ids=[a["id"]])
    assert updated["depends_on_ids"] == [a["id"]]


async def test_update_dependency_cycle_rejected(engine: AsyncEngine) -> None:
    await _seed_design_session(engine)
    a = await create_design_task("A", _ctx())
    b = await create_design_task("B", _ctx(), depends_on_ids=[a["id"]])
    result = await update_design_task(a["id"], _ctx(), depends_on_ids=[b["id"]])
    assert "error" in result


async def test_update_preserves_unset_fields(engine: AsyncEngine) -> None:
    await _seed_design_session(engine)
    created = await create_design_task("Original", _ctx(), description="desc")
    updated = await update_design_task(
        created["id"], _ctx(), description="updated desc"
    )
    assert updated["title"] == "Original"
    assert updated["description"] == "updated desc"


async def test_delete_design_task(engine: AsyncEngine) -> None:
    await _seed_design_session(engine)
    created = await create_design_task("Temp", _ctx())
    result = await delete_design_task(created["id"], _ctx())
    assert result == {"deleted": created["id"]}
    listed = await list_design_tasks(_ctx())
    assert listed["tasks"] == []


async def test_delete_cross_workflow_guard(engine: AsyncEngine) -> None:
    await _seed_design_session(engine, session_id="design-a")
    await _seed_design_session(engine, session_id="design-b")
    created = await create_design_task("A", _ctx("design-a"))
    result = await delete_design_task(created["id"], _ctx("design-b"))
    assert "error" in result


# ---------- session resolution ----------


async def test_resolve_workflow_design_tenant(engine: AsyncEngine) -> None:
    workflow_id = await _seed_design_session(engine, session_id="design-x")
    async with AsyncSession(engine) as db:
        assert await resolve_workflow_design_tenant(db, "design-x") == (
            workflow_id,
            DEFAULT_TEST_TENANT_ID,
        )
        assert await resolve_workflow_design_tenant(db, "absent") is None


# ---------- tool bindings ----------


async def _seed_mcp_server(eng: AsyncEngine, *, name: str = "srv") -> str:
    """Insert an MCPServer owned by the seeded system user and return its id."""
    from models.mcp_server import MCPServer
    from models.user import SYSTEM_USER_ID

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


async def test_register_with_tools_binds_them(engine: AsyncEngine) -> None:
    await _seed_design_session(engine)
    server_id = await _seed_mcp_server(engine)
    result = await register_design_tasks(
        [
            {
                "key": "t0",
                "title": "Search",
                "tools": [{"server_id": server_id, "tool_name": "search"}],
            }
        ],
        _ctx(),
    )
    assert "error" not in result
    listed = await list_design_tasks(_ctx())
    assert listed["tasks"][0]["tool_bindings"] == [
        {"server_id": server_id, "tool_name": "search"}
    ]


async def test_register_with_malformed_tools_errors(engine: AsyncEngine) -> None:
    await _seed_design_session(engine)
    result = await register_design_tasks(
        [{"key": "t0", "title": "Bad", "tools": [{"server_id": "only"}]}], _ctx()
    )
    assert "error" in result
    listed = await list_design_tasks(_ctx())
    assert listed["tasks"] == []


async def test_register_with_unknown_server_errors(engine: AsyncEngine) -> None:
    await _seed_design_session(engine)
    result = await register_design_tasks(
        [
            {
                "key": "t0",
                "title": "Bad",
                "tools": [{"server_id": "ghost", "tool_name": "search"}],
            }
        ],
        _ctx(),
    )
    assert "error" in result


async def test_update_replaces_tool_bindings(engine: AsyncEngine) -> None:
    await _seed_design_session(engine)
    server_id = await _seed_mcp_server(engine)
    created = await create_design_task(
        "Solo",
        _ctx(),
        tool_bindings=[{"server_id": server_id, "tool_name": "search"}],
    )
    result = await update_design_task(
        created["id"],
        _ctx(),
        tool_bindings=[{"server_id": server_id, "tool_name": "fetch"}],
    )
    assert result["tool_bindings"] == [{"server_id": server_id, "tool_name": "fetch"}]


# ---------- published -> modified ----------


async def test_register_marks_published_workflow_modified(engine: AsyncEngine) -> None:
    workflow_id = await _seed_design_session(engine, status=WorkflowStatus.published)
    result = await register_design_tasks([{"key": "t0", "title": "First"}], _ctx())
    assert "error" not in result
    assert await _workflow_status(engine, workflow_id) is WorkflowStatus.modified


async def test_create_marks_published_workflow_modified(engine: AsyncEngine) -> None:
    workflow_id = await _seed_design_session(engine, status=WorkflowStatus.published)
    await create_design_task("Solo", _ctx())
    assert await _workflow_status(engine, workflow_id) is WorkflowStatus.modified


async def test_update_marks_published_workflow_modified(engine: AsyncEngine) -> None:
    workflow_id = await _seed_design_session(engine)
    created = await create_design_task("Solo", _ctx())
    await _set_workflow_status(engine, workflow_id, WorkflowStatus.published)

    await update_design_task(created["id"], _ctx(), title="Renamed")
    assert await _workflow_status(engine, workflow_id) is WorkflowStatus.modified


async def test_delete_marks_published_workflow_modified(engine: AsyncEngine) -> None:
    workflow_id = await _seed_design_session(engine)
    created = await create_design_task("Temp", _ctx())
    await _set_workflow_status(engine, workflow_id, WorkflowStatus.published)

    await delete_design_task(created["id"], _ctx())
    assert await _workflow_status(engine, workflow_id) is WorkflowStatus.modified


async def test_reads_leave_published_workflow_alone(engine: AsyncEngine) -> None:
    workflow_id = await _seed_design_session(engine)
    created = await create_design_task("Solo", _ctx())
    await _set_workflow_status(engine, workflow_id, WorkflowStatus.published)

    await list_design_tasks(_ctx())
    await get_design_task(created["id"], _ctx())
    assert await _workflow_status(engine, workflow_id) is WorkflowStatus.published


async def test_failed_write_leaves_published_workflow_alone(
    engine: AsyncEngine,
) -> None:
    workflow_id = await _seed_design_session(engine, status=WorkflowStatus.published)
    result = await create_design_task("Bad", _ctx(), depends_on_ids=["ghost"])
    assert "error" in result
    assert await _workflow_status(engine, workflow_id) is WorkflowStatus.published


async def test_draft_workflow_stays_draft(engine: AsyncEngine) -> None:
    workflow_id = await _seed_design_session(engine)
    await create_design_task("Solo", _ctx())
    assert await _workflow_status(engine, workflow_id) is WorkflowStatus.draft


async def test_generating_workflow_stays_generating(engine: AsyncEngine) -> None:
    # The initial background design run registers the task templates while the workflow
    # is still ``generating``; that status is owned by the generation job.
    workflow_id = await _seed_design_session(engine, status=WorkflowStatus.generating)
    result = await register_design_tasks([{"key": "t0", "title": "First"}], _ctx())
    assert "error" not in result
    assert await _workflow_status(engine, workflow_id) is WorkflowStatus.generating


# ---------- failed -> draft ----------


async def test_register_recovers_a_failed_workflow(engine: AsyncEngine) -> None:
    """The design chat is where a failed design run gets repaired.

    Reproduces the user-visible bug: the workflow stayed ``failed`` with a
    stale reason after the user rebuilt its task templates by hand, so the
    design chat kept showing a failure banner for a design that no longer
    existed.
    """
    workflow_id = await _seed_design_session(engine, status=WorkflowStatus.failed)
    await _set_generation_error(engine, workflow_id, "The design agent run failed.")

    result = await register_design_tasks([{"key": "t0", "title": "First"}], _ctx())
    assert "error" not in result
    assert await _workflow_status(engine, workflow_id) is WorkflowStatus.draft
    assert await _generation_error(engine, workflow_id) is None


async def test_update_recovers_a_failed_workflow(engine: AsyncEngine) -> None:
    workflow_id = await _seed_design_session(engine)
    created = await create_design_task("Solo", _ctx())
    await _set_workflow_status(engine, workflow_id, WorkflowStatus.failed)
    await _set_generation_error(engine, workflow_id, "The design agent run failed.")

    await update_design_task(created["id"], _ctx(), title="Renamed")
    assert await _workflow_status(engine, workflow_id) is WorkflowStatus.draft
    assert await _generation_error(engine, workflow_id) is None


async def test_failed_write_leaves_a_failed_workflow_failed(
    engine: AsyncEngine,
) -> None:
    """Nothing landed, so there is nothing repaired to report."""
    workflow_id = await _seed_design_session(engine, status=WorkflowStatus.failed)
    await _set_generation_error(engine, workflow_id, "The design agent run failed.")

    result = await create_design_task("Bad", _ctx(), depends_on_ids=["ghost"])
    assert "error" in result
    assert await _workflow_status(engine, workflow_id) is WorkflowStatus.failed
    assert (
        await _generation_error(engine, workflow_id) == "The design agent run failed."
    )
