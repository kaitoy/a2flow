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

It also owns both halves of tag-based **access control** (see
:mod:`models.tag`): :meth:`TagLinks.visibility_clause` is the predicate the
owning repository folds into every caller-facing query, and
:meth:`TagLinks.validate` refuses to attach an access-control tag the caller
does not hold, so nobody hides a record from themselves by accident.
"""

from collections.abc import Sequence

from sqlalchemy import ColumnElement, Exists
from sqlalchemy.orm import Mapped
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.tag import Tag, TagLink
from repositories.exceptions import ForbiddenError, ForeignKeyViolationError

#: The owning table's id column, as returned by :func:`sqlmodel.col`.
_IdColumn = Mapped[str]


class TagLinks:
    """Reads and writes one resource type's tag attachments.

    Args:
        session: The SQLModel session to run queries on.
        link_model: The join table for this resource type, e.g.
            :class:`models.tag.SecretTag`.
        tenant_id: Tenant the owning repository is scoped to; tags outside it
            are not attachable. ``None`` means the owning repository was built
            for a read route running in "all tenants" mode -- :meth:`validate`
            is only ever reached through the owning repository's write
            methods, which guard against a ``None`` tenant before delegating
            here, so this is never actually ``None`` when it matters.
        access_tag_ids: Ids of the tags the caller holds through their groups
            (``AccessTagIdsDep``), or ``None`` when the caller is unrestricted
            -- a ``super_admin``, or a job or agent tool acting on the
            system's behalf rather than a user's. Drives
            :meth:`visibility_clause` and the lock-out check in
            :meth:`validate`; a ``TagLinks`` over ``UserGroupTag`` is built
            without it, since attaching an access-control tag to a *group* is
            how an admin grants access, not how a caller claims it.
    """

    def __init__(
        self,
        session: AsyncSession,
        link_model: type[TagLink],
        *,
        tenant_id: str | None,
        access_tag_ids: frozenset[str] | None = None,
    ) -> None:
        """Store the session, the join model, the tenant scope, and the caller's tags."""
        self._db = session
        self._link = link_model
        self._tenant_id = tenant_id
        self._access_tag_ids = access_tag_ids

    def visibility_clause(self, owner_col: _IdColumn) -> ColumnElement[bool] | None:
        """Build the predicate admitting only records the caller may act on.

        A record passes when it carries **no** access-control tag outside the
        caller's set: ``NOT EXISTS`` an attachment whose tag is flagged and
        not held. Records with no access-control tags pass trivially, so plain
        tags never restrict anything. With an empty caller set, every flagged
        tag is "not held" and every access-controlled record is hidden.

        Args:
            owner_col: The owning table's id column, e.g. ``col(Secret.id)``.

        Returns:
            The predicate, or ``None`` when the caller is unrestricted and the
            query needs no narrowing.
        """
        if self._access_tag_ids is None:
            return None
        return ~(
            select(col(self._link.resource_id))
            .join(Tag, onclause=col(Tag.id) == col(self._link.tag_id))
            .where(
                col(self._link.resource_id) == owner_col,
                col(Tag.access_control).is_(True),
                col(Tag.id).not_in(list(self._access_tag_ids)),
            )
            .exists()
        )

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

        A restricted caller is also refused any access-control tag their
        groups do not carry: attaching one would hide the record from the very
        person editing it, on the next request. An unrestricted caller (see
        ``access_tag_ids`` in the class docstring) may attach any tag.

        Args:
            tag_ids: The proposed tag ids (deduplicated by the payload model).

        Raises:
            ForeignKeyViolationError: For the first id that does not qualify.
            ForbiddenError: If any id names an access-control tag the caller
                does not hold.
        """
        if not tag_ids:
            return
        stmt = select(Tag.id, Tag.access_control).where(
            col(Tag.id).in_(list(tag_ids)), Tag.tenant_id == self._tenant_id
        )
        known = dict((await self._db.exec(stmt)).all())
        for tag_id in tag_ids:
            if tag_id not in known:
                raise ForeignKeyViolationError("Tag", tag_id)
        if self._access_tag_ids is None:
            return
        for tag_id in tag_ids:
            if known[tag_id] and tag_id not in self._access_tag_ids:
                raise ForbiddenError(
                    "Cannot attach an access-control tag your groups do not carry"
                )

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
