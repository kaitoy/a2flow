"""Tests for the knowledge ingest job (``services.knowledge_ingest``).

The model is a scripted ``BaseLlm``: each call it makes pops the next list of
tool calls off a script (answering with plain text once the script runs out),
so a test decides exactly which edits "the agent" makes and then checks what
the job did with them -- written back whole, rolled back whole, or cleaned up
after.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from google.adk.models import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.knowledge_extract import FetchedDocument
from models.knowledge import (
    KnowledgeBase,
    KnowledgePage,
    KnowledgeSource,
    KnowledgeSourceKind,
    KnowledgeSourceStatus,
)
from repositories.knowledge import (
    SqlKnowledgePageRepository,
    SqlKnowledgeSourceRepository,
)
from services.knowledge_ingest import (
    KnowledgeIngestService,
    KnowledgeJobAction,
    PageDraft,
    SourceRef,
    WikiEditor,
)
from tests._engine import make_test_engine
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users

_USER = "owner"


class _ScriptedLlm(BaseLlm):
    """Makes the scripted tool calls, one step per model call, then says ``done``."""

    model: str = "scripted"
    script: list[list[tuple[str, dict[str, Any]]]] = Field(default_factory=list)
    prompts: list[str] = Field(default_factory=list)
    fail_after: int | None = None
    calls: int = 0

    async def generate_content_async(
        self, llm_request: Any, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise RuntimeError("model unavailable")
        first = llm_request.contents[0].parts[0].text if llm_request.contents else None
        if first and (not self.prompts or self.prompts[-1] != first):
            self.prompts.append(first)
        step = self.script.pop(0) if self.script else []
        if step:
            parts = [
                types.Part(function_call=types.FunctionCall(name=name, args=args))
                for name, args in step
            ]
        else:
            parts = [types.Part(text="done")]
        yield LlmResponse(content=types.Content(role="model", parts=parts))


@pytest_asyncio.fixture()
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Yield a throwaway engine with users and the default tenant seeded."""
    eng = await make_test_engine()
    await seed_users(eng)
    await seed_tenant(eng)
    yield eng
    await eng.dispose()


async def _seed_kb(eng: AsyncEngine) -> str:
    async with AsyncSession(eng, expire_on_commit=False) as db:
        kb = KnowledgeBase(
            name="IT",
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=_USER,
            updated_by=_USER,
        )
        db.add(kb)
        await db.commit()
        return kb.id


async def _seed_source(
    eng: AsyncEngine,
    kb_id: str,
    *,
    text: str = "VPN uses port 443.",
    file_name: str = "vpn.txt",
    status: KnowledgeSourceStatus = KnowledgeSourceStatus.pending,
) -> KnowledgeSource:
    async with AsyncSession(eng, expire_on_commit=False) as db:
        source = await SqlKnowledgeSourceRepository(
            db, tenant_id=DEFAULT_TEST_TENANT_ID
        ).add(
            kb_id,
            kind=KnowledgeSourceKind.file,
            file_name=file_name,
            content_type="text/plain",
            data=text.encode(),
            user_id=_USER,
        )
        if status is not KnowledgeSourceStatus.pending:
            source.status = status
            db.add(source)
            await db.commit()
        return source


async def _seed_page(
    eng: AsyncEngine, kb_id: str, path: str, keys: list[str], body: str = "Body."
) -> None:
    async with AsyncSession(eng) as db:
        await SqlKnowledgePageRepository(db, tenant_id=DEFAULT_TEST_TENANT_ID).upsert(
            kb_id,
            path,
            type_="Concept",
            title=path,
            description="",
            body=body,
            meta={"sources": [{"id": k, "resource": k, "title": k} for k in keys]},
            user_id=_USER,
        )
        await db.commit()


async def _run(
    eng: AsyncEngine,
    source_id: str,
    action: KnowledgeJobAction,
    llm: BaseLlm,
    **kwargs: Any,
) -> None:
    async with AsyncSession(eng, expire_on_commit=False) as db:
        service = KnowledgeIngestService(
            db, tenant_id=DEFAULT_TEST_TENANT_ID, llm=llm, **kwargs
        )
        await service.run(source_id, action, user_id=_USER)


async def _pages(eng: AsyncEngine, kb_id: str) -> dict[str, KnowledgePage]:
    async with AsyncSession(eng) as db:
        pages = await SqlKnowledgePageRepository(
            db, tenant_id=DEFAULT_TEST_TENANT_ID
        ).list_for(kb_id)
        return {p.path: p for p in pages}


async def _source(eng: AsyncEngine, source_id: str) -> KnowledgeSource | None:
    async with AsyncSession(eng) as db:
        return await SqlKnowledgeSourceRepository(
            db, tenant_id=DEFAULT_TEST_TENANT_ID
        ).get(source_id)


