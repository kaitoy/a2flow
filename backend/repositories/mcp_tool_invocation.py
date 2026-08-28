"""MCP tool-invocation audit repository: Protocol and SQLModel implementation.

Append-only: there is no ``update`` or ``delete``. ``list`` reads a run's rows
back for ``GET /workflow-executions/{id}/tool-invocations``; nothing else in the
application touches them, and no route can alter or remove one.
"""

from collections.abc import Sequence
from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

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


class SqlMcpToolInvocationRepository:
    """SQLModel-backed implementation of McpToolInvocationRepository."""

    def __init__(self, session: AsyncSession, *, tenant_id: str | None) -> None:
        """Store the session and the tenant these records belong to.

        Args:
            session: The proxy's open database session.
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
        the proxy, which writes a denial on its way out through an exception:
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
        return list(result.all())
