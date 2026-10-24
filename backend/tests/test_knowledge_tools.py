"""Tests for the knowledge base agent tools in ``infrastructure.knowledge_tools``.

Same shape as ``tests/test_session_file_tools.py``: the tools open their own
session on ``infrastructure.database.engine``, so each test points it at a
throwaway database and calls the tools with a fake ToolContext. What matters
here is that a session -- design or run -- sees exactly the knowledge bases
its workflow is linked to.
"""

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.knowledge_tools import (
    list_knowledge_bases,
    read_knowledge_index,
    read_knowledge_page,
    search_knowledge,
)
from infrastructure.workflow_task_tools import ACTING_USER_STATE_KEY
from models.agent_skill import AgentSkill
from models.knowledge import KnowledgeBase, WorkflowKnowledgeBase
from models.tag import KnowledgeBaseTag, Tag, UserGroupTag
from models.user_group import UserGroup, UserGroupMember
from models.workflow import Workflow
from models.workflow_execution import WorkflowExecution
from repositories.knowledge import SqlKnowledgePageRepository
from tests._engine import make_test_engine
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users

_USER = "owner"


@pytest_asyncio.fixture()
async def engine(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[AsyncEngine, None]:
    """Yield a throwaway engine and point the tools' module-level engine at it."""
    eng = await make_test_engine()
    await seed_users(eng)
    await seed_tenant(eng)
    monkeypatch.setattr("infrastructure.database.engine", eng)
    yield eng
    await eng.dispose()


def _audit() -> dict[str, Any]:
    return {
        "tenant_id": DEFAULT_TEST_TENANT_ID,
        "created_by": _USER,
        "updated_by": _USER,
    }


@pytest_asyncio.fixture()
async def kbs(engine: AsyncEngine) -> dict[str, str]:
    """Seed a workflow with a design session and a run, linked to one of two KBs.

    Returns:
        ``{"linked": <kb id>, "other": <kb id>}``.
    """
    async with AsyncSession(engine, expire_on_commit=False) as db:
        skill = AgentSkill(name="skill", repo_url="https://example.com/r", **_audit())
        linked = KnowledgeBase(name="IT", description="IT know-how", **_audit())
        other = KnowledgeBase(name="HR", **_audit())
        db.add_all([skill, linked, other])
        await db.flush()
        workflow = Workflow(
            name="wf",
            agent_skill_id=skill.id,
            session_id="design-1",
            agent_skill_commit_sha="abc",
            **_audit(),
        )
        db.add(workflow)
        await db.flush()
        db.add(
            WorkflowExecution(
                session_id="run-1",
                workflow_id=workflow.id,
                name="wf",
                agent_skill_id=skill.id,
                agent_skill_name="skill",
                agent_skill_repo_url="https://example.com/r",
                agent_skill_repo_path=".",
                initiator_id=_USER,
                **_audit(),
            )
        )
        db.add(
            WorkflowKnowledgeBase(workflow_id=workflow.id, knowledge_base_id=linked.id)
        )
        pages = SqlKnowledgePageRepository(db, tenant_id=DEFAULT_TEST_TENANT_ID)
        for kb, path, title, body in (
            (
                linked,
                "/procedures/vpn-setup.md",
                "VPN setup",
                "Connect with the VPN client on port 443.",
            ),
            (
                linked,
                "/topics/printers.md",
                "Printers",
                "The VPN is not needed for printing.",
            ),
            (
                other,
                "/policies/leave.md",
                "Leave",
                "VPN access during leave is revoked.",
            ),
        ):
            await pages.upsert(
                kb.id,
                path,
                type_="Concept",
                title=title,
                description="",
                body=body,
                meta={},
                user_id=_USER,
            )
        await db.commit()
        return {"linked": linked.id, "other": other.id}


def _ctx(session_id: str) -> Any:
    return SimpleNamespace(session=SimpleNamespace(id=session_id), state={})


@pytest.mark.parametrize("session_id", ["design-1", "run-1"])
async def test_lists_only_the_linked_knowledge_bases(
    kbs: dict[str, str], session_id: str
) -> None:
    result = await list_knowledge_bases(_ctx(session_id))
    assert result == {
        "knowledgeBases": [
            {"id": kbs["linked"], "name": "IT", "description": "IT know-how"}
        ]
    }


async def test_unknown_session_gets_an_error(kbs: dict[str, str]) -> None:
    assert "error" in await list_knowledge_bases(_ctx("nobody"))


async def test_unlinked_knowledge_base_is_refused(kbs: dict[str, str]) -> None:
    result = await read_knowledge_index(kbs["other"], _ctx("run-1"))
    assert "not linked" in result["error"]
    result = await read_knowledge_page(
        kbs["other"], "/policies/leave.md", _ctx("run-1")
    )
    assert "not linked" in result["error"]


async def test_index_and_page(kbs: dict[str, str]) -> None:
    index = await read_knowledge_index(kbs["linked"], _ctx("run-1"))
    assert "# IT" in index["content"]
    assert "* [Procedures](/procedures/index.md) - 1 page" in index["content"]
    sub = await read_knowledge_index(
        kbs["linked"], _ctx("run-1"), directory="procedures"
    )
    assert "* [VPN setup](/procedures/vpn-setup.md)" in sub["content"]

    page = await read_knowledge_page(
        kbs["linked"], "procedures/vpn-setup.md", _ctx("run-1")
    )
    assert page["title"] == "VPN setup"
    assert page["content"].endswith("Connect with the VPN client on port 443.\n")
    missing = await read_knowledge_page(kbs["linked"], "/nope.md", _ctx("run-1"))
    assert "no page" in missing["error"]


async def test_search_ranks_title_matches_first_and_stays_in_linked_bases(
    kbs: dict[str, str],
) -> None:
    result = await search_knowledge("vpn", _ctx("design-1"))
    paths = [r["path"] for r in result["results"]]
    assert paths == ["/procedures/vpn-setup.md", "/topics/printers.md"]
    assert "VPN" in result["results"][0]["snippet"]

    narrowed = await search_knowledge(
        "printing", _ctx("run-1"), knowledge_base_id=kbs["linked"]
    )
    assert [r["path"] for r in narrowed["results"]] == ["/topics/printers.md"]

    assert "error" in await search_knowledge(" ", _ctx("run-1"))
    assert (
        "not linked"
        in (
            await search_knowledge("vpn", _ctx("run-1"), knowledge_base_id=kbs["other"])
        )["error"]
    )


async def test_search_ranks_before_the_limit_cuts(engine: AsyncEngine) -> None:
    """A strong match written after weaker ones still survives a small limit."""
    async with AsyncSession(engine, expire_on_commit=False) as db:
        kb = KnowledgeBase(name="Big", **_audit())
        db.add(kb)
        await db.flush()
        pages = SqlKnowledgePageRepository(db, tenant_id=DEFAULT_TEST_TENANT_ID)
        for path, title in (("/a.md", "Alpha"), ("/b.md", "Beta"), ("/z.md", "VPN")):
            await pages.upsert(
                kb.id,
                path,
                type_="Concept",
                title=title,
                description="",
                body="Mentions the VPN.",
                meta={},
                user_id=_USER,
            )
        await db.commit()
        found = await pages.search([kb.id], ["vpn"], limit=1)
    assert [p.path for p in found] == ["/z.md"]


async def test_access_control_tag_hides_a_linked_knowledge_base(
    engine: AsyncEngine, kbs: dict[str, str]
) -> None:
    """A run follows its initiator's groups; a design session, the acting user's."""
    async with AsyncSession(engine, expire_on_commit=False) as db:
        tag = Tag(name="it-only", access_control=True, **_audit())
        db.add(tag)
        db.add(UserGroup(id="group-1", name="IT", roles=[], **_audit()))
        db.add(UserGroupMember(group_id="group-1", user_id="alice"))
        await db.commit()
        db.add(KnowledgeBaseTag(resource_id=kbs["linked"], tag_id=tag.id))
        await db.commit()

    # The initiator ("owner") holds no group with the tag: hidden as if unlinked.
    assert await list_knowledge_bases(_ctx("run-1")) == {"knowledgeBases": []}
    assert (
        "not linked"
        in (await read_knowledge_index(kbs["linked"], _ctx("run-1")))["error"]
    )
    assert (await search_knowledge("vpn", _ctx("run-1")))["results"] == []

    def design_as(user: str) -> Any:
        ctx = _ctx("design-1")
        ctx.state[ACTING_USER_STATE_KEY] = user
        return ctx

    assert await list_knowledge_bases(design_as("owner")) == {"knowledgeBases": []}

    async with AsyncSession(engine) as db:
        db.add(UserGroupTag(resource_id="group-1", tag_id=tag.id))
        await db.commit()

    found = await list_knowledge_bases(design_as("alice"))
    assert [kb["id"] for kb in found["knowledgeBases"]] == [kbs["linked"]]
    assert await list_knowledge_bases(_ctx("run-1")) == {"knowledgeBases": []}
