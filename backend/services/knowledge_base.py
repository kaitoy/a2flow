"""Use case service for knowledge bases, their sources, their pages, and workflow links.

Everything under a knowledge base is reached through it: each source and page
operation first fetches the knowledge base with the caller's
access-control-tag-restricted repository, so a hidden knowledge base hides its
sources and pages too (404), the way an approval follows its execution.

Registering, re-ingesting, and removing a source only update the row; the
caller schedules :func:`services.knowledge_ingest.run_knowledge_job` with the
returned source id to do the work.
"""

from collections.abc import Awaitable, Callable, Sequence

from infrastructure.knowledge_extract import is_supported_file
from infrastructure.okf import build_bundle, render_page
from models.knowledge import (
    KnowledgeBase,
    KnowledgeBaseCreate,
    KnowledgeBaseRead,
    KnowledgeBaseUpdate,
    KnowledgePageContent,
    KnowledgePageSummary,
    KnowledgeSource,
    KnowledgeSourceKind,
    KnowledgeSourceRead,
    KnowledgeSourceStatus,
)
from repositories.exceptions import KnowledgeSourceValidationError, NotFoundError
from repositories.knowledge import (
    KnowledgeBaseRepository,
    SqlKnowledgePageRepository,
    SqlKnowledgeSourceRepository,
)
from repositories.query import FilterSpec, SortSpec
from repositories.workflow import WorkflowRepository
from services.session_file import sanitize_file_name

#: Alias for ``list[KnowledgeBaseRead]``: the ``list`` method below shadows the
#: builtin inside the service class body.
_ReadList = list[KnowledgeBaseRead]
_SourceList = list[KnowledgeSourceRead]
_PageList = list[KnowledgePageSummary]

#: Size of each read from an upload stream.
_READ_CHUNK_BYTES = 1024 * 1024


