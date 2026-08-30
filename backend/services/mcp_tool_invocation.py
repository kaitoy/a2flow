"""Use case service for the tenant-wide MCP tool-invocation audit: List and Get.

Rows are written only by :class:`infrastructure.mcp_audit.SqlMcpAuditSink` as the
proxy decides each ``call_tool`` -- see :mod:`models.mcp_tool_invocation`. This
service therefore exposes reads only; there is deliberately no ``create()``,
``update()``, or ``delete()``, which is what keeps the trail append-only.

Distinct from :meth:`services.workflow_execution.WorkflowExecutionService.list_tool_invocations`,
which narrows to one run and admits that run's participants. This one spans the
acting tenant and is reachable only by an admin.
"""

from collections.abc import Sequence

from models.mcp_tool_invocation import MCPToolInvocation
from repositories.exceptions import NotFoundError
from repositories.mcp_tool_invocation import McpToolInvocationRepository
from repositories.query import FilterSpec, SortSpec


class McpToolInvocationService:
    """Application service orchestrating MCP tool-invocation audit reads."""

    def __init__(self, repo: McpToolInvocationRepository) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing invocation persistence, already scoped to
                the acting tenant (or to every tenant for a platform-scoped
                caller browsing with the all-tenants selection).
        """
        self._repo = repo

    async def get(self, invocation_id: str) -> MCPToolInvocation:
        """Return the recorded decision with the given ID.

        Args:
            invocation_id: The record's primary key.

        Returns:
            The recorded decision.

        Raises:
            NotFoundError: If no record exists with that ID in the acting tenant.
        """
        invocation = await self._repo.get(invocation_id)
        if invocation is None:
            raise NotFoundError("MCPToolInvocation", invocation_id)
        return invocation

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[MCPToolInvocation]:
        """Return a page of recorded decisions in the acting tenant.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of records.
        """
        return await self._repo.list(
            limit=limit, offset=offset, sort=sort, filters=filters
        )
