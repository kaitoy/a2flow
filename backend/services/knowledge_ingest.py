"""The background job that folds a knowledge source into its wiki, or takes it out.

Registering, re-ingesting, or removing a source only records the request; the
router then hands :func:`run_knowledge_job` to ``BackgroundTasks``. The job
reads the source as Markdown (:mod:`infrastructure.knowledge_extract`), and an
LLM agent edits the knowledge base's pages through four tools --
``list_pages``, ``read_page``, ``write_page``, ``delete_page`` -- merging the
source into the existing topic pages rather than filing a summary per source.

**Working copy.** The agent never touches the database. :class:`WikiEditor`
loads every page of the knowledge base into memory first, the tools edit that
copy, and only once the agent is done are the changes written back -- in one
transaction, together with the source's new status. A job therefore lands
whole or not at all, and no write lock is held while the model thinks (which
on SQLite would stall every other writer for minutes).

**Serialization.** Two jobs on one knowledge base would edit the same pages,
so they take the knowledge base's advisory lock
(:func:`infrastructure.locks.knowledge_base_key`) and run one after another;
jobs on different knowledge bases run side by side. A source waiting for the
lock stays ``pending``.

**Removal.** A page records the sources it draws on (frontmatter ``sources``,
cited in the body with keyed footnotes). Removing a source shows the agent
only the pages citing it and asks it to take that source's claims out; any
page that still lists the source afterwards has the entry dropped by code,
and a page left without sources is deleted. A re-ingest is that removal
followed by a fresh ingest, in the same job.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import InMemoryRunner
from google.genai import types
from sqlmodel.ext.asyncio.session import AsyncSession

from config import Settings, get_settings
from infrastructure import database
from infrastructure.agent import ToolUnion, resolve_model
from infrastructure.knowledge_extract import (
    ExtractedDocument,
    FetchedDocument,
    extract_markdown,
    fetch_url,
    split_chunks,
)
from infrastructure.locks import advisory_lock, knowledge_base_key
from infrastructure.okf import normalize_page_path
from models.knowledge import (
    KnowledgePage,
    KnowledgeSource,
    KnowledgeSourceKind,
    KnowledgeSourceStatus,
)
from repositories.knowledge import (
    SqlKnowledgePageRepository,
    SqlKnowledgeSourceRepository,
)
from repositories.tenant_bootstrap import resolve_knowledge_source_tenant

logger = logging.getLogger(__name__)

#: How long a job waits for the other jobs of its knowledge base to finish.
_LOCK_WAIT_SECONDS = 30 * 60.0

#: ADK app and user names of the throwaway in-memory runner sessions.
_APP_NAME = "a2flow-knowledge"
_RUNNER_USER = "knowledge-ingest"

#: Limits the tools enforce on what the agent writes into one page.
_MAX_TITLE_CHARS = 200
_MAX_DESCRIPTION_CHARS = 500
_MAX_BODY_CHARS = 60_000
_MAX_TAGS = 10

#: Longest failure reason recorded on a source row.
_MAX_ERROR_CHARS = 1000

_INSTRUCTION = """\
You maintain a knowledge wiki that other AI agents read to do their work and \
answer questions. The wiki is a set of Markdown pages in Open Knowledge \
Format: each page is one concept -- a topic, an entity, a procedure, a \
policy, a glossary of terms -- with a short type, a title, a one-sentence \
description, and a Markdown body.

You edit the wiki only through your tools. Always start with `list_pages`, \
then `read_page` every page that is related to what you are about to write.

Rules:
- Merge, do not duplicate. When a page about a concept already exists, \
rewrite it with `write_page` so it covers the new information, keeping what \
it already says that remains true. Create a new page only for a concept no \
page covers yet. Prefer several focused pages over one long page.
- Paths are lowercase kebab-case and end in `.md`, grouped in a few \
top-level directories, for example `/topics/`, `/entities/`, `/procedures/`, \
`/glossary/`. Never write `index.md` or `log.md`; they are generated.
- Link related pages with absolute Markdown links such as \
`[VPN setup](/procedures/vpn-setup.md)`.
- Cite every fact with a footnote whose label is the key of the source it \
came from, for example `...uses port 443.[^src-1a2b3c4d]`, and define each \
footnote at the end of the body as `[^src-1a2b3c4d]: <source title>`. When \
you rewrite a page, keep the claims and footnotes of other sources intact. \
`source_ids` must list every source key the page cites.
- Write pages in the language of the source material.
- Record knowledge, not commentary about the document: no "this document \
says", no summaries of what was in which file.

