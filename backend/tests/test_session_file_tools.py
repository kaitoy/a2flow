"""Tests for the session-file agent tools in ``infrastructure.session_file_tools``.

Same shape as ``tests/test_workflow_task_tools.py``: the tools open their own
``AsyncSession`` on ``infrastructure.database.engine``, so each test points that
engine at a throwaway database and drives the tools with a fake ToolContext
exposing only the attributes they read.

What these tests are really pinning down is that the agent can add but never
replace, and that one run's files are invisible from another.
"""

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure.session_file_tools import (
    list_session_files,
    read_session_file,
    write_session_file,
)
from infrastructure.workflow_task_tools import ACTING_USER_STATE_KEY
from models.session_file import SessionFile, SessionFileOrigin
from models.workflow_execution import WorkflowExecution
from tests._engine import make_test_engine
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users


@pytest_asyncio.fixture()
async def engine(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[AsyncEngine, None]:
    """Yield a throwaway engine and point the tools' module-level engine at it."""
    eng = await make_test_engine()
    await seed_users(eng)
    await seed_tenant(eng)

    monkeypatch.setattr("infrastructure.database.engine", eng)
    yield eng
    await eng.dispose()


async def _seed_session(
    eng: AsyncEngine,
    *,
    session_id: str = "sess-abc",
    user_id: str = "owner",
) -> str:
    """Insert a WorkflowExecution with the given ADK session id and return its PK."""
    async with AsyncSession(eng) as db:
        execution = WorkflowExecution(
            session_id=session_id,
            name="wf",
            agent_skill_id="skill-1",
            agent_skill_name="skill",
            agent_skill_repo_url="https://example.com/repo",
            agent_skill_repo_path=".",
            initiator_id=user_id,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)
        return execution.id


async def _seed_file(
    eng: AsyncEngine,
    execution_id: str,
    *,
    name: str = "input.txt",
    data: bytes = b"hello",
    content_type: str = "text/plain",
) -> str:
    """Insert a participant-uploaded file straight into the table."""
    async with AsyncSession(eng) as db:
        record = SessionFile(
            workflow_execution_id=execution_id,
            name=name,
            data=data,
            content_type=content_type,
            size_bytes=len(data),
            origin=SessionFileOrigin.user,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by="owner",
            updated_by="owner",
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record.id


def _ctx(
    session_id: str = "sess-abc",
    user_id: str = "tester",
    *,
    state: dict[str, Any] | None = None,
) -> Any:
    """Build a fake ToolContext exposing ``session.id``, ``user_id``, and ``state``."""
    return SimpleNamespace(
        session=SimpleNamespace(id=session_id), user_id=user_id, state=state
    )


async def test_list_session_files_reports_the_session_files(
    engine: AsyncEngine,
) -> None:
    execution_id = await _seed_session(engine)
    file_id = await _seed_file(engine, execution_id, name="input.csv")
    result = await list_session_files(_ctx())
    assert result["files"] == [
        {
            "fileId": file_id,
            "workflowExecutionId": execution_id,
            "name": "input.csv",
            "contentType": "text/plain",
            "sizeBytes": 5,
            "origin": "user",
        }
    ]


async def test_list_session_files_isolates_sessions(engine: AsyncEngine) -> None:
    execution_a = await _seed_session(engine, session_id="sess-a")
    await _seed_session(engine, session_id="sess-b")
    await _seed_file(engine, execution_a, name="only-in-a.txt")
    assert [f["name"] for f in (await list_session_files(_ctx("sess-a")))["files"]] == [
        "only-in-a.txt"
    ]
    assert (await list_session_files(_ctx("sess-b")))["files"] == []


async def test_list_session_files_without_a_session_returns_an_error() -> None:
    result = await list_session_files(_ctx("unknown-session"))
    assert "error" in result


async def test_read_session_file_returns_the_text(engine: AsyncEngine) -> None:
    execution_id = await _seed_session(engine)
    file_id = await _seed_file(engine, execution_id, data="ハロー".encode())
    result = await read_session_file(file_id, _ctx())
    assert result["content"] == "ハロー"
    assert result["name"] == "input.txt"


async def test_read_session_file_refuses_non_text_bytes(engine: AsyncEngine) -> None:
    """An LLM cannot use raw bytes, so saying so beats returning mangled text."""
    execution_id = await _seed_session(engine)
    file_id = await _seed_file(engine, execution_id, data=b"\xff\xfe\x00binary")
    result = await read_session_file(file_id, _ctx())
    assert "not UTF-8 text" in result["error"]


async def test_read_session_file_from_another_session_returns_an_error(
    engine: AsyncEngine,
) -> None:
    execution_a = await _seed_session(engine, session_id="sess-a")
    await _seed_session(engine, session_id="sess-b")
    file_id = await _seed_file(engine, execution_a)
    result = await read_session_file(file_id, _ctx("sess-b"))
    assert result["error"] == f"no file {file_id!r} in this session"


async def test_write_session_file_stores_it_as_agent_output(
    engine: AsyncEngine,
) -> None:
    execution_id = await _seed_session(engine)
    result = await write_session_file(
        "summary.md", "# Findings\n", "text/markdown", _ctx()
    )
    assert result["name"] == "summary.md"
    assert result["origin"] == "agent"
    assert result["contentType"] == "text/markdown"

    async with AsyncSession(engine) as db:
        stored = await db.get(SessionFile, result["fileId"])
    assert stored is not None
    assert stored.data == b"# Findings\n"
    assert stored.workflow_execution_id == execution_id


async def test_write_session_file_attributes_to_the_acting_user(
    engine: AsyncEngine,
) -> None:
    await _seed_session(engine, user_id="owner")
    result = await write_session_file(
        "out.txt", "x", "text/plain", _ctx(state={ACTING_USER_STATE_KEY: "bob"})
    )
    async with AsyncSession(engine) as db:
        stored = await db.get(SessionFile, result["fileId"])
    assert stored is not None
    assert stored.created_by == "bob"


async def test_write_session_file_never_overwrites(engine: AsyncEngine) -> None:
    """The agent may only add: a taken name is stored as a numbered variant."""
    execution_id = await _seed_session(engine)
    await _seed_file(engine, execution_id, name="report.csv", data=b"uploaded")
    result = await write_session_file("report.csv", "generated", "text/csv", _ctx())
    assert result["name"] == "report (2).csv"

    names = {f["name"] for f in (await list_session_files(_ctx()))["files"]}
    assert names == {"report.csv", "report (2).csv"}


async def test_write_session_file_respects_the_size_limit(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SESSION_FILE_MAX_BYTES", "4")
    get_settings.cache_clear()
    await _seed_session(engine)
    result = await write_session_file("big.txt", "far too long", "text/plain", _ctx())
    assert "size limit" in result["error"]


async def test_write_session_file_rejects_an_unusable_name(
    engine: AsyncEngine,
) -> None:
    await _seed_session(engine)
    result = await write_session_file("..", "x", "text/plain", _ctx())
    assert "error" in result
