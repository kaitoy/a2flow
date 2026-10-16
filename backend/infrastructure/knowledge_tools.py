"""ADK agent tools reading the knowledge bases linked to the current workflow.

Attached to the design and execution agents (see
:func:`infrastructure.agent.create_agent`), so a run -- and the chat in which
the workflow is designed -- can look things up in the LLM-maintained wikis of
:mod:`models.knowledge` instead of relying on what the model happens to know.
Retrieval is navigational, the way an OKF bundle is meant to be read: start at
a knowledge base's ``index.md`` (``read_knowledge_index``), drill into pages
(``read_knowledge_page``), or jump to candidates with ``search_knowledge``.

The facts that shape the other ``*_tools`` modules shape this one too: the
tools run outside FastAPI's dependency injection, so each call opens its own
``AsyncSession`` on the module-level engine; and one cached agent serves every
session of a skill, so the workflow is resolved at call time from the ADK
session id -- a workflow session through its execution, a design session
directly. A tool only ever sees the knowledge bases linked to that workflow.

Unlike most agent tools, these honour access-control tags: a knowledge base
the acting user's groups could not open in the admin UI is hidden from the
agent too, exactly as if it were not linked. The acting user is the one
chatting in a design session, and the run's initiator in a run -- fixed for the
whole run, so a server-driven turn (an approval resuming it, a scheduled wait)
sees the same knowledge bases as the turns the initiator drove.
"""

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from google.adk.tools.tool_context import ToolContext
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure import database
from infrastructure.okf import render_index, render_page
from infrastructure.workflow_task_tools import _user_id
from models.knowledge import KnowledgeBase
from repositories.effective_roles import SqlEffectiveRoleRepository
from repositories.knowledge import (
    SqlKnowledgeBaseRepository,
    SqlKnowledgePageRepository,
)
from repositories.tenant_bootstrap import (
    resolve_workflow_design_tenant,
    resolve_workflow_execution_tenant,
)
from repositories.workflow_execution import SqlWorkflowExecutionRepository

_NO_WORKFLOW = "no workflow is bound to the current session; no knowledge is available"

#: Search returns at most this many pages, best first.
_MAX_RESULTS = 10

#: Words of a query beyond this many are ignored.
_MAX_TERMS = 8

#: Characters of context on each side of the first match in a snippet.
_SNIPPET_RADIUS = 120


@asynccontextmanager
async def _knowledge(
    tool_context: ToolContext,
) -> AsyncIterator[tuple[list[KnowledgeBase], SqlKnowledgePageRepository] | None]:
    """Yield the current workflow's knowledge bases and a page repository.

    Yields ``None`` when the ADK session maps to no workflow (a run whose
    workflow was deleted, or a chat outside any workflow). The knowledge bases
    are filtered by the acting user's access-control tags -- the run's
    initiator, or the user chatting in a design session; see the module
    docstring.

    Args:
        tool_context: The ADK tool context for the current invocation.
    """
    async with AsyncSession(database.engine) as db:
        session = getattr(tool_context, "session", None)
        session_id = getattr(session, "id", None)
        workflow_id = tenant_id = user_id = None
        if session_id:
            execution = await resolve_workflow_execution_tenant(db, session_id)
            if execution is not None:
                execution_id, tenant_id = execution
                run = await SqlWorkflowExecutionRepository(db, tenant_id=tenant_id).get(
                    execution_id
                )
                if run is not None:
                    workflow_id, user_id = run.workflow_id, run.initiator_id
            else:
                design = await resolve_workflow_design_tenant(db, session_id)
                if design is not None:
                    workflow_id, tenant_id = design
                    user_id = _user_id(tool_context)
        if workflow_id is None or tenant_id is None:
            yield None
            return
        access_tag_ids = await SqlEffectiveRoleRepository(db).access_tag_ids_for_user(
            user_id
        )
        kbs = await SqlKnowledgeBaseRepository(
            db, tenant_id=tenant_id, access_tag_ids=access_tag_ids
        ).linked_to_workflow(workflow_id)
        yield kbs, SqlKnowledgePageRepository(db, tenant_id=tenant_id)


def _find(kbs: list[KnowledgeBase], kb_id: str) -> KnowledgeBase | None:
    """Return the linked knowledge base with the given id, or ``None``."""
    return next((kb for kb in kbs if kb.id == kb_id), None)


def _not_linked(kb_id: str) -> dict[str, Any]:
    """Build the error for a knowledge base id the workflow is not linked to."""
    return {
        "error": f"knowledge base {kb_id!r} is not linked to this workflow; "
        "call list_knowledge_bases for the ids"
    }


