"""Knowledge base repositories: the bases themselves, their sources, and their pages.

Three repositories over the tables of :mod:`models.knowledge`, all tenant-scoped.
Only :class:`SqlKnowledgeBaseRepository` carries access-control tags: sources
and pages have no tags of their own and are reached only through a knowledge
base the caller has already fetched (``services/knowledge_base.py``), the same
shape an approval has under its workflow execution.

Page writes (:meth:`SqlKnowledgePageRepository.upsert` / ``delete``) only
*flush*. An ingest job edits many pages and then records the outcome on the
source row, and that status write (:meth:`SqlKnowledgeSourceRepository.set_status`)
is the one commit -- so either every page change of a job lands, together with
``ready``, or a rollback discards them all and the source is marked ``failed``.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import ColumnElement, delete, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.knowledge import (
    KnowledgeBase,
    KnowledgeBaseCreate,
    KnowledgeBaseRead,
    KnowledgeBaseUpdate,
    KnowledgePage,
    KnowledgeSource,
    KnowledgeSourceKind,
    KnowledgeSourceRead,
    KnowledgeSourceStatus,
    WorkflowKnowledgeBase,
    citation_key_for,
)
from models.tag import KnowledgeBaseTag
from repositories._integrity import commit_or_translate_user_fk, is_foreign_key_error
from repositories._scoped import TenantScopedRepository
from repositories.exceptions import (
    ForeignKeyViolationError,
    NotFoundError,
    UniqueViolationError,
)
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort
from repositories.tags import TagLinks

#: Alias for ``list[str]``: the ``list`` method below shadows the builtin
#: inside every class body in this module.
_StrList = list[str]
_KnowledgeBaseList = list[KnowledgeBase]


async def _commit_named(db: AsyncSession, *, user_id: str, name: str) -> None:
    """Commit a knowledge base write, translating integrity failures.

    Raises:
        ForeignKeyViolationError: If the acting user does not exist.
        UniqueViolationError: If the name is already taken in this tenant.
    """
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        if is_foreign_key_error(e):
            raise ForeignKeyViolationError("User", user_id) from e
        raise UniqueViolationError("KnowledgeBase", "name", name) from e


class KnowledgeBaseRepository(Protocol):
    """Interface for KnowledgeBase persistence operations."""

    async def get(self, kb_id: str) -> KnowledgeBase | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
        tag_ids: Sequence[str] = (),
    ) -> list[KnowledgeBase]: ...

    async def create(
        self, data: KnowledgeBaseCreate, *, user_id: str
    ) -> KnowledgeBase: ...

    async def update(
        self, kb_id: str, data: KnowledgeBaseUpdate, *, user_id: str
    ) -> KnowledgeBase: ...

    async def delete(self, kb_id: str) -> None: ...

    async def exists(self, kb_id: str) -> bool: ...

    async def tag_ids_for(self, kb_id: str) -> _StrList: ...

    async def tag_ids_for_many(self, kb_ids: Sequence[str]) -> dict[str, _StrList]: ...

    async def set_tags(self, kb_id: str, tag_ids: Sequence[str]) -> KnowledgeBase: ...

    async def linked_to_workflow(self, workflow_id: str) -> _KnowledgeBaseList: ...

    async def replace_workflow_links(
        self, workflow_id: str, kb_ids: Sequence[str]
    ) -> None: ...


class SqlKnowledgeBaseRepository(TenantScopedRepository[KnowledgeBase]):
    """SQLModel-backed implementation of KnowledgeBaseRepository.

    Deleting a knowledge base cascades to its sources, pages, tag attachments,
    and workflow links, so ``delete`` never reports it as referenced.
    """

    model = KnowledgeBase

    def __init__(
        self,
        session: AsyncSession,
        *,
        tenant_id: str | None,
        access_tag_ids: frozenset[str] | None = None,
    ) -> None:
        """Store the session, the tenant scope, and the caller's access-control tags.

        Args:
            session: The SQLModel session to run queries on.
            tenant_id: Tenant every query is filtered by, or ``None`` for a
                platform-scoped read across every tenant.
            access_tag_ids: The caller's group tags for access control, or
                ``None`` for an unrestricted caller -- see
                :class:`repositories.tags.TagLinks`. The agent tools pass the
                acting user's set too -- the run's initiator, or the user
                chatting in a design session -- so an agent sees only the
                linked knowledge bases that user could open.
        """
        super().__init__(session, tenant_id=tenant_id)
        self._tags = TagLinks(
            session,
            KnowledgeBaseTag,
            tenant_id=tenant_id,
            access_tag_ids=access_tag_ids,
        )

    def _visibility_clause(self) -> ColumnElement[bool] | None:
        """Hide knowledge bases gated by an access-control tag the caller does not hold."""
        return self._tags.visibility_clause(col(KnowledgeBase.id))

    async def get(self, kb_id: str) -> KnowledgeBase | None:
        """Return the KnowledgeBase with the given ID, or ``None`` if missing or hidden."""
        return await self._get_scoped(kb_id)

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
        tag_ids: Sequence[str] = (),
    ) -> list[KnowledgeBase]:
        """Return a page of KnowledgeBases, defaulting to ``created_at`` descending.

        ``tag_ids`` narrows the page to knowledge bases carrying **every**
        listed tag, applied before the page window.
        """
        stmt = self._scoped(select(KnowledgeBase))
        for clause in self._tags.filter_clauses(col(KnowledgeBase.id), tag_ids):
            stmt = stmt.where(clause)
        stmt = apply_filters(stmt, KnowledgeBase, filters, readable=KnowledgeBaseRead)
        stmt = apply_sort(
            stmt,
            KnowledgeBase,
            sort,
            default=[col(KnowledgeBase.created_at).desc()],
            readable=KnowledgeBaseRead,
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def create(self, data: KnowledgeBaseCreate, *, user_id: str) -> KnowledgeBase:
        """Insert a new KnowledgeBase in the current tenant.

        Raises:
            UniqueViolationError: If the name is already taken in this tenant.
        """
        kb = KnowledgeBase.model_validate(
            {
                **data.model_dump(),
                "tenant_id": self._require_tenant(),
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        self._db.add(kb)
        await _commit_named(self._db, user_id=user_id, name=data.name)
        await self._db.refresh(kb)
        return kb

    async def update(
        self, kb_id: str, data: KnowledgeBaseUpdate, *, user_id: str
    ) -> KnowledgeBase:
        """Apply the fields set on ``data`` to a KnowledgeBase.

        Raises:
            NotFoundError: If the knowledge base does not exist or is hidden.
            UniqueViolationError: If the new name is already taken in this tenant.
        """
        self._require_tenant()
        kb = await self._get_scoped(kb_id)
        if kb is None:
            raise NotFoundError("KnowledgeBase", kb_id)
        kb.sqlmodel_update(data.model_dump(exclude_unset=True))
        kb.updated_by = user_id
        self._db.add(kb)
        await _commit_named(self._db, user_id=user_id, name=kb.name)
        await self._db.refresh(kb)
        return kb

    async def delete(self, kb_id: str) -> None:
        """Delete a KnowledgeBase together with everything that hangs off it.

        Raises:
            NotFoundError: If the knowledge base does not exist or is hidden.
        """
        self._require_tenant()
        kb = await self._get_scoped(kb_id)
        if kb is None:
            raise NotFoundError("KnowledgeBase", kb_id)
        await self._db.delete(kb)
        await self._db.commit()

    async def tag_ids_for(self, kb_id: str) -> _StrList:
        """Return the sorted ids of the tags attached to one KnowledgeBase."""
        return await self._tags.for_one(kb_id)

    async def tag_ids_for_many(self, kb_ids: Sequence[str]) -> dict[str, _StrList]:
        """Return each KnowledgeBase's sorted tag ids, in one query."""
        return await self._tags.for_many(kb_ids)

    async def set_tags(self, kb_id: str, tag_ids: Sequence[str]) -> KnowledgeBase:
        """Replace a KnowledgeBase's tag attachments wholesale.

        Raises:
            NotFoundError: If the knowledge base does not exist or is hidden.
            ForeignKeyViolationError: If any id does not name a tag of this tenant.
        """
        self._require_tenant()
        kb = await self._get_scoped(kb_id)
        if kb is None:
            raise NotFoundError("KnowledgeBase", kb_id)
        await self._tags.validate(tag_ids)
        await self._tags.replace(kb_id, tag_ids)
        await self._db.commit()
        await self._db.refresh(kb)
        return kb

    async def linked_to_workflow(self, workflow_id: str) -> _KnowledgeBaseList:
        """Return the knowledge bases linked to a workflow, ordered by name.

        Filtered like every other read, so a restricted caller sees only the
        linked knowledge bases they could open themselves.

        Args:
            workflow_id: Id of the workflow whose links to read.

        Returns:
            The linked knowledge bases.
        """
        stmt = self._scoped(
            select(KnowledgeBase)
            .join(
                WorkflowKnowledgeBase,
                col(WorkflowKnowledgeBase.knowledge_base_id) == col(KnowledgeBase.id),
            )
            .where(col(WorkflowKnowledgeBase.workflow_id) == workflow_id)
            .order_by(col(KnowledgeBase.name))
        )
        return list((await self._db.exec(stmt)).all())

    async def replace_workflow_links(
        self, workflow_id: str, kb_ids: Sequence[str]
    ) -> None:
        """Replace the set of knowledge bases a workflow is linked to.

        The caller is responsible for having checked that the workflow exists
        in this tenant; every knowledge base id is checked here with ``get``,
        so a restricted caller cannot link one they could not open.

        Args:
            workflow_id: Id of the workflow to relink.
            kb_ids: Ids of the knowledge bases it should read; empty unlinks all.

        Raises:
            ForeignKeyViolationError: If an id names no knowledge base the
                caller can see in this tenant.
        """
        self._require_tenant()
        for kb_id in kb_ids:
            if await self._get_scoped(kb_id) is None:
                raise ForeignKeyViolationError("KnowledgeBase", kb_id)
        await self._db.exec(
            delete(WorkflowKnowledgeBase).where(
                col(WorkflowKnowledgeBase.workflow_id) == workflow_id
            )
        )
        for kb_id in kb_ids:
            self._db.add(
                WorkflowKnowledgeBase(workflow_id=workflow_id, knowledge_base_id=kb_id)
            )
        await self._db.commit()


