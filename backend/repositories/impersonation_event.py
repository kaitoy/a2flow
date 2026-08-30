"""ImpersonationEvent repository: Protocol interface and SQLModel-backed implementation.

``impersonation_events`` has no ``tenant_id`` of its own -- it references users,
which are platform-scoped -- so the audit reads here scope rows by joining
``users`` on ``target_user_id`` and filtering the *target's* tenant. Filtering on
the target rather than the actor is what makes a platform-scoped ``super_admin``
impersonating a tenant user visible to that tenant's admins: the actor carries no
``tenant_id`` at all, while the target names the tenant whose data was touched.

That join is how these queries stay scoped, so this module is not a fourth entry
in the audited list of intentionally tenant-unscoped repositories in
``.claude/rules/backend-patterns.md``. The three write methods are genuinely
unscoped, as they always were: they act on an actor/target pair the request layer
has already validated.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from models.impersonation_event import ImpersonationEvent, ImpersonationEventRead
from models.user import User
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort


class ImpersonationEventRepository(Protocol):
    """Interface for impersonation audit-trail persistence operations."""

    async def create(
        self, *, impersonator_id: str, target_user_id: str
    ) -> ImpersonationEvent: ...

    async def get_open(
        self, *, impersonator_id: str, target_user_id: str
    ) -> ImpersonationEvent | None: ...

    async def close_open_for_actor(
        self, impersonator_id: str
    ) -> ImpersonationEvent | None: ...

    async def get(self, event_id: str) -> ImpersonationEventRead | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[ImpersonationEventRead]: ...


class SqlImpersonationEventRepository:
    """SQLModel-backed implementation of :class:`ImpersonationEventRepository`."""

    def __init__(self, session: AsyncSession, *, tenant_id: str | None = None) -> None:
        """Initialize the repository.

        Args:
            session: The request-scoped async database session.
            tenant_id: Tenant the audit reads are scoped to, or ``None`` to read
                across every tenant. Defaults to ``None`` because the three
                write methods never consult it -- they act on an actor/target
                pair the request layer has already validated -- so the
                impersonation flow constructs this repository with the session
                alone.
        """
        self._db = session
        self._tenant_id = tenant_id

    async def create(
        self, *, impersonator_id: str, target_user_id: str
    ) -> ImpersonationEvent:
        """Insert a new open impersonation event.

        Args:
            impersonator_id: The real, session-authenticated actor's id.
            target_user_id: The id of the user being impersonated.

        Returns:
            The persisted, still-open ``ImpersonationEvent``.
        """
        event = ImpersonationEvent(
            impersonator_id=impersonator_id, target_user_id=target_user_id
        )
        self._db.add(event)
        await self._db.commit()
        await self._db.refresh(event)
        return event

    async def get_open(
        self, *, impersonator_id: str, target_user_id: str
    ) -> ImpersonationEvent | None:
        """Return the open event for this exact actor/target pair, if any.

        Args:
            impersonator_id: The real, session-authenticated actor's id.
            target_user_id: The id of the user being impersonated.

        Returns:
            The matching open ``ImpersonationEvent``, or ``None``.
        """
        stmt = select(ImpersonationEvent).where(
            col(ImpersonationEvent.impersonator_id) == impersonator_id,
            col(ImpersonationEvent.target_user_id) == target_user_id,
            col(ImpersonationEvent.ended_at).is_(None),
        )
        return (await self._db.exec(stmt)).first()

    async def close_open_for_actor(
        self, impersonator_id: str
    ) -> ImpersonationEvent | None:
        """Close the most recent open event for this actor, if any.

        Args:
            impersonator_id: The real, session-authenticated actor's id.

        Returns:
            The closed ``ImpersonationEvent``, or ``None`` if none was open.
        """
        stmt = (
            select(ImpersonationEvent)
            .where(
                col(ImpersonationEvent.impersonator_id) == impersonator_id,
                col(ImpersonationEvent.ended_at).is_(None),
            )
            .order_by(col(ImpersonationEvent.started_at).desc())
        )
        event = (await self._db.exec(stmt)).first()
        if event is None:
            return None
        event.ended_at = datetime.now(UTC)
        self._db.add(event)
        await self._db.commit()
        await self._db.refresh(event)
        return event

    def _scoped_select(self) -> SelectOfScalar[ImpersonationEvent]:
        """Build the audit select, narrowed to targets in this tenant.

        Scoping uses an ``IN`` subquery over ``users`` rather than a join so the
        statement stays a scalar select over ``ImpersonationEvent`` -- which is
        what :func:`repositories.query.apply_filters` and
        :func:`~repositories.query.apply_sort` resolve field names against.

        The narrowing is conditional: ``tenant_id=None`` means "every tenant"
        (see ``get_current_tenant_scope`` in ``dependencies/auth.py``), and
        comparing ``User.tenant_id`` against ``None`` would compile to
        ``IS NULL`` and match only platform-scoped targets instead.

        Returns:
            A select over the events this repository may read.
        """
        stmt = select(ImpersonationEvent)
        if self._tenant_id is not None:
            stmt = stmt.where(
                col(ImpersonationEvent.target_user_id).in_(
                    select(User.id).where(col(User.tenant_id) == self._tenant_id)
                )
            )
        return stmt

    async def _read_many(
        self, events: list[ImpersonationEvent]
    ) -> list[ImpersonationEventRead]:
        """Attach each event's target tenant and fold the rows into read views.

        Resolves every target's tenant in one extra query rather than joining it
        into :meth:`_scoped_select`, which has to stay a scalar select for the
        filter/sort helpers. One query per page is cheap; an N+1 would not be.

        Declared before :meth:`list` on purpose: once a method named ``list``
        exists in this class body, a later ``list[...]`` annotation resolves to
        that method instead of the builtin.

        Args:
            events: The page of events to decorate.

        Returns:
            The read views, in the order the events were given.
        """
        if not events:
            return []
        target_ids = {event.target_user_id for event in events}
        rows = await self._db.exec(
            select(User.id, User.tenant_id).where(col(User.id).in_(target_ids))
        )
        tenant_by_user = {user_id: tenant_id for user_id, tenant_id in rows.all()}
        return [
            ImpersonationEventRead(
                **event.model_dump(),
                target_tenant_id=tenant_by_user.get(event.target_user_id),
            )
            for event in events
        ]

    async def get(self, event_id: str) -> ImpersonationEventRead | None:
        """Return one recorded session by id, scoped to the target's tenant.

        A cross-tenant id returns ``None``, which the service turns into a 404 --
        so an admin is never told an event exists in a tenant they cannot see.

        Args:
            event_id: The event's primary key.

        Returns:
            The read view, or ``None`` when no such event exists within this
            repository's tenant scope.
        """
        stmt = self._scoped_select().where(col(ImpersonationEvent.id) == event_id)
        event = (await self._db.exec(stmt)).first()
        if event is None:
            return None
        return (await self._read_many([event]))[0]

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[ImpersonationEventRead]:
        """Return a page of recorded sessions, most recently started first.

        Ordering defaults to ``startedAt`` descending rather than the usual
        ``createdAt``: this table skips :class:`~models.base.BaseEntity`, so it
        has no ``created_at`` column.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of read views.
        """
        stmt = self._scoped_select()
        stmt = apply_filters(
            stmt, ImpersonationEvent, filters, readable=ImpersonationEventRead
        )
        stmt = apply_sort(
            stmt,
            ImpersonationEvent,
            sort,
            default=[col(ImpersonationEvent.started_at).desc()],
            readable=ImpersonationEventRead,
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return await self._read_many([*result.all()])