async def list_knowledge_bases(tool_context: ToolContext) -> dict[str, Any]:
    """List the knowledge bases linked to this workflow.

    Each one is a wiki of pages written from documents and web pages people
    registered. Consult them before relying on general knowledge for anything
    specific to this organization: its systems, procedures, policies, terms.

    Args:
        tool_context: Injected by ADK; identifies the current session. Not
            shown to the model.

    Returns:
        ``{"knowledgeBases": [{"id", "name", "description"}, ...]}`` -- empty
        when none is linked -- or ``{"error": <message>}``.
    """
    async with _knowledge(tool_context) as found:
        if found is None:
            return {"error": _NO_WORKFLOW}
        kbs, _pages = found
        return {
            "knowledgeBases": [
                {"id": kb.id, "name": kb.name, "description": kb.description or ""}
                for kb in kbs
            ]
        }


async def read_knowledge_index(
    knowledge_base_id: str, tool_context: ToolContext, directory: str = "/"
) -> dict[str, Any]:
    """Read the table of contents of a knowledge base, or of one of its directories.

    Start here to see what a knowledge base covers: the index lists each page
    with a one-line description, and each subdirectory with a link to its own
    index.

    Args:
        knowledge_base_id: Id from ``list_knowledge_bases``.
        tool_context: Injected by ADK. Not shown to the model.
        directory: Directory to list, e.g. ``/procedures/``; the root by default.

    Returns:
        ``{"content": <index.md>}``, or ``{"error": <message>}``.
    """
    async with _knowledge(tool_context) as found:
        if found is None:
            return {"error": _NO_WORKFLOW}
        kbs, pages = found
        kb = _find(kbs, knowledge_base_id)
        if kb is None:
            return _not_linked(knowledge_base_id)
        return {
            "content": render_index(
                await pages.list_for(kb.id),
                directory,
                title=kb.name,
                description=kb.description,
            )
        }


async def read_knowledge_page(
    knowledge_base_id: str, path: str, tool_context: ToolContext
) -> dict[str, Any]:
    """Read one page of a knowledge base in full.

    The page's frontmatter lists the documents it was written from
    (``sources``); its footnotes say which source supports which statement.
    Mention the page when you rely on it in an answer.

    Args:
        knowledge_base_id: Id from ``list_knowledge_bases``.
        path: The page path as linked from an index or search result, e.g.
            ``/procedures/vpn-setup.md``.
        tool_context: Injected by ADK. Not shown to the model.

    Returns:
        ``{"path", "title", "content"}`` with the page as Markdown, or
        ``{"error": <message>}``.
    """
    async with _knowledge(tool_context) as found:
        if found is None:
            return {"error": _NO_WORKFLOW}
        kbs, pages = found
        kb = _find(kbs, knowledge_base_id)
        if kb is None:
            return _not_linked(knowledge_base_id)
        page = await pages.get(kb.id, path if path.startswith("/") else f"/{path}")
        if page is None:
            return {
                "error": f"no page at {path!r}; use read_knowledge_index or "
                "search_knowledge to find one"
            }
        return {"path": page.path, "title": page.title, "content": render_page(page)}


def _terms(query: str) -> list[str]:
    """Split a query into distinct lowercase words of two characters or more."""
    words = [w.lower() for w in re.split(r"\s+", query) if len(w.strip()) >= 2]
    return list(dict.fromkeys(words))[:_MAX_TERMS]


def _snippet(body: str, terms: list[str]) -> str:
    """Return the stretch of ``body`` around the first matching term."""
    lowered = body.lower()
    hits = [i for i in (lowered.find(t) for t in terms) if i >= 0]
    if not hits:
        return body[: 2 * _SNIPPET_RADIUS].strip()
    start = max(min(hits) - _SNIPPET_RADIUS, 0)
    text = body[start : start + 2 * _SNIPPET_RADIUS].strip()
    return ("..." if start else "") + text + "..."


async def search_knowledge(
    query: str, tool_context: ToolContext, knowledge_base_id: str | None = None
) -> dict[str, Any]:
    """Find knowledge base pages mentioning the given words.

    Matches words literally (case-insensitive), so search with the terms a
    page would use -- names of systems, products, procedures -- and try
    synonyms when nothing comes back. Read a result in full with
    ``read_knowledge_page`` before relying on it.

    Args:
        query: Space-separated keywords.
        tool_context: Injected by ADK. Not shown to the model.
        knowledge_base_id: Restrict the search to one knowledge base; every
            linked one by default.

    Returns:
        ``{"results": [{"knowledgeBaseId", "path", "title", "description",
        "snippet"}, ...]}`` best match first, or ``{"error": <message>}``.
    """
    terms = _terms(query)
    if not terms:
        return {"error": "the query has no words to search for"}
    async with _knowledge(tool_context) as found:
        if found is None:
            return {"error": _NO_WORKFLOW}
        kbs, pages = found
        if knowledge_base_id is not None:
            kb = _find(kbs, knowledge_base_id)
            if kb is None:
                return _not_linked(knowledge_base_id)
            kbs = [kb]
        ranked = await pages.search([kb.id for kb in kbs], terms, limit=_MAX_RESULTS)
        return {
            "results": [
                {
                    "knowledgeBaseId": p.knowledge_base_id,
                    "path": p.path,
                    "title": p.title,
                    "description": p.description,
                    "snippet": _snippet(p.body, terms),
                }
                for p in ranked
            ]
        }