#: Columns of :class:`KnowledgeSourceRead`, i.e. every column but ``data``, so a
#: listing never loads the stored documents.
_SOURCE_READ_COLUMNS = [
    col(getattr(KnowledgeSource, name))
    for name in KnowledgeSourceRead.model_fields
    if name != "citation_key"
]


class SqlKnowledgeSourceRepository(TenantScopedRepository[KnowledgeSource]):
    """Tenant-scoped persistence for the URLs and documents feeding a knowledge base."""

    model = KnowledgeSource

    async def add(
        self,
        kb_id: str,
        *,
        kind: KnowledgeSourceKind,
        user_id: str,
        url: str | None = None,
        file_name: str | None = None,
        content_type: str | None = None,
        data: bytes | None = None,
    ) -> KnowledgeSource:
        """Register a new source, ``pending`` its first ingest.

        Args:
            kb_id: Id of the knowledge base it feeds; checked by the caller.
            kind: Whether it is a URL or an uploaded file.
            user_id: Id of the user registering it.
            url: The page to fetch, for a URL source.
            file_name: The uploaded file's sanitized name.
            content_type: The upload's declared media type.
            data: The uploaded file's bytes.

        Returns:
            The stored source.
        """
        source = KnowledgeSource(
            tenant_id=self._require_tenant(),
            knowledge_base_id=kb_id,
            kind=kind,
            url=url,
            file_name=file_name,
            content_type=content_type,
            data=data,
            size_bytes=len(data) if data is not None else 0,
            created_by=user_id,
            updated_by=user_id,
        )
        self._db.add(source)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(source)
        return source

    async def get(self, source_id: str) -> KnowledgeSource | None:
        """Return one source with its bytes, or ``None`` if it is not in this tenant."""
        return await self._get_scoped(source_id)

    async def list_for(self, kb_id: str) -> list[KnowledgeSourceRead]:
        """Return every source of a knowledge base, newest first, without their bytes."""
        stmt = (
            select(*_SOURCE_READ_COLUMNS)
            .where(col(KnowledgeSource.knowledge_base_id) == kb_id)
            .order_by(col(KnowledgeSource.created_at).desc())
        )
        rows = (await self._db.exec(self._scoped(stmt))).all()
        return [
            KnowledgeSourceRead.model_validate(
                {**row._asdict(), "citation_key": citation_key_for(row.id)}
            )
            for row in rows
        ]

    async def set_status(
        self,
        source: KnowledgeSource,
        status: KnowledgeSourceStatus,
        *,
        user_id: str,
        error: str | None = None,
        title: str | None = None,
    ) -> None:
        """Record a source's state and commit everything pending in the session.

        This commit is also what persists the page edits a job flushed before
        it -- see the module docstring. ``ready`` stamps ``ingested_at``.

        Args:
            source: The source row, loaded in this session.
            status: The state to record.
            user_id: Id of the user whose action started the job.
            error: The failure reason; cleared unless given.
            title: The document's title, when the job learned it.
        """
        source.status = status
        source.error = error
        if title:
            source.title = title[:500]
        if status is KnowledgeSourceStatus.ready:
            source.ingested_at = datetime.now(UTC)
        source.updated_by = user_id
        self._db.add(source)
        await self._db.commit()
        await self._db.refresh(source)

    async def delete(self, source: KnowledgeSource) -> None:
        """Delete a source and commit everything pending in the session."""
        await self._db.delete(source)
        await self._db.commit()


