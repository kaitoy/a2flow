"""Base class for the SQL repositories of tenant-scoped entities.

Every repository over a :class:`models.tenant_scoped.TenantScoped` table holds
the same two things -- the session and the tenant its queries are filtered by --
and answers the same three questions with the same queries: "is there a concrete
tenant to write into?", "which row has this id *in my tenant*?", and "does that
row exist?". This class holds those once; a repository subclasses it and names
its table in ``model``.

Two scopes are distinguished. :meth:`TenantScopedRepository._in_tenant` is the
tenant predicate alone -- the rows that *exist* for this caller's tenant.
:meth:`TenantScopedRepository._scoped` narrows that further by
:meth:`TenantScopedRepository._visibility_clause` -- the rows the caller may
*act on*, which for a taggable repository excludes records gated by an
access-control tag the caller does not hold (see :mod:`models.tag`). Caller-
facing reads and writes use ``_scoped``; reference resolution on behalf of
another record (``exists`` for foreign-key checks, a lookup by name for a
``${secret:...}`` placeholder) uses ``_in_tenant``, since a workflow may
legitimately use a skill or secret its runner could not open in the admin UI.
"""

from typing import Generic, Protocol, TypeVar

from sqlalchemy import ColumnElement
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar


class TenantRow(Protocol):
    """The columns the base class filters on: any ``TenantScoped`` ``BaseEntity``."""

    id: str
    tenant_id: str


M = TypeVar("M", bound=TenantRow)
T = TypeVar("T")


class TenantScopedRepository(Generic[M]):
    """Session, tenant scope, and the id lookup shared by tenant-scoped repositories.

    ``tenant_id`` is ``None`` only for a read route running in "all tenants"
    mode (see ``CurrentTenantScopeDep``); every query then drops the tenant
    predicate, and every write must go through :meth:`_require_tenant`.
    """

    #: The table this repository reads and writes.
    model: type[M]

    def __init__(self, session: AsyncSession, *, tenant_id: str | None) -> None:
        """Store the session and the tenant these operations are scoped to.

        Args:
            session: The request-scoped (or job-scoped) database session.
            tenant_id: Tenant every query is filtered by, or ``None`` for a
                platform-scoped read across every tenant.
        """
        self._db = session
        self._tenant_id = tenant_id

    def _require_tenant(self) -> str:
        """Return ``self._tenant_id``, raising if this instance has no concrete tenant.

        Only a write method should call this. A write route always resolves a
        concrete tenant via the strict ``CurrentTenantIdDep``, so reaching
        ``None`` here means a write route was mis-wired to the permissive
        dependency -- a bug, not a state a real request should produce.

        Returns:
            The concrete tenant id.

        Raises:
            RuntimeError: If the repository was built without a tenant.
        """
        if self._tenant_id is None:
            raise RuntimeError(
                f"{type(self).__name__} mutation requires a concrete tenant_id"
            )
        return self._tenant_id

    def _in_tenant(self, stmt: SelectOfScalar[T]) -> SelectOfScalar[T]:
        """Add the tenant predicate to ``stmt`` unless reading across all tenants.

        The rows that *exist* for this caller, regardless of whether they may
        act on them -- see the module docstring for when that is the right
        scope.

        Args:
            stmt: A select over :attr:`model` (or a column of it).

        Returns:
            The statement, filtered to this repository's tenant when it has one.
        """
        if self._tenant_id is not None:
            stmt = stmt.where(self.model.tenant_id == self._tenant_id)
        return stmt

    def _visibility_clause(self) -> ColumnElement[bool] | None:
        """Return the predicate narrowing :meth:`_scoped` to rows the caller may act on.

        ``None`` by default: most tables have no visibility rule beyond the
        tenant. A taggable repository overrides this with
        :meth:`repositories.tags.TagLinks.visibility_clause`.

        Returns:
            The extra predicate, or ``None`` for no narrowing.
        """
        return None

    def _scoped(self, stmt: SelectOfScalar[T]) -> SelectOfScalar[T]:
        """Narrow ``stmt`` to the rows the caller may act on.

        :meth:`_in_tenant` plus :meth:`_visibility_clause`. Every caller-facing
        read and write goes through this, so a record the caller may not see
        reads as missing (a 404) rather than as forbidden -- the same
        convention as a cross-tenant id.

        Args:
            stmt: A select over :attr:`model` (or a column of it).

        Returns:
            The statement, filtered to this repository's tenant and to the
            caller's visibility.
        """
        stmt = self._in_tenant(stmt)
        clause = self._visibility_clause()
        if clause is not None:
            stmt = stmt.where(clause)
        return stmt

    async def _get_scoped(self, id_: str) -> M | None:
        """Return the row with the given id the caller may act on, or ``None``.

        A filtered ``select`` rather than ``session.get`` so a cross-tenant or
        access-controlled id reads as missing (surfacing as a 404) instead of
        a row the caller may not see.

        Args:
            id_: The primary key to look up.

        Returns:
            The row, or ``None`` when absent, in another tenant, or hidden
            from the caller.
        """
        stmt = self._scoped(select(self.model).where(self.model.id == id_))
        return (await self._db.exec(stmt)).first()

    async def exists(self, id_: str) -> bool:
        """Return ``True`` if a row with the given id exists in the current tenant.

        Deliberately :meth:`_in_tenant`, not :meth:`_scoped`: this backs
        foreign-key validation ("does the skill this workflow names exist?"),
        which asks about existence, not about what the caller may open.

        Args:
            id_: The primary key to look up.

        Returns:
            Whether the row exists in this repository's tenant.
        """
        stmt = self._in_tenant(select(self.model.id).where(self.model.id == id_))
        return (await self._db.exec(stmt)).first() is not None