class KnowledgeBaseService:
    """Application service orchestrating knowledge base operations."""

    def __init__(
        self,
        repo: KnowledgeBaseRepository,
        sources: SqlKnowledgeSourceRepository,
        pages: SqlKnowledgePageRepository,
        workflows: WorkflowRepository,
        *,
        max_source_bytes: int,
    ) -> None:
        """Initialize the service.

        Args:
            repo: Knowledge base persistence, restricted to what the caller may see.
            sources: Source persistence, scoped to the same tenant.
            pages: Page persistence, scoped to the same tenant.
            workflows: Workflow persistence, restricted like ``repo``, used to
                check a workflow before reading or replacing its links.
            max_source_bytes: Largest document accepted for upload.
        """
        self._repo = repo
        self._sources = sources
        self._pages = pages
        self._workflows = workflows
        self._max_source_bytes = max_source_bytes

    async def get(self, kb_id: str) -> KnowledgeBase:
        """Return the KnowledgeBase with the given ID.

        Raises:
            NotFoundError: If it does not exist or is hidden from the caller.
        """
        kb = await self._repo.get(kb_id)
        if kb is None:
            raise NotFoundError("KnowledgeBase", kb_id)
        return kb

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
        tag_ids: Sequence[str] = (),
    ) -> list[KnowledgeBase]:
        """Return a page of the knowledge bases the caller may see."""
        return await self._repo.list(
            limit=limit, offset=offset, sort=sort, filters=filters, tag_ids=tag_ids
        )

    async def to_read(self, kb: KnowledgeBase) -> KnowledgeBaseRead:
        """Project one knowledge base into its API read view, attaching its tags."""
        return KnowledgeBaseRead.from_knowledge_base(
            kb, tag_ids=await self._repo.tag_ids_for(kb.id)
        )

    async def to_read_many(self, kbs: Sequence[KnowledgeBase]) -> _ReadList:
        """Project a page of knowledge bases into read views, reading tags in one query."""
        by_id = await self._repo.tag_ids_for_many([kb.id for kb in kbs])
        return [
            KnowledgeBaseRead.from_knowledge_base(kb, tag_ids=by_id.get(kb.id, []))
            for kb in kbs
        ]

    async def create(self, data: KnowledgeBaseCreate, *, user_id: str) -> KnowledgeBase:
        """Create an empty knowledge base.

        Raises:
            UniqueViolationError: If the name is already taken in this tenant.
        """
        return await self._repo.create(data, user_id=user_id)

    async def update(
        self, kb_id: str, data: KnowledgeBaseUpdate, *, user_id: str
    ) -> KnowledgeBase:
        """Rename or redescribe a knowledge base.

        Raises:
            NotFoundError: If it does not exist or is hidden from the caller.
            UniqueViolationError: If the new name is already taken.
        """
        return await self._repo.update(kb_id, data, user_id=user_id)

    async def delete(self, kb_id: str) -> None:
        """Delete a knowledge base with its sources, pages, and workflow links.

        Raises:
            NotFoundError: If it does not exist or is hidden from the caller.
        """
        await self._repo.delete(kb_id)

    async def set_tags(self, kb_id: str, tag_ids: Sequence[str]) -> KnowledgeBase:
        """Replace a knowledge base's tag attachments wholesale.

        Raises:
            NotFoundError: If it does not exist or is hidden from the caller.
            ForeignKeyViolationError: If any id does not name a tag of this tenant.
        """
        return await self._repo.set_tags(kb_id, tag_ids)

    async def list_sources(self, kb_id: str) -> _SourceList:
        """Return a knowledge base's sources, newest first."""
        await self.get(kb_id)
        return await self._sources.list_for(kb_id)

    async def add_url_source(
        self, kb_id: str, url: str, *, user_id: str
    ) -> KnowledgeSourceRead:
        """Register a web page as a source, ``pending`` its ingest.

        Args:
            kb_id: The knowledge base it feeds.
            url: The page, already SSRF-checked by the request model.
            user_id: Id of the user registering it.

        Returns:
            The new source.

        Raises:
            NotFoundError: If the knowledge base does not exist or is hidden.
        """
        await self.get(kb_id)
        source = await self._sources.add(
            kb_id, kind=KnowledgeSourceKind.url, url=url, user_id=user_id
        )
        return KnowledgeSourceRead.from_source(source)

    async def add_file_source(
        self,
        kb_id: str,
        *,
        filename: str | None,
        content_type: str | None,
        read: Callable[[int], Awaitable[bytes]],
        user_id: str,
    ) -> KnowledgeSourceRead:
        """Store an uploaded document as a source, ``pending`` its ingest.

        The stream is read in chunks and refused as soon as it passes the size
        cap, so an oversized upload is never buffered whole.

        Args:
            kb_id: The knowledge base it feeds.
            filename: The client's file name; reduced to a safe bare name.
            content_type: The declared media type.
            read: The upload's chunked reader (``UploadFile.read``).
            user_id: Id of the user uploading it.

        Returns:
            The new source.

        Raises:
            NotFoundError: If the knowledge base does not exist or is hidden.
            KnowledgeSourceValidationError: If the file is unnamed, of an
                unsupported type, empty, or too large.
        """
        await self.get(kb_id)
        name = sanitize_file_name(filename)
        if not name:
            raise KnowledgeSourceValidationError("The file has no usable name")
        if not is_supported_file(name):
            raise KnowledgeSourceValidationError(
                "Unsupported file type; upload PDF, Word (.docx), HTML, Markdown, "
                "CSV, JSON, or plain text"
            )
        buffer = bytearray()
        while chunk := await read(_READ_CHUNK_BYTES):
            buffer.extend(chunk)
            if len(buffer) > self._max_source_bytes:
                mib = self._max_source_bytes / (1024 * 1024)
                raise KnowledgeSourceValidationError(
                    f"File exceeds the {mib:g} MiB size limit"
                )
        if not buffer:
            raise KnowledgeSourceValidationError("The file is empty")
        source = await self._sources.add(
            kb_id,
            kind=KnowledgeSourceKind.file,
            file_name=name,
            content_type=content_type or "application/octet-stream",
            data=bytes(buffer),
            user_id=user_id,
        )
        return KnowledgeSourceRead.from_source(source)

    async def _source(self, kb_id: str, source_id: str) -> KnowledgeSource:
        """Return a source of a knowledge base the caller may see.

        Raises:
            NotFoundError: If either does not exist, or the source belongs to
                another knowledge base.
        """
        await self.get(kb_id)
        source = await self._sources.get(source_id)
        if source is None or source.knowledge_base_id != kb_id:
            raise NotFoundError("KnowledgeSource", source_id)
        return source

    async def request_reingest(
        self, kb_id: str, source_id: str, *, user_id: str
    ) -> KnowledgeSourceRead:
        """Mark a source ``pending`` a fresh ingest of its current content.

        Allowed in any state but ``removing``: a source stuck in ``ingesting``
        after a crash is recovered this way, and a duplicate request only
        queues a second, equivalent job behind the knowledge base's lock.

        Raises:
            NotFoundError: If the source does not exist in this knowledge base.
            KnowledgeSourceValidationError: If the source is being removed.
        """
        source = await self._source(kb_id, source_id)
        if source.status is KnowledgeSourceStatus.removing:
            raise KnowledgeSourceValidationError("The source is being removed")
        await self._sources.set_status(
            source, KnowledgeSourceStatus.pending, user_id=user_id
        )
        return KnowledgeSourceRead.from_source(source)

    async def request_removal(
        self, kb_id: str, source_id: str, *, user_id: str
    ) -> KnowledgeSourceRead:
        """Mark a source ``removing``; the job takes it out of the wiki and deletes it.

        Raises:
            NotFoundError: If the source does not exist in this knowledge base.
        """
        source = await self._source(kb_id, source_id)
        await self._sources.set_status(
            source, KnowledgeSourceStatus.removing, user_id=user_id
        )
        return KnowledgeSourceRead.from_source(source)

    async def list_pages(self, kb_id: str) -> _PageList:
        """Return a summary of every page of a knowledge base, ordered by path."""
        await self.get(kb_id)
        return [
            KnowledgePageSummary(
                path=p.path,
                type=p.type,
                title=p.title,
                description=p.description,
                updated_at=p.updated_at,
            )
            for p in await self._pages.list_for(kb_id)
        ]

    async def get_page(self, kb_id: str, path: str) -> KnowledgePageContent:
        """Return one page as its complete OKF document.

        Raises:
            NotFoundError: If the knowledge base or the page does not exist.
        """
        await self.get(kb_id)
        page = await self._pages.get(
            kb_id, path if path.startswith("/") else f"/{path}"
        )
        if page is None:
            raise NotFoundError("KnowledgePage", path)
        return KnowledgePageContent(
            path=page.path, title=page.title, content=render_page(page)
        )

    async def export(self, kb_id: str) -> tuple[KnowledgeBase, bytes]:
        """Package a knowledge base as a zipped OKF bundle.

        Returns:
            The knowledge base, for naming the download, and the zip's bytes.

        Raises:
            NotFoundError: If the knowledge base does not exist or is hidden.
        """
        kb = await self.get(kb_id)
        bundle = build_bundle(
            await self._pages.list_for(kb_id),
            title=kb.name,
            description=kb.description,
        )
        return kb, bundle

    async def _assert_workflow(self, workflow_id: str) -> None:
        """Raise ``NotFoundError`` unless the caller can see the workflow."""
        if await self._workflows.get(workflow_id) is None:
            raise NotFoundError("Workflow", workflow_id)

    async def workflow_links(self, workflow_id: str) -> _ReadList:
        """Return the knowledge bases linked to a workflow that the caller may see.

        Raises:
            NotFoundError: If the workflow does not exist or is hidden.
        """
        await self._assert_workflow(workflow_id)
        return await self.to_read_many(await self._repo.linked_to_workflow(workflow_id))

    async def set_workflow_links(
        self, workflow_id: str, kb_ids: Sequence[str]
    ) -> _ReadList:
        """Replace the knowledge bases a workflow's agents may read.

        Raises:
            NotFoundError: If the workflow does not exist or is hidden.
            ForeignKeyViolationError: If an id names no knowledge base the
                caller can see.
        """
        await self._assert_workflow(workflow_id)
        await self._repo.replace_workflow_links(workflow_id, kb_ids)
        return await self.workflow_links(workflow_id)
