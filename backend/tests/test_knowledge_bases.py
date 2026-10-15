"""Integration tests for the knowledge base endpoints and the workflow links.

The background ingest job is replaced by a recorder (``KnowledgeJobDep``):
what is pinned here is that each route records the right state and schedules
the right job, not what the job does -- ``tests/test_knowledge_ingest.py``
covers that.
"""

import io
import zipfile
from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from models.agent_skill import AgentSkill
from models.user import SYSTEM_USER_ID
from models.workflow import Workflow
from repositories.knowledge import SqlKnowledgePageRepository
from services.knowledge_ingest import KnowledgeJobAction
from tests._engine import make_test_engine
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users
from tests.conftest import _install_auth_overrides

_BASE = "/api/v1/knowledge-bases"


@pytest_asyncio.fixture()
async def mem_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Yield a throwaway engine with the schema created and users seeded."""
    eng = await make_test_engine()
    await seed_users(eng)
    await seed_tenant(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture()
async def jobs() -> list[tuple[str, KnowledgeJobAction]]:
    """Collect the ``(source_id, action)`` of every scheduled knowledge job."""
    return []


@pytest_asyncio.fixture()
async def client(
    mem_engine: AsyncEngine, jobs: list[tuple[str, KnowledgeJobAction]]
) -> AsyncGenerator[AsyncClient, None]:
    from dependencies.service import get_knowledge_job
    from infrastructure.database import get_session
    from main import app

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine) as session:
            yield session

    async def record(source_id: str, *, action: KnowledgeJobAction, **_: Any) -> None:
        jobs.append((source_id, action))

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_knowledge_job] = lambda: record
    _install_auth_overrides(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-Id": SYSTEM_USER_ID},
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


async def _create_kb(client: AsyncClient, name: str = "IT") -> str:
    body = assert_ok(
        await client.post(_BASE, json={"name": name, "description": "IT knowledge"}),
        status=201,
    )
    kb_id: str = body["id"]
    return kb_id


async def _seed_workflow(eng: AsyncEngine) -> str:
    """Insert a skill and a workflow on it, returning the workflow's id."""
    async with AsyncSession(eng, expire_on_commit=False) as db:
        skill = AgentSkill(
            name="skill",
            repo_url="https://example.com/repo",
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(skill)
        await db.flush()
        workflow = Workflow(
            name="wf",
            agent_skill_id=skill.id,
            session_id="design-1",
            agent_skill_commit_sha="abc",
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        db.add(workflow)
        await db.commit()
        return workflow.id


# ---------- knowledge base CRUD ----------


async def test_crud_round_trip(client: AsyncClient) -> None:
    kb_id = await _create_kb(client)
    listed = assert_ok(await client.get(_BASE))
    assert [kb["name"] for kb in listed] == ["IT"]
    updated = assert_ok(await client.patch(f"{_BASE}/{kb_id}", json={"name": "Ops"}))
    assert updated["name"] == "Ops"
    assert_ok(await client.delete(f"{_BASE}/{kb_id}"))
    assert_err(await client.get(f"{_BASE}/{kb_id}"), status=404, code="NOT_FOUND")


async def test_duplicate_name_conflicts(client: AsyncClient) -> None:
    await _create_kb(client)
    assert_err(
        await client.post(_BASE, json={"name": "IT"}),
        status=409,
        code="CONFLICT_UNIQUE",
    )


async def test_writes_require_developer(client: AsyncClient) -> None:
    kb_id = await _create_kb(client)
    requester = {"X-User-Roles": "requester"}
    assert_err(
        await client.post(_BASE, json={"name": "x"}, headers=requester),
        status=403,
        code="FORBIDDEN",
    )
    assert_err(
        await client.post(
            f"{_BASE}/{kb_id}/sources/url",
            json={"url": "https://example.com/a"},
            headers=requester,
        ),
        status=403,
        code="FORBIDDEN",
    )
    assert_ok(await client.get(f"{_BASE}/{kb_id}/sources", headers=requester))


# ---------- sources ----------


async def test_url_source_is_registered_pending_and_scheduled(
    client: AsyncClient, jobs: list[tuple[str, KnowledgeJobAction]]
) -> None:
    kb_id = await _create_kb(client)
    source = assert_ok(
        await client.post(
            f"{_BASE}/{kb_id}/sources/url", json={"url": "https://example.com/vpn"}
        ),
        status=201,
    )
    assert source["status"] == "pending"
    assert source["kind"] == "url"
    assert source["citationKey"].startswith("src-")
    assert jobs == [(source["id"], KnowledgeJobAction.ingest)]
    listed = assert_ok(await client.get(f"{_BASE}/{kb_id}/sources"))
    assert [s["id"] for s in listed] == [source["id"]]
    assert "data" not in listed[0]


async def test_url_source_rejects_private_addresses(client: AsyncClient) -> None:
    kb_id = await _create_kb(client)
    assert_err(
        await client.post(
            f"{_BASE}/{kb_id}/sources/url", json={"url": "http://127.0.0.1/admin"}
        ),
        status=422,
        code="VALIDATION_ERROR",
    )


async def test_file_source_is_stored_and_scheduled(
    client: AsyncClient, jobs: list[tuple[str, KnowledgeJobAction]]
) -> None:
    kb_id = await _create_kb(client)
    source = assert_ok(
        await client.post(
            f"{_BASE}/{kb_id}/sources/file",
            files={"file": ("../../manual.txt", b"hello", "text/plain")},
        ),
        status=201,
    )
    assert source["fileName"] == "manual.txt"
    assert source["sizeBytes"] == 5
    assert jobs == [(source["id"], KnowledgeJobAction.ingest)]


async def test_file_source_rejects_unsupported_empty_and_oversized(
    client: AsyncClient, monkeypatch: Any
) -> None:
    kb_id = await _create_kb(client)
    url = f"{_BASE}/{kb_id}/sources/file"
    for files, reason in (
        ({"file": ("deck.pptx", b"x", "application/octet-stream")}, "Unsupported"),
        ({"file": ("empty.txt", b"", "text/plain")}, "empty"),
    ):
        body = assert_err(
            await client.post(url, files=files),
            status=422,
            code="INVALID_KNOWLEDGE_SOURCE",
        )
        assert reason in body["details"]["reason"]

    from config import get_settings

    monkeypatch.setenv("KNOWLEDGE_SOURCE_MAX_BYTES", "4")
    get_settings.cache_clear()
    body = assert_err(
        await client.post(url, files={"file": ("big.txt", b"12345", "text/plain")}),
        status=422,
        code="INVALID_KNOWLEDGE_SOURCE",
    )
    assert "size limit" in body["details"]["reason"]


async def test_delete_source_marks_it_removing_and_schedules_removal(
    client: AsyncClient, jobs: list[tuple[str, KnowledgeJobAction]]
) -> None:
    kb_id = await _create_kb(client)
    source = assert_ok(
        await client.post(
            f"{_BASE}/{kb_id}/sources/url", json={"url": "https://example.com/vpn"}
        ),
        status=201,
    )
    removed = assert_ok(await client.delete(f"{_BASE}/{kb_id}/sources/{source['id']}"))
    assert removed["status"] == "removing"
    assert jobs[-1] == (source["id"], KnowledgeJobAction.remove)
    # A source on its way out cannot be re-ingested.
    assert_err(
        await client.post(f"{_BASE}/{kb_id}/sources/{source['id']}/reingest"),
        status=422,
        code="INVALID_KNOWLEDGE_SOURCE",
    )


async def test_reingest_resets_to_pending(
    client: AsyncClient, jobs: list[tuple[str, KnowledgeJobAction]]
) -> None:
    kb_id = await _create_kb(client)
    source = assert_ok(
        await client.post(
            f"{_BASE}/{kb_id}/sources/url", json={"url": "https://example.com/vpn"}
        ),
        status=201,
    )
    again = assert_ok(
        await client.post(f"{_BASE}/{kb_id}/sources/{source['id']}/reingest")
    )
    assert again["status"] == "pending"
    assert jobs[-1] == (source["id"], KnowledgeJobAction.reingest)


async def test_source_of_another_knowledge_base_is_not_found(
    client: AsyncClient,
) -> None:
    first = await _create_kb(client, "first")
    second = await _create_kb(client, "second")
    source = assert_ok(
        await client.post(
            f"{_BASE}/{first}/sources/url", json={"url": "https://example.com/vpn"}
        ),
        status=201,
    )
    assert_err(
        await client.delete(f"{_BASE}/{second}/sources/{source['id']}"),
        status=404,
        code="NOT_FOUND",
    )


# ---------- pages and export ----------


async def test_pages_list_read_and_export(
    client: AsyncClient, mem_engine: AsyncEngine
) -> None:
    kb_id = await _create_kb(client)
    async with AsyncSession(mem_engine) as db:
        await SqlKnowledgePageRepository(db, tenant_id=DEFAULT_TEST_TENANT_ID).upsert(
            kb_id,
            "/procedures/vpn.md",
            type_="Procedure",
            title="VPN",
            description="Connect remotely.",
            body="Port 443.",
            meta={},
            user_id=SYSTEM_USER_ID,
        )
        await db.commit()

    pages = assert_ok(await client.get(f"{_BASE}/{kb_id}/pages"))
    assert [(p["path"], p["title"]) for p in pages] == [("/procedures/vpn.md", "VPN")]
    page = assert_ok(await client.get(f"{_BASE}/{kb_id}/pages/procedures/vpn.md"))
    assert page["content"].startswith("---\ntype: Procedure\n")
    assert_err(
        await client.get(f"{_BASE}/{kb_id}/pages/missing.md"),
        status=404,
        code="NOT_FOUND",
    )

    response = await client.get(f"{_BASE}/{kb_id}/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert sorted(names) == ["index.md", "procedures/index.md", "procedures/vpn.md"]


# ---------- workflow links ----------


async def test_workflow_links_round_trip(
    client: AsyncClient, mem_engine: AsyncEngine
) -> None:
    workflow_id = await _seed_workflow(mem_engine)
    kb_id = await _create_kb(client)
    url = f"/api/v1/workflows/{workflow_id}/knowledge-bases"
    assert assert_ok(await client.get(url)) == []
    linked = assert_ok(await client.put(url, json={"knowledgeBaseIds": [kb_id, kb_id]}))
    assert [kb["id"] for kb in linked] == [kb_id]
    assert [kb["id"] for kb in assert_ok(await client.get(url))] == [kb_id]
    # Deleting the knowledge base drops the link with it.
    assert_ok(await client.delete(f"{_BASE}/{kb_id}"))
    assert assert_ok(await client.get(url)) == []


async def test_linking_an_unknown_knowledge_base_is_rejected(
    client: AsyncClient, mem_engine: AsyncEngine
) -> None:
    workflow_id = await _seed_workflow(mem_engine)
    assert_err(
        await client.put(
            f"/api/v1/workflows/{workflow_id}/knowledge-bases",
            json={"knowledgeBaseIds": ["nope"]},
        ),
        status=422,
        code="FOREIGN_KEY_VIOLATION",
    )
    assert_err(
        await client.get("/api/v1/workflows/nope/knowledge-bases"),
        status=404,
        code="NOT_FOUND",
    )
