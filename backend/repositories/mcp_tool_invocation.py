"""MCP tool-invocation audit repository: Protocol and SQLModel implementation.

Append-only: there is no ``update`` or ``delete``. ``list_for_execution`` reads
one run's rows back for ``GET /workflow-executions/{id}/tool-invocations``, and
``list``/``get`` read them tenant-wide for the admin audit surface
(``GET /mcp-tool-invocations``); nothing else in the application touches them,
and no route can alter or remove one.
"""

from collections.abc import Sequence
from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from models.mcp_tool_invocation import (
    MCPToolInvocation,
    McpToolInvocationCreate,
)
from repositories._integrity import commit_or_translate_user_fk
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort


class McpToolInvocationRepository(Protocol):
    """Interface for recording and reading back MCP tool-call decisions."""

    async def record(
        self, data: McpToolInvocationCreate, *, user_id: str
    ) -> MCPToolInvocation: ...

    async def list_for_execution(
        self,
        execution_id: str,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[MCPToolInvocation]: ...

    async def get(self, invocation_id: str) -> MCPToolInvocation | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[MCPToolInvocation]: ...


class SqlMcpToolInvocationRepository:
    """SQLModel-backed implementation of McpToolInvocationRepository."""

    def __init__(self, session: AsyncSession, *, tenant_id: str | None) -> None:
        """Store the session and the tenant these records belong to.

        Args:
            session: The gateway's open database session.
            tenant_id: Tenant the audited run belongs to, or ``None`` for a
                super_admin read across every tenant. Recording always needs a
                concrete tenant -- see :meth:`_require_tenant`.
        """
        self._db = session
        self._tenant_id = tenant_id

    def _require_tenant(self) -> str:
        """Return ``self._tenant_id``, raising if this instance has no concrete tenant.

        Only :meth:`record` calls this -- see
        ``repositories.mcp_server.SqlMCPServerRepository._require_tenant``.
        """
        if self._tenant_id is None:
            raise RuntimeError(
                f"{type(self).__name__} recording requires a concrete tenant_id"
            )
        return self._tenant_id

    async def record(
        self, data: McpToolInvocationCreate, *, user_id: str
    ) -> MCPToolInvocation:
        """Append one decision record and commit it.

        Commits rather than leaving the transaction open because the caller is
        the gateway, which writes a denial on its way out through an exception:
        an uncommitted row would be rolled back by the session's ``__aexit__``
        and the refusal would go unrecorded.

        Args:
            data: The decision to record.
            user_id: The acting user, recorded as ``created_by``/``updated_by``.

        Returns:
            The persisted record.

        Raises:
            ForeignKeyViolationError: If the acting user does not exist.
        """
        invocation = MCPToolInvocation(
            **data.model_dump(),
            tenant_id=self._require_tenant(),
            created_by=user_id,
            updated_by=user_id,
        )
        self._db.add(invocation)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(invocation)
        return invocation

    async def _page(
        self,
        stmt: SelectOfScalar[MCPToolInvocation],
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec],
        filters: Sequence[FilterSpec],
    ) -> list[MCPToolInvocation]:
        """Apply the tenant predicate, filters, sort, and paging to a select.

        Shared by :meth:`list` and :meth:`list_for_execution` so the two cannot
        drift in how they scope or order rows.

        Declared before both on purpose: once a method named ``list`` exists in
        this class body, a later ``list[...]`` annotation resolves to that
        method instead of the builtin.

        Args:
            stmt: The select to narrow, already carrying any caller predicate.
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of records.
        """
        if self._tenant_id is not None:
            stmt = stmt.where(MCPToolInvocation.tenant_id == self._tenant_id)
        stmt = apply_filters(
            stmt, MCPToolInvocation, filters, readable=MCPToolInvocation
        )
        stmt = apply_sort(
            stmt,
            MCPToolInvocation,
            sort,
            default=[col(MCPToolInvocation.created_at).desc()],
            readable=MCPToolInvocation,
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return [*result.all()]

    async def list_for_execution(
        self,
        execution_id: str,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[MCPToolInvocation]:
        """Return a page of one run's recorded decisions, newest first by default.

        ``workflow_execution_id`` is a plain indexed column rather than a foreign
        key (see :mod:`models.mcp_tool_invocation`), so this filters on it
        directly. The tenant predicate is still applied unless this repository
        was built in all-tenants mode: a run id from another tenant otherwise
        yields an empty page rather than that tenant's evidence.

        Args:
            execution_id: The run whose decisions to read.
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of records.
        """
        stmt = select(MCPToolInvocation).where(
            MCPToolInvocation.workflow_execution_id == execution_id
        )
        return await self._page(
            stmt, limit=limit, offset=offset, sort=sort, filters=filters
        )

    async def get(self, invocation_id: str) -> MCPToolInvocation | None:
        """Return one recorded decision by id, filtered by tenant.

        Uses a filtered ``select`` rather than ``session.get`` so a cross-tenant
        id returns ``None`` (surfacing as a 404) instead of another tenant's
        evidence. The tenant predicate is dropped entirely in all-tenants mode,
        since ``tenant_id`` is non-nullable and ``Column == None`` would compile
        to ``IS NULL`` and match nothing.

        Args:
            invocation_id: The record's primary key.

        Returns:
            The row, or ``None`` when it does not exist in this tenant.
        """
        stmt = select(MCPToolInvocation).where(MCPToolInvocation.id == invocation_id)
        if self._tenant_id is not None:
            stmt = stmt.where(MCPToolInvocation.tenant_id == self._tenant_id)
        return (await self._db.exec(stmt)).first()

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[MCPToolInvocation]:
        """Return a page of the tenant's recorded decisions, newest first by default.

        Backs the tenant-wide admin audit list, unlike
        :meth:`list_for_execution` which narrows to one run.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of records.
        """
        return await self._page(
            select(MCPToolInvocation),
            limit=limit,
            offset=offset,
            sort=sort,
            filters=filters,
        )