class SqlKnowledgePageRepository(TenantScopedRepository[KnowledgePage]):
    """Tenant-scoped persistence for the pages of knowledge bases.

    Writes flush rather than commit -- see the module docstring.
    """

    model = KnowledgePage

    async def list_for(self, kb_id: str) -> list[KnowledgePage]:
        """Return every page of a knowledge base, ordered by path.

        # ponytail: loads whole pages including bodies; select summary columns
        # once knowledge bases grow to thousands of pages.
        """
        stmt = (
            select(KnowledgePage)
            .where(col(KnowledgePage.knowledge_base_id) == kb_id)
            .order_by(col(KnowledgePage.path))
        )
        return list((await self._db.exec(self._scoped(stmt))).all())

    async def get(self, kb_id: str, path: str) -> KnowledgePage | None:
        """Return the page at ``path`` in a knowledge base, or ``None``."""
        stmt = select(KnowledgePage).where(
            col(KnowledgePage.knowledge_base_id) == kb_id,
            col(KnowledgePage.path) == path,
        )
        return (await self._db.exec(self._scoped(stmt))).first()

    async def upsert(
        self,
        kb_id: str,
        path: str,
        *,
        type_: str,
        title: str,
        description: str,
        body: str,
        meta: dict[str, Any],
        user_id: str,
    ) -> KnowledgePage:
        """Create the page at ``path``, or replace the existing one's content. Flushes only.

        Args:
            kb_id: Id of the knowledge base the page belongs to.
            path: Bundle-relative path with a leading ``/``.
            type_: The OKF ``type``.
            title: The page title.
            description: One-sentence summary.
            body: Markdown body.
            meta: The remaining frontmatter (``tags``, ``sources``, ``generated``).
            user_id: Id of the user whose action started the job.

        Returns:
            The page as it now stands.
        """
        page = await self.get(kb_id, path)
        if page is None:
            page = KnowledgePage(
                tenant_id=self._require_tenant(),
                knowledge_base_id=kb_id,
                path=path,
                type=type_,
                title=title,
                created_by=user_id,
                updated_by=user_id,
            )
        page.type = type_
        page.title = title
        page.description = description
        page.body = body
        page.meta = meta
        page.updated_by = user_id
        self._db.add(page)
        await self._db.flush()
        return page

    async def delete(self, page: KnowledgePage) -> None:
        """Delete a page. Flushes only."""
        await self._db.delete(page)
        await self._db.flush()

    async def search(
        self, kb_ids: Sequence[str], terms: Sequence[str], *, limit: int
    ) -> list[KnowledgePage]:
        """Return pages whose title, description, or body contains any of ``terms``.

        Case-insensitive substring matching; the caller ranks the result.

        # ponytail: LIKE scan over every page; move to PostgreSQL full-text
        # search (tsvector + GIN) when knowledge bases get large.

        Args:
            kb_ids: Knowledge bases to search.
            terms: Words to look for; a page matching any one is returned.
            limit: Maximum number of candidate pages.

        Returns:
            Matching pages, unranked.
        """
        if not kb_ids or not terms:
            return []
        matches = [
            column.icontains(term, autoescape=True)
            for term in terms
            for column in (
                col(KnowledgePage.title),
                col(KnowledgePage.description),
                col(KnowledgePage.body),
            )
        ]
        stmt = (
            select(KnowledgePage)
            .where(col(KnowledgePage.knowledge_base_id).in_(kb_ids), or_(*matches))
            .limit(limit)
        )
        return list((await self._db.exec(self._scoped(stmt))).all())

    async def delete_all_for(self, kb_id: str) -> None:
        """Delete every page of a knowledge base. Flushes only."""
        await self._db.exec(
            delete(KnowledgePage).where(
                col(KnowledgePage.knowledge_base_id) == kb_id,
                col(KnowledgePage.tenant_id) == self._require_tenant(),
            )
        )
        await self._db.flush()
