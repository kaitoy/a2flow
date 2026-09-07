"""Tests for the session-file upload and download endpoints.

The two things worth pinning down here are the access split -- uploading needs
the same standing as driving the run, downloading only the standing to read it --
and the storage rules: sizes are capped, names are reduced to a bare filename,
and nothing already stored is ever replaced.
"""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from models.session_file import SessionFile
from tests._envelope import assert_err, assert_ok
from tests._workflow import create_published_workflow, create_skill

#: Headers of the user every test starts the run as, so the initiator is a plain
#: participant rather than a super admin who would pass every check anyway.
ALICE = {"X-User-Id": "alice", "X-User-Roles": "requester"}

#: A user with no part in the run at all.
BOB = {"X-User-Id": "bob", "X-User-Roles": "requester"}

#: A tenant admin: may read any run in the tenant, may act on none.
ADMIN = {"X-User-Id": "carol", "X-User-Roles": "admin"}


async def _execute(client: AsyncClient) -> Any:
    """Start a run initiated by ``alice`` and return its execution record."""
    skill = await create_skill(client)
    workflow = await create_published_workflow(client, skill["id"])
    return assert_ok(
        await client.post(f"/api/v1/workflows/{workflow['id']}/execute", headers=ALICE),
        status=201,
    )


async def _upload(
    client: AsyncClient,
    execution_id: str,
    *,
    name: str = "notes.txt",
    content: bytes = b"hello",
    content_type: str = "text/plain",
    headers: dict[str, str] | None = None,
) -> Any:
    """Upload one file and return the raw response."""
    return await client.post(
        f"/api/v1/workflow-executions/{execution_id}/files",
        files={"file": (name, content, content_type)},
        headers=ALICE if headers is None else headers,
    )


@pytest.mark.asyncio
async def test_upload_session_file_returns_its_metadata(
    workflow_client: AsyncClient,
) -> None:
    execution = await _execute(workflow_client)
    data = assert_ok(
        await _upload(workflow_client, execution["id"], content=b"hello there"),
        status=201,
    )
    assert data["name"] == "notes.txt"
    assert data["contentType"] == "text/plain"
    assert data["sizeBytes"] == len(b"hello there")
    assert data["origin"] == "user"
    assert data["workflowExecutionId"] == execution["id"]


@pytest.mark.asyncio
async def test_upload_session_file_never_returns_the_bytes(
    workflow_client: AsyncClient,
) -> None:
    """The read schema omits ``data``, so an upload response cannot leak content."""
    execution = await _execute(workflow_client)
    data = assert_ok(await _upload(workflow_client, execution["id"]), status=201)
    assert "data" not in data


@pytest.mark.asyncio
async def test_upload_session_file_strips_the_path_from_the_name(
    workflow_client: AsyncClient,
) -> None:
    execution = await _execute(workflow_client)
    data = assert_ok(
        await _upload(workflow_client, execution["id"], name="../../etc/passwd"),
        status=201,
    )
    assert data["name"] == "passwd"


@pytest.mark.asyncio
async def test_upload_session_file_renames_instead_of_overwriting(
    workflow_client: AsyncClient,
) -> None:
    """A second upload under a taken name gets a variant; the first is untouched."""
    execution = await _execute(workflow_client)
    first = assert_ok(
        await _upload(workflow_client, execution["id"], content=b"original"), status=201
    )
    second = assert_ok(
        await _upload(workflow_client, execution["id"], content=b"replacement"),
        status=201,
    )
    assert first["name"] == "notes.txt"
    assert second["name"] == "notes (2).txt"

    still_there = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/files/{first['id']}/content",
        headers=ALICE,
    )
    assert still_there.content == b"original"


@pytest.mark.asyncio
async def test_upload_session_file_rejects_an_empty_file(
    workflow_client: AsyncClient,
) -> None:
    execution = await _execute(workflow_client)
    error = assert_err(
        await _upload(workflow_client, execution["id"], content=b""),
        code="INVALID_SESSION_FILE",
        status=422,
    )
    assert "empty" in error["details"]["reason"].lower()


@pytest.mark.asyncio
async def test_upload_session_file_rejects_an_unusable_name(
    workflow_client: AsyncClient,
) -> None:
    execution = await _execute(workflow_client)
    assert_err(
        await _upload(workflow_client, execution["id"], name=".."),
        code="INVALID_SESSION_FILE",
        status=422,
    )