def _write(path: str, key: str, body: str = "Port 443.") -> tuple[str, dict[str, Any]]:
    return (
        "write_page",
        {
            "path": path,
            "page_type": "Procedure",
            "title": "VPN",
            "description": "How to connect.",
            "body": f"{body}[^{key}]\n\n[^{key}]: VPN memo",
            "source_ids": [key],
        },
    )


# ---------- ingest ----------


async def test_ingest_writes_the_agents_pages_and_marks_ready(
    engine: AsyncEngine,
) -> None:
    kb_id = await _seed_kb(engine)
    source = await _seed_source(engine, kb_id)
    key = source.citation_key
    llm = _ScriptedLlm(
        script=[[("list_pages", {})], [_write("/procedures/vpn.md", key)]]
    )

    await _run(engine, source.id, KnowledgeJobAction.ingest, llm)

    pages = await _pages(engine, kb_id)
    assert list(pages) == ["/procedures/vpn.md"]
    page = pages["/procedures/vpn.md"]
    assert page.type == "Procedure"
    assert page.meta["sources"] == [
        {"id": key, "resource": "vpn.txt", "title": "vpn.txt"}
    ]
    assert page.meta["generated"]["by"].startswith("a2flow/")
    stored = await _source(engine, source.id)
    assert stored is not None
    assert stored.status is KnowledgeSourceStatus.ready
    assert stored.ingested_at is not None
    assert key in llm.prompts[0] and "VPN uses port 443." in llm.prompts[0]


async def test_long_source_is_read_in_parts(engine: AsyncEngine) -> None:
    from config import Settings

    kb_id = await _seed_kb(engine)
    source = await _seed_source(engine, kb_id, text="a" * 30 + "\n\n" + "b" * 30)
    llm = _ScriptedLlm()

    await _run(
        engine,
        source.id,
        KnowledgeJobAction.ingest,
        llm,
        settings=Settings(knowledge_ingest_chunk_chars=40),
    )

    assert [("part 1 of 2" in p, "part 2 of 2" in p) for p in llm.prompts] == [
        (True, False),
        (False, True),
    ]


async def test_failure_rolls_back_every_edit_and_records_the_reason(
    engine: AsyncEngine,
) -> None:
    kb_id = await _seed_kb(engine)
    source = await _seed_source(engine, kb_id)
    llm = _ScriptedLlm(
        script=[[_write("/procedures/vpn.md", source.citation_key)]], fail_after=1
    )

    await _run(engine, source.id, KnowledgeJobAction.ingest, llm)

    assert await _pages(engine, kb_id) == {}
    stored = await _source(engine, source.id)
    assert stored is not None
    assert stored.status is KnowledgeSourceStatus.failed
    assert stored.error is not None and "model unavailable" in stored.error


async def test_empty_document_fails_without_calling_the_model(
    engine: AsyncEngine,
) -> None:
    kb_id = await _seed_kb(engine)
    source = await _seed_source(engine, kb_id, text="   ")
    llm = _ScriptedLlm()

    await _run(engine, source.id, KnowledgeJobAction.ingest, llm)

    stored = await _source(engine, source.id)
    assert stored is not None
    assert stored.status is KnowledgeSourceStatus.failed
    assert stored.error is not None and "No text" in stored.error
    assert llm.calls == 0


async def test_url_source_is_fetched(engine: AsyncEngine) -> None:
    kb_id = await _seed_kb(engine)
    async with AsyncSession(engine, expire_on_commit=False) as db:
        source = await SqlKnowledgeSourceRepository(
            db, tenant_id=DEFAULT_TEST_TENANT_ID
        ).add(
            kb_id,
            kind=KnowledgeSourceKind.url,
            url="https://example.com/vpn",
            user_id=_USER,
        )

    async def fetch(url: str, **_: Any) -> FetchedDocument:
        html = b"<html><head><title>VPN guide</title></head><body><p>Hello</p></body></html>"
        return FetchedDocument(html, "text/html", url)

    llm = _ScriptedLlm()
    await _run(engine, source.id, KnowledgeJobAction.ingest, llm, fetch=fetch)

    stored = await _source(engine, source.id)
    assert stored is not None
    assert stored.status is KnowledgeSourceStatus.ready
    assert stored.title == "VPN guide"
    assert "Source title: VPN guide" in llm.prompts[0]


