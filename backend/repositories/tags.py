"""Shared helper for reading and writing the tag join tables.

Every taggable resource attaches tags through its own join table
(:class:`models.tag.SecretTag`, :class:`models.tag.WorkflowTag`, …), and all
four are structurally identical — which is why :class:`models.tag.TagLink`
names the owner column ``resource_id`` rather than ``secret_id``. That lets one
:class:`TagLinks` instance, parameterized by the join model, serve every
resource repository instead of four copies of the same four queries.

A resource repository composes this rather than inheriting it: it builds one
``TagLinks`` in its constructor and delegates. Nothing here commits — the
owning repository's ``create``/``update`` does, so an attachment change and the
row it belongs to land in the same transaction.
"""

from collections.abc import Sequence

from sqlalchemy import Exists
from sqlalchemy.orm import Mapped
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.tag import Tag, TagLink
from repositories.exceptions import ForeignKeyViolationError

#: The owning table's id column, as returned by :func:`sqlmodel.col`.
_IdColumn = Mapped[str]


class TagLinks:
    """Reads and writes one resource type's tag attachments.

    Args:
        session: The SQLModel session to run queries on.
        link_model: The join table for this resource type, e.g.
            :class:`models.tag.SecretTag`.
        tenant_id: Tenant the owning repository is scoped to; tags outside it
            are not attachable.
    """

    def __init__(
        self, session: AsyncSession, link_model: type[TagLink], *, tenant_id: str
    ) -> None:
        """Store the session, the join model, and the tenant scope."""
        self._db = session
        self._link = link_model
        self._tenant_id = tenant_id

    async def for_one(self, resource_id: str) -> list[str]:
        """Return the sorted tag ids attached to one record.

        Args:
            resource_id: Id of the record to read attachments for.

        Returns:
            The attached tag ids, sorted so the order is stable across reads.
        """
        stmt = select(self._link.tag_id).where(
            col(self._link.resource_id) == resource_id
        )
        return sorted((await self._db.exec(stmt)).all())

    async def for_many(self, resource_ids: Sequence[str]) -> dict[str, list[str]]:
        """Return each record's sorted tag ids, in one query.

        Reading a page of records one at a time would be an N+1; this is what
        the list endpoints use.

        Args:
            resource_ids: Ids of the records to read attachments for.

        Returns:
            A mapping from record id to its sorted tag ids. Every requested id
            is present, mapping to an empty list when it carries no tags.
        """
        out: dict[str, list[str]] = {rid: [] for rid in resource_ids}
        if not resource_ids:
            return out
        stmt = select(self._link).where(
            col(self._link.resource_id).in_(list(resource_ids))
        )
        for row in (await self._db.exec(stmt)).all():
            out.setdefault(row.resource_id, []).append(row.tag_id)
        return {rid: sorted(tag_ids) for rid, tag_ids in out.items()}

    async def replace(self, resource_id: str, tag_ids: Sequence[str]) -> None:
        """Detach every tag from one record and attach ``tag_ids`` afresh.

        Staged only — the caller commits.

        Args:
            resource_id: Id of the record whose attachments are replaced.
            tag_ids: Ids of the tags to attach, already validated and
                deduplicated.
        """
        existing = await self._db.exec(
            select(self._link).where(col(self._link.resource_id) == resource_id)
        )
        for row in existing.all():
            await self._db.delete(row)
        # Flush the deletes before the inserts: re-attaching a tag that is
        # already present would otherwise collide on the composite primary key
        # when SQLAlchemy orders the INSERT ahead of the DELETE.
        await self._db.flush()
        for tag_id in tag_ids:
            self._db.add(self._link(resource_id=resource_id, tag_id=tag_id))

    async def validate(self, tag_ids: Sequence[str]) -> None:
        """Reject tag ids that do not name a tag of this repository's tenant.

        A tag of another tenant is reported as a missing foreign key rather
        than a forbidden one, so attaching never confirms that an id exists
        somewhere else.

        Args:
            tag_ids: The proposed tag ids (deduplicated by the payload model).

        Raises:
            ForeignKeyViolationError: For the first id that does not qualify.
        """
        if not tag_ids:
            return
        stmt = select(Tag.id).where(
            col(Tag.id).in_(list(tag_ids)), Tag.tenant_id == self._tenant_id
        )
        known = set((await self._db.exec(stmt)).all())
        for tag_id in tag_ids:
            if tag_id not in known:
                raise ForeignKeyViolationError("Tag", tag_id)

    def filter_clauses(
        self, owner_col: _IdColumn, tag_ids: Sequence[str]
    ) -> list[Exists]:
        """Build one ``EXISTS`` clause per tag, to be ANDed into a list query.

        One clause per tag rather than a single ``IN`` is what makes the filter
        conjunctive: a record must satisfy all of them, so ``?tag=a&tag=b``
        matches only records carrying both.

        Args:
            owner_col: The owning table's id column, e.g. ``col(Secret.id)``.
            tag_ids: Ids every matching record must carry.

        Returns:
            One correlated ``EXISTS`` subquery per requested tag.
        """
        return [
            select(col(self._link.resource_id))
            .where(
                col(self._link.resource_id) == owner_col,
                col(self._link.tag_id) == tag_id,
            )
            .exists()
            for tag_id in tag_ids
        ]
