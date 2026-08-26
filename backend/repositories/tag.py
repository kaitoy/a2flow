"""Tag repository: Protocol interface and SQLModel-backed implementation."""

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.tag import Tag, TagCreate, TagUpdate
from repositories._integrity import is_foreign_key_error
from repositories.exceptions import (
    ForeignKeyViolationError,
    NotFoundError,
    ReferencedError,
    UniqueViolationError,
)
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort


class TagRepository(Protocol):
    """Interface for Tag persistence operations."""

    async def get(self, tag_id: str) -> Tag | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[Tag]: ...

    async def create(self, data: TagCreate, *, user_id: str) -> Tag: ...

    async def update(self, tag_id: str, data: TagUpdate, *, user_id: str) -> Tag: ...

    async def delete(self, tag_id: str) -> None: ...

    async def exists(self, tag_id: str) -> bool: ...


class SqlTagRepository:
    """SQLModel-backed implementation of TagRepository.

    ``create`` and ``update`` translate a unique-name violation into
    UniqueViolationError. Deleting a tag is deliberately unguarded: the join
    tables cascade, so retiring a tag detaches it from every record that
    carried it rather than being blocked by them.
    """

    def __init__(self, session: AsyncSession, *, tenant_id: str | None) -> None:
        """Store the SQLModel session and the tenant these operations are scoped to."""
        self._db = session
        self._tenant_id = tenant_id

    def _require_tenant(self) -> str:
        """Return ``self._tenant_id``, raising if this instance has no concrete tenant.

        Only a write method should call this -- see
        ``repositories.agent_skill.SqlAgentSkillRepository._require_tenant``.
        """
        if self._tenant_id is None:
            raise RuntimeError(
                f"{type(self).__name__} mutation requires a concrete tenant_id"
            )
        return self._tenant_id

    async def _get_scoped(self, tag_id: str) -> Tag | None:
        """Return the Tag with the given ID within the current tenant, or ``None``."""
        stmt = select(Tag).where(Tag.id == tag_id)
        if self._tenant_id is not None:
            stmt = stmt.where(Tag.tenant_id == self._tenant_id)
        result = await self._db.exec(stmt)
        return result.first()

    async def get(self, tag_id: str) -> Tag | None:
        """Return the Tag with the given ID, or ``None`` if missing."""
        return await self._get_scoped(tag_id)

    async def exists(self, tag_id: str) -> bool:
        """Return ``True`` if a Tag with the given ID exists."""
        return await self._get_scoped(tag_id) is not None

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[Tag]:
        """Return a page of Tags, defaulting to ``name`` ascending.

        Tags are picked from a list by name far more often than they are
        reviewed by recency, so this is the one resource whose default order is
        alphabetical rather than ``created_at`` descending.
        """
        stmt = select(Tag)
        if self._tenant_id is not None:
            stmt = stmt.where(Tag.tenant_id == self._tenant_id)
        stmt = apply_filters(stmt, Tag, filters, readable=Tag)
        stmt = apply_sort(
            stmt,
            Tag,
            sort,
            default=[col(Tag.name).asc()],
            readable=Tag,
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def create(self, data: TagCreate, *, user_id: str) -> Tag:
        """Create a new Tag, raising UniqueViolationError on duplicate name."""
        tag = Tag.model_validate(
            {
                **data.model_dump(),
                "tenant_id": self._require_tenant(),
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        self._db.add(tag)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_foreign_key_error(e):
                raise ForeignKeyViolationError("User", user_id) from e
            raise UniqueViolationError("Tag", "name", data.name) from e
        await self._db.refresh(tag)
        return tag

    async def update(self, tag_id: str, data: TagUpdate, *, user_id: str) -> Tag:
        """Apply a partial update, raising NotFoundError or UniqueViolationError."""
        self._require_tenant()
        tag = await self._get_scoped(tag_id)
        if tag is None:
            raise NotFoundError("Tag", tag_id)
        update = data.model_dump(exclude_unset=True)
        tag.sqlmodel_update(update)
        tag.updated_by = user_id
        self._db.add(tag)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_foreign_key_error(e):
                raise ForeignKeyViolationError("User", user_id) from e
            raise UniqueViolationError(
                "Tag", "name", str(update.get("name", ""))
            ) from e
        await self._db.refresh(tag)
        return tag

    async def delete(self, tag_id: str) -> None:
        """Delete the Tag, raising NotFoundError when missing.

        Attachments cascade away with it, so a tag in use is still deletable —
        the records simply stop carrying it.
        """
        self._require_tenant()
        tag = await self._get_scoped(tag_id)
        if tag is None:
            raise NotFoundError("Tag", tag_id)
        await self._db.delete(tag)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            raise ReferencedError("Tag is referenced by other records") from e