@pytest.mark.asyncio
async def test_upload_session_file_rejects_a_file_over_the_per_file_limit(
    workflow_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SESSION_FILE_MAX_BYTES", "16")
    get_settings.cache_clear()
    execution = await _execute(workflow_client)
    error = assert_err(
        await _upload(workflow_client, execution["id"], content=b"x" * 17),
        code="INVALID_SESSION_FILE",
        status=422,
    )
    assert "size limit" in error["details"]["reason"]


@pytest.mark.asyncio
async def test_upload_session_file_rejects_a_file_over_the_session_limit(
    workflow_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SESSION_FILES_MAX_TOTAL_BYTES", "10")
    get_settings.cache_clear()
    execution = await _execute(workflow_client)
    assert_ok(
        await _upload(workflow_client, execution["id"], content=b"x" * 8), status=201
    )
    error = assert_err(
        await _upload(workflow_client, execution["id"], content=b"y" * 8),
        code="INVALID_SESSION_FILE",
        status=422,
    )
    assert "total size limit" in error["details"]["reason"]


@pytest.mark.asyncio
async def test_upload_session_file_unknown_execution_returns_404(
    workflow_client: AsyncClient,
) -> None:
    assert_err(
        await _upload(workflow_client, "nonexistent"), code="NOT_FOUND", status=404
    )


@pytest.mark.asyncio
async def test_upload_session_file_rejects_a_non_participant(
    workflow_client: AsyncClient,
) -> None:
    execution = await _execute(workflow_client)
    assert_err(
        await _upload(workflow_client, execution["id"], headers=BOB),
        code="FORBIDDEN",
        status=403,
    )


@pytest.mark.asyncio
async def test_upload_session_file_rejects_a_plain_admin(
    workflow_client: AsyncClient,
) -> None:
    """An admin may read a run they have no part in, but not feed its agent."""
    execution = await _execute(workflow_client)
    assert_err(
        await _upload(workflow_client, execution["id"], headers=ADMIN),
        code="FORBIDDEN",
        status=403,
    )


@pytest.mark.asyncio
async def test_download_session_file_serves_it_as_an_attachment(
    workflow_client: AsyncClient,
) -> None:
    execution = await _execute(workflow_client)
    stored = assert_ok(
        await _upload(
            workflow_client,
            execution["id"],
            name="report.csv",
            content=b"a,b\n1,2\n",
            content_type="text/csv",
        ),
        status=201,
    )
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/files/{stored['id']}/content",
        headers=ALICE,
    )
    assert response.status_code == 200
    assert response.content == b"a,b\n1,2\n"
    # Never the recorded type: an uploaded file is never rendered by the browser.
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["x-content-type-options"] == "nosniff"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert 'filename="report.csv"' in disposition


@pytest.mark.asyncio
async def test_download_session_file_encodes_a_non_ascii_name(
    workflow_client: AsyncClient,
) -> None:
    execution = await _execute(workflow_client)
    stored = assert_ok(
        await _upload(workflow_client, execution["id"], name="レポート.txt"), status=201
    )
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/files/{stored['id']}/content",
        headers=ALICE,
    )
    disposition = response.headers["content-disposition"]
    assert "filename*=UTF-8''" in disposition
    assert "%E3%83%AC" in disposition


@pytest.mark.asyncio
async def test_download_session_file_allows_a_plain_admin(
    workflow_client: AsyncClient,
) -> None:
    execution = await _execute(workflow_client)
    stored = assert_ok(await _upload(workflow_client, execution["id"]), status=201)
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/files/{stored['id']}/content",
        headers=ADMIN,
    )
    assert response.status_code == 200
    assert response.content == b"hello"


@pytest.mark.asyncio
async def test_download_session_file_rejects_a_non_participant(
    workflow_client: AsyncClient,
) -> None:
    execution = await _execute(workflow_client)
    stored = assert_ok(await _upload(workflow_client, execution["id"]), status=201)
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/files/{stored['id']}/content",
        headers=BOB,
    )
    assert_err(response, code="FORBIDDEN", status=403)


@pytest.mark.asyncio
async def test_download_session_file_from_another_run_returns_404(
    workflow_client: AsyncClient,
) -> None:
    """A file id is only ever resolved within its own session."""
    skill = await create_skill(workflow_client)
    workflow = await create_published_workflow(workflow_client, skill["id"])
    first, second = [
        assert_ok(
            await workflow_client.post(
                f"/api/v1/workflows/{workflow['id']}/execute", headers=ALICE
            ),
            status=201,
        )
        for _ in range(2)
    ]
    stored = assert_ok(await _upload(workflow_client, first["id"]), status=201)
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{second['id']}/files/{stored['id']}/content",
        headers=ALICE,
    )
    assert_err(response, code="NOT_FOUND", status=404)


@pytest.mark.asyncio
async def test_agent_run_is_told_which_files_the_session_holds(
    workflow_client: AsyncClient, mock_adk_agent: MagicMock
) -> None:
    """The agent learns what is attached from the server, never from the client.

    The frontend uploads a file and then sends an ordinary message; nothing it
    sends says which files exist. The run's context is where that list comes
    from, which is what makes it trustworthy.
    """
    execution = await _execute(workflow_client)
    assert_ok(
        await _upload(workflow_client, execution["id"], name="input.csv"), status=201
    )

    received: list[Any] = []

    async def _capturing_run(
        input_data: Any, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[Any, None]:
        received.append(input_data)
        return
        yield

    mock_adk_agent.run = _capturing_run

    await workflow_client.post(
        f"/api/v1/workflow-executions/{execution['id']}/agent",
        json={
            "threadId": "thread-001",
            "runId": "run-001",
            "state": {},
            "messages": [],
            "tools": [],
            "context": [],
            "forwardedProps": {},
        },
        headers=ALICE,
    )

    entries = {c.description: c.value for c in received[0].context}
    assert "Files attached to this session" in entries
    assert "input.csv" in entries["Files attached to this session"]


@pytest.mark.asyncio
async def test_deleting_the_execution_removes_its_files(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """The cascade is the whole persistence rule: files live as long as their run."""
    client, engine = workflow_client_with_engine
    execution = await _execute(client)
    assert_ok(await _upload(client, execution["id"]), status=201)

    async with AsyncSession(engine) as db:
        before = (await db.exec(select(SessionFile))).all()
    assert len(before) == 1

    assert_ok(await client.delete(f"/api/v1/workflow-executions/{execution['id']}"))

    async with AsyncSession(engine) as db:
        after = (await db.exec(select(SessionFile))).all()
    assert after == []