When you are finished, reply with one short line saying what you changed.\
"""


class KnowledgeJobAction(StrEnum):
    """What a knowledge job does with its source."""

    ingest = "ingest"
    """Read a newly registered source into the wiki."""

    reingest = "reingest"
    """Take the source's previous contribution out, then read it again."""

    remove = "remove"
    """Take the source's contribution out, then delete the source."""


class KnowledgeIngestError(Exception):
    """Raised for an ingest failure the source row should record verbatim."""


@dataclass(frozen=True)
class PageDraft:
    """One page of the editor's working copy."""

    path: str
    type: str
    title: str
    description: str
    body: str
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def source_ids(self) -> list[str]:
        """Return the citation keys listed in the page's ``sources``."""
        return [str(s.get("id")) for s in self.meta.get("sources", [])]

    @classmethod
    def from_page(cls, page: KnowledgePage) -> "PageDraft":
        """Copy a stored page into the working copy."""
        return cls(
            path=page.path,
            type=page.type,
            title=page.title,
            description=page.description,
            body=page.body,
            meta=dict(page.meta),
        )


@dataclass(frozen=True)
class SourceRef:
    """What a page's ``sources`` entry says about one source."""

    resource: str
    title: str


class WikiEditor:
    """In-memory working copy of a knowledge base's pages, edited by the agent's tools.

    The four public tool methods return JSON-serializable dicts and report a
    rejected edit as ``{"error": ...}`` so the model can correct itself rather
    than the job failing.
    """

    def __init__(
        self,
        pages: list[PageDraft],
        sources: dict[str, SourceRef],
        *,
        actor: str,
    ) -> None:
        """Start a working copy.

        Args:
            pages: The knowledge base's pages as currently stored.
            sources: Every source of the knowledge base a page may cite, keyed
                by citation key.
            actor: The OKF ``generated.by`` actor stamped on written pages.
        """
        self._original = {p.path: p for p in pages}
        self.pages: dict[str, PageDraft] = dict(self._original)
        self._sources = sources
        self._actor = actor
        #: A citation key pages may no longer cite: the source being removed.
        self.forbidden_key: str | None = None

    def tools(self) -> list[ToolUnion]:
        """Return the tool functions to hand the agent."""
        return [self.list_pages, self.read_page, self.write_page, self.delete_page]

    def list_pages(self) -> dict[str, Any]:
        """List every page of the wiki.

        Returns:
            ``{"pages": [{"path", "type", "title", "description", "sourceIds"}]}``.
        """
        return {
            "pages": [
                {
                    "path": p.path,
                    "type": p.type,
                    "title": p.title,
                    "description": p.description,
                    "sourceIds": p.source_ids,
                }
                for p in sorted(self.pages.values(), key=lambda p: p.path)
            ]
        }

    def read_page(self, path: str) -> dict[str, Any]:
        """Read one page in full.

        Args:
            path: The page path, e.g. ``/topics/vpn-setup.md``.

        Returns:
            The page's ``path``, ``type``, ``title``, ``description``, ``tags``,
            ``sourceIds``, and Markdown ``body``; or ``{"error": ...}``.
        """
        page = self.pages.get(path)
        if page is None:
            return {"error": f"no page at {path!r}; call list_pages for the paths"}
        return {
            "path": page.path,
            "type": page.type,
            "title": page.title,
            "description": page.description,
            "tags": page.meta.get("tags", []),
            "sourceIds": page.source_ids,
            "body": page.body,
        }

    def write_page(
        self,
        path: str,
        page_type: str,
        title: str,
        description: str,
        body: str,
        source_ids: list[str],
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a page, or replace the whole content of an existing one.

        Args:
            path: Lowercase kebab-case path ending in ``.md``, at most three
                directories deep, e.g. ``/procedures/vpn-setup.md``.
            page_type: Short category, e.g. ``Concept``, ``Entity``,
                ``Procedure``, ``Policy``, ``Glossary``.
            title: The page title.
            description: One sentence saying what the page covers.
            body: The complete Markdown body, footnote definitions included.
            source_ids: Keys of every source the body cites, e.g.
                ``["src-1a2b3c4d"]``.
            tags: Optional short keywords.

        Returns:
            ``{"written": <path>}``, or ``{"error": ...}`` explaining what to fix.
        """
        try:
            path = normalize_page_path(path)
        except ValueError as exc:
            return {"error": str(exc)}
        problems = []
        if not page_type.strip():
            problems.append("page_type must not be empty")
        if not title.strip() or len(title) > _MAX_TITLE_CHARS:
            problems.append(f"title must be 1-{_MAX_TITLE_CHARS} characters")
        if len(description) > _MAX_DESCRIPTION_CHARS:
            problems.append(
                f"description must be at most {_MAX_DESCRIPTION_CHARS} characters"
            )
        if not body.strip() or len(body) > _MAX_BODY_CHARS:
            problems.append(
                f"body must be 1-{_MAX_BODY_CHARS} characters; split a longer "
                "page into several linked pages"
            )
        keys = list(dict.fromkeys(source_ids))
        if not keys:
            problems.append("source_ids must name at least one source")
        unknown = [k for k in keys if k not in self._sources]
        if unknown:
            problems.append(f"unknown source ids: {', '.join(unknown)}")
        if self.forbidden_key is not None and self.forbidden_key in keys:
            problems.append(
                f"{self.forbidden_key} is being removed and may not be cited"
            )
        if problems:
            return {"error": "; ".join(problems)}

        meta: dict[str, Any] = {
            "generated": {
                "by": self._actor,
                "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "sources": [
                {
                    "id": k,
                    "resource": self._sources[k].resource,
                    "title": self._sources[k].title,
                }
                for k in keys
            ],
        }
        clean_tags = [t.strip() for t in tags or [] if t.strip()][:_MAX_TAGS]
        if clean_tags:
            meta["tags"] = clean_tags
        self.pages[path] = PageDraft(
            path=path,
            type=page_type.strip(),
            title=title.strip(),
            description=description.strip(),
            body=body.strip(),
            meta=meta,
        )
        return {"written": path}

    def delete_page(self, path: str) -> dict[str, Any]:
        """Delete a page that no longer has anything to say.

        Args:
            path: The page path.

        Returns:
            ``{"deleted": <path>}``, or ``{"error": ...}``.
        """
        if self.pages.pop(path, None) is None:
            return {"error": f"no page at {path!r}"}
        return {"deleted": path}

    def paths_citing(self, key: str) -> list[str]:
        """Return the paths of the pages that list ``key`` among their sources."""
        return sorted(p.path for p in self.pages.values() if key in p.source_ids)

    def drop_source(self, key: str) -> None:
        """Remove ``key`` from every page's sources, deleting pages left with none."""
        for path in self.paths_citing(key):
            page = self.pages[path]
            remaining = [s for s in page.meta.get("sources", []) if s.get("id") != key]
            if not remaining:
                del self.pages[path]
            else:
                self.pages[path] = PageDraft(
                    path=page.path,
                    type=page.type,
                    title=page.title,
                    description=page.description,
                    body=page.body,
                    meta={**page.meta, "sources": remaining},
                )

    def changes(self) -> tuple[list[PageDraft], list[str]]:
        """Return the pages written and the paths deleted since the copy was loaded."""
        written = [
            p for path, p in self.pages.items() if self._original.get(path) is not p
        ]
        deleted = [path for path in self._original if path not in self.pages]
        return written, deleted


def _ingest_message(
    key: str, label: str, resource: str, part: int, parts: int, text: str
) -> str:
    """Build the user turn that hands the agent one part of a source."""
    of = f" (part {part} of {parts})" if parts > 1 else ""
    return (
        f"Fold the following source into the wiki{of}.\n\n"
        f"Source key: {key}\nSource title: {label}\nSource: {resource}\n\n"
        f"---\n{text}\n---"
    )


def _removal_message(key: str, paths: list[str]) -> str:
    """Build the user turn asking the agent to take a source out of the wiki."""
    listed = "\n".join(f"- {p}" for p in paths)
    return (
        f"The source {key} is being removed from the wiki. These pages cite it:\n"
        f"{listed}\n\n"
        "Read each one. Remove the claims that only that source supports and its "
        "footnotes, and drop it from source_ids. Rewrite the page with the "
        "remaining material, or call delete_page when nothing other sources "
        "support is left."
    )


def _reason(exc: BaseException) -> str:
    """Render an exception as the short reason recorded on the source."""
    text = str(exc) or type(exc).__name__
    return text[:_MAX_ERROR_CHARS]


Fetcher = Callable[..., Awaitable[FetchedDocument]]


class KnowledgeIngestService:
    """Runs one knowledge job against one tenant's database session."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        tenant_id: str,
        settings: Settings | None = None,
        llm: BaseLlm | str | None = None,
        fetch: Fetcher = fetch_url,
    ) -> None:
        """Initialize the service.

        Args:
            db: Database session owned by the job.
            tenant_id: Tenant of the source being processed.
            settings: Application settings; read from the environment by default.
            llm: Model the agent runs on; the configured model by default.
            fetch: Downloader for URL sources, replaceable in tests.
        """
        self._db = db
        self._settings = settings or get_settings()
        self._llm = llm if llm is not None else resolve_model()
        self._fetch = fetch
        self._sources = SqlKnowledgeSourceRepository(db, tenant_id=tenant_id)
        self._pages = SqlKnowledgePageRepository(db, tenant_id=tenant_id)
        model = self._settings.llm_model.removeprefix("litellm:")
        self._actor = f"a2flow/{model}"

    async def run(
        self, source_id: str, action: KnowledgeJobAction, *, user_id: str
    ) -> None:
        """Process one source, recording the outcome on its row.

        Never raises for a failure of the job itself: the reason is what the
        admin UI is waiting for, so it lands on the row as ``failed``.

        Args:
            source_id: Id of the source to process.
            action: What to do with it.
            user_id: Id of the user whose request started the job.
        """
        source = await self._sources.get(source_id)
        if source is None:
            return
        kb_id = source.knowledge_base_id
        try:
            async with advisory_lock(
                knowledge_base_key(kb_id), wait_seconds=_LOCK_WAIT_SECONDS
            ):
                # Re-read under the lock: a job that ran while this one waited
                # may have deleted the source or marked it for removal.
                source = await self._sources.get(source_id)
                if source is None:
                    return
                if action is KnowledgeJobAction.remove:
                    await self._remove(source, user_id=user_id)
                elif source.status is not KnowledgeSourceStatus.removing:
                    await self._ingest(
                        source,
                        user_id=user_id,
                        reingest=action is KnowledgeJobAction.reingest,
                    )
        except Exception as exc:
            logger.warning(
                "Knowledge job %s on source %s failed: %s",
                action.value,
                source_id,
                exc,
                exc_info=True,
            )
            await self._db.rollback()
            failed = await self._sources.get(source_id)
            if failed is not None:
                await self._sources.set_status(
                    failed,
                    KnowledgeSourceStatus.failed,
                    user_id=user_id,
                    error=_reason(exc),
                )

    async def _ingest(
        self, source: KnowledgeSource, *, user_id: str, reingest: bool
    ) -> None:
        """Read a source into the wiki and mark it ``ready``."""
        await self._sources.set_status(
            source, KnowledgeSourceStatus.ingesting, user_id=user_id
        )
        document = await self._read(source)
        label = document.title or source.title or source.resource
        editor = await self._editor(
            source.knowledge_base_id, current=(source.citation_key, label)
        )
        if reingest:
            await self._remove_claims(editor, source.citation_key)
        parts = split_chunks(
            document.markdown, self._settings.knowledge_ingest_chunk_chars
        )
        for number, part in enumerate(parts, start=1):
            await self._run_agent(
                editor,
                _ingest_message(
                    source.citation_key,
                    label,
                    source.resource,
                    number,
                    len(parts),
                    part,
                ),
            )
        await self._apply(source.knowledge_base_id, editor, user_id=user_id)
        await self._sources.set_status(
            source, KnowledgeSourceStatus.ready, user_id=user_id, title=document.title
        )

    async def _remove(self, source: KnowledgeSource, *, user_id: str) -> None:
        """Take a source out of the wiki and delete it."""
        await self._sources.set_status(
            source, KnowledgeSourceStatus.removing, user_id=user_id
        )
        editor = await self._editor(source.knowledge_base_id)
        await self._remove_claims(editor, source.citation_key)
        await self._apply(source.knowledge_base_id, editor, user_id=user_id)
        await self._sources.delete(source)

    async def _read(self, source: KnowledgeSource) -> ExtractedDocument:
        """Fetch or load a source and convert it to Markdown.

        Raises:
            KnowledgeIngestError: If the document yields no text.
        """
        if source.kind is KnowledgeSourceKind.url and source.url:
            fetched = await self._fetch(
                source.url,
                max_bytes=self._settings.knowledge_source_max_bytes,
                timeout=self._settings.knowledge_fetch_timeout_seconds,
            )
            document = await extract_markdown(
                fetched.data, content_type=fetched.content_type, url=fetched.url
            )
        else:
            document = await extract_markdown(
                source.data or b"",
                file_name=source.file_name,
                content_type=source.content_type,
            )
        if not document.markdown:
            raise KnowledgeIngestError(
                "No text could be extracted from the document (a scanned PDF "
                "without a text layer reads as empty)"
            )
        return document

    async def _editor(
        self, kb_id: str, *, current: tuple[str, str] | None = None
    ) -> WikiEditor:
        """Load a knowledge base's pages and sources into a fresh working copy.

        Args:
            kb_id: The knowledge base to edit.
            current: ``(citation key, title)`` of the source being ingested,
                whose title is not stored yet.

        Returns:
            The working copy.
        """
        pages = [PageDraft.from_page(p) for p in await self._pages.list_for(kb_id)]
        refs = {
            s.citation_key: SourceRef(
                resource=s.url or s.file_name or s.id,
                title=s.title or s.url or s.file_name or s.id,
            )
            for s in await self._sources.list_for(kb_id)
        }
        if current is not None:
            key, title = current
            refs[key] = SourceRef(resource=refs[key].resource, title=title)
        # End the read transaction so no connection idles in one while the
        # model works.
        await self._db.commit()
        return WikiEditor(pages, refs, actor=self._actor)

    async def _remove_claims(self, editor: WikiEditor, key: str) -> None:
        """Have the agent take a source's claims out, then drop any it left behind."""
        citing = editor.paths_citing(key)
        if citing:
            editor.forbidden_key = key
            await self._run_agent(editor, _removal_message(key, citing))
            editor.drop_source(key)
        editor.forbidden_key = None

    async def _run_agent(self, editor: WikiEditor, message: str) -> None:
        """Run the wiki agent for one user turn on a fresh in-memory session.

        Each turn gets its own session: the wiki itself carries everything a
        later part needs, and replaying earlier parts would only fill the
        context window.

        Raises:
            KnowledgeIngestError: If the model reports an error.
        """
        agent = LlmAgent(
            name="a2flow_knowledge_agent",
            model=self._llm,
            instruction=_INSTRUCTION,
            tools=editor.tools(),
        )
        runner = InMemoryRunner(agent=agent, app_name=_APP_NAME)
        session = await runner.session_service.create_session(
            app_name=_APP_NAME, user_id=_RUNNER_USER
        )
        content = types.Content(role="user", parts=[types.Part(text=message)])
        error: str | None = None
        # Drained to the end even after an error event: abandoning ADK's
        # generator midway trips its tracing context on close.
        async for event in runner.run_async(
            user_id=_RUNNER_USER, session_id=session.id, new_message=content
        ):
            if event.error_code and error is None:
                error = event.error_message or event.error_code
        if error is not None:
            raise KnowledgeIngestError(f"The model failed: {error}")

    async def _apply(self, kb_id: str, editor: WikiEditor, *, user_id: str) -> None:
        """Write the working copy's changes back. Flushes; the status write commits."""
        written, deleted = editor.changes()
        for path in deleted:
            page = await self._pages.get(kb_id, path)
            if page is not None:
                await self._pages.delete(page)
        for draft in written:
            await self._pages.upsert(
                kb_id,
                draft.path,
                type_=draft.type,
                title=draft.title,
                description=draft.description,
                body=draft.body,
                meta=draft.meta,
                user_id=user_id,
            )


async def run_knowledge_job(
    source_id: str, *, action: KnowledgeJobAction, user_id: str
) -> None:
    """Run :meth:`KnowledgeIngestService.run` on a database session of its own.

    The entry point routers hand to ``BackgroundTasks``. Swallows every error:
    nothing downstream is listening, and the service has already recorded the
    ones the admin needs to see on the source row. The engine is read through
    the ``database`` module so tests can redirect it.

    Args:
        source_id: Id of the source to process.
        action: What to do with it.
        user_id: Id of the user whose request started the job.
    """
    try:
        async with AsyncSession(database.engine, expire_on_commit=False) as db:
            tenant_id = await resolve_knowledge_source_tenant(db, source_id)
            if tenant_id is None:
                logger.warning(
                    "Knowledge job on source %s: source not found.", source_id
                )
                return
            service = KnowledgeIngestService(db, tenant_id=tenant_id)
            await service.run(source_id, action, user_id=user_id)
    except Exception:
        logger.exception("Knowledge job on source %s crashed.", source_id)