async def test_ingest_of_a_source_marked_for_removal_does_nothing(
    engine: AsyncEngine,
) -> None:
    kb_id = await _seed_kb(engine)
    source = await _seed_source(engine, kb_id, status=KnowledgeSourceStatus.removing)
    llm = _ScriptedLlm()

    await _run(engine, source.id, KnowledgeJobAction.ingest, llm)

    assert llm.calls == 0
    stored = await _source(engine, source.id)
    assert stored is not None and stored.status is KnowledgeSourceStatus.removing


# ---------- removal ----------


async def test_removal_drops_the_source_and_pages_left_without_sources(
    engine: AsyncEngine,
) -> None:
    kb_id = await _seed_kb(engine)
    gone = await _seed_source(engine, kb_id, file_name="a.txt")
    kept = await _seed_source(engine, kb_id, file_name="b.txt")
    await _seed_page(engine, kb_id, "/only-a.md", [gone.citation_key])
    await _seed_page(engine, kb_id, "/both.md", [gone.citation_key, kept.citation_key])
    await _seed_page(engine, kb_id, "/only-b.md", [kept.citation_key])
    # The agent ignores the request entirely: the code-side cleanup still runs.
    llm = _ScriptedLlm()

    await _run(engine, gone.id, KnowledgeJobAction.remove, llm)

    pages = await _pages(engine, kb_id)
    assert sorted(pages) == ["/both.md", "/only-b.md"]
    assert pages["/both.md"].source_ids == [kept.citation_key]
    assert await _source(engine, gone.id) is None
    assert "/only-a.md" in llm.prompts[0] and "/both.md" in llm.prompts[0]
    assert "/only-b.md" not in llm.prompts[0]


async def test_removal_of_an_uncited_source_skips_the_model(
    engine: AsyncEngine,
) -> None:
    kb_id = await _seed_kb(engine)
    source = await _seed_source(engine, kb_id)
    llm = _ScriptedLlm()

    await _run(engine, source.id, KnowledgeJobAction.remove, llm)

    assert llm.calls == 0
    assert await _source(engine, source.id) is None


async def test_reingest_removes_then_reads_again(engine: AsyncEngine) -> None:
    kb_id = await _seed_kb(engine)
    source = await _seed_source(engine, kb_id, text="VPN now uses port 8443.")
    key = source.citation_key
    await _seed_page(engine, kb_id, "/procedures/vpn.md", [key], body="Port 443.")
    llm = _ScriptedLlm(
        script=[
            # Removal pass: the agent tries to keep citing the source -- refused.
            [_write("/procedures/vpn.md", key)],
            [("delete_page", {"path": "/procedures/vpn.md"})],
            [],
            # Ingest pass: the source may be cited again.
            [_write("/procedures/vpn.md", key, body="Port 8443.")],
        ]
    )

    await _run(engine, source.id, KnowledgeJobAction.reingest, llm)

    pages = await _pages(engine, kb_id)
    assert pages["/procedures/vpn.md"].body.startswith("Port 8443.")
    assert len(llm.prompts) == 2
    assert "being removed" in llm.prompts[0]
    assert "port 8443" in llm.prompts[1]


# ---------- the editor's tool validation ----------


def _editor() -> WikiEditor:
    page = PageDraft(
        path="/a.md",
        type="Concept",
        title="A",
        description="",
        body="x",
        meta={"sources": [{"id": "src-1"}]},
    )
    return WikiEditor(
        [page],
        {"src-1": SourceRef("a.txt", "A"), "src-2": SourceRef("b.txt", "B")},
        actor="a2flow/test",
    )


def test_write_page_rejects_unknown_sources_and_bad_paths() -> None:
    editor = _editor()
    result = editor.write_page("/Bad Path.md", "Concept", "T", "", "body", ["src-1"])
    assert "not a valid page path" in result["error"]
    result = editor.write_page("/b.md", "Concept", "T", "", "body", ["src-9"])
    assert "unknown source ids: src-9" in result["error"]
    result = editor.write_page("/b.md", "Concept", "T", "", "body", [])
    assert "at least one source" in result["error"]
    assert editor.changes() == ([], [])


def test_write_page_refuses_the_source_being_removed() -> None:
    editor = _editor()
    editor.forbidden_key = "src-1"
    result = editor.write_page("/a.md", "Concept", "A", "", "x", ["src-1"])
    assert "being removed" in result["error"]


def test_changes_report_writes_and_deletes() -> None:
    editor = _editor()
    assert editor.write_page("b", "Concept", "B", "", "y", ["src-2"]) == {
        "written": "/b.md"
    }
    assert editor.delete_page("/a.md") == {"deleted": "/a.md"}
    written, deleted = editor.changes()
    assert [p.path for p in written] == ["/b.md"]
    assert written[0].meta["sources"] == [
        {"id": "src-2", "resource": "b.txt", "title": "B"}
    ]
    assert deleted == ["/a.md"]
