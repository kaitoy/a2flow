"""Use case service for MCPToolMock resources.

Wraps the :class:`MCPToolMockRepository` with the business rules the router
needs: raising :class:`NotFoundError` when a mock is missing, projecting rows
into the typed :class:`McpToolMockRead` view, and validating the *merged*
target of a partial update -- ``McpToolMockCreate``'s validator covers POST
bodies, but only the service can see what a PATCH merges into.
"""

from collections.abc import Sequence

from models.mcp_tool_mock import (
    BUILTIN_MOCKABLE_TOOLS,
    MCPToolMock,
    McpToolMockCreate,
    McpToolMockRead,
    McpToolMockUpdate,
)
from repositories import MCPToolMockRepository
from repositories.exceptions import McpToolMockValidationError, NotFoundError
from repositories.query import FilterSpec, SortSpec

#: Alias for ``list[McpToolMockRead]``: the ``list`` method below shadows the
#: builtin inside the service class body.
_ReadList = list[McpToolMockRead]


class MCPToolMockService:
    """Application service orchestrating MCPToolMock operations."""

    def __init__(self, repo: MCPToolMockRepository) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing MCPToolMock persistence.
        """
        self._repo = repo

    async def get(self, mock_id: str) -> MCPToolMock:
        """Return the MCPToolMock with the given ID.

        Args:
            mock_id: Identifier of the mock to fetch.

        Returns:
            The matching MCPToolMock.

        Raises:
            NotFoundError: If no mock exists with the given ID.
        """
        mock = await self._repo.get(mock_id)
        if mock is None:
            raise NotFoundError("MCPToolMock", mock_id)
        return mock

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
        tag_ids: Sequence[str] = (),
    ) -> list[MCPToolMock]:
        """Return a page of MCPToolMock records.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.
            tag_ids: Narrows the page to mocks carrying every listed tag.

        Returns:
            The requested page of mocks.
        """
        return await self._repo.list(
            limit=limit, offset=offset, sort=sort, filters=filters, tag_ids=tag_ids
        )

    async def to_read(self, mock: MCPToolMock) -> McpToolMockRead:
        """Project one MCPToolMock into its API read view, attaching its tags.

        Args:
            mock: The persisted mock to project.

        Returns:
            The read view, with typed responses and tag ids attached.
        """
        return McpToolMockRead.from_mock(
            mock, tag_ids=await self._repo.tag_ids_for(mock.id)
        )

    async def to_read_many(self, mocks: Sequence[MCPToolMock]) -> _ReadList:
        """Project a page of MCPToolMocks into read views, reading their tags in one query.

        Args:
            mocks: The persisted records to project.

        Returns:
            The read views, in the order they were given.
        """
        by_id = await self._repo.tag_ids_for_many([mock.id for mock in mocks])
        return [
            McpToolMockRead.from_mock(mock, tag_ids=by_id.get(mock.id, []))
            for mock in mocks
        ]

    async def set_tags(self, mock_id: str, tag_ids: Sequence[str]) -> MCPToolMock:
        """Replace an MCPToolMock's tag attachments wholesale.

        Args:
            mock_id: Identifier of the mock to retag.
            tag_ids: Ids of the tags it should carry.

        Returns:
            The mock, unchanged apart from its attachments.

        Raises:
            NotFoundError: If no mock exists with the given ID.
            ForeignKeyViolationError: If any id does not name a tag of this
                tenant.
        """
        return await self._repo.set_tags(mock_id, tag_ids)

    async def create(self, data: McpToolMockCreate, *, user_id: str) -> MCPToolMock:
        """Create a new MCPToolMock.

        Args:
            data: Fields for the new mock.
            user_id: ID of the user creating the mock.

        Returns:
            The created MCPToolMock.

        Raises:
            ForeignKeyViolationError: If ``mcp_server_id`` names no registered
                server of this tenant.
            UniqueViolationError: If the name is already taken in this tenant.
        """
        return await self._repo.create(data, user_id=user_id)

    async def update(
        self, mock_id: str, data: McpToolMockUpdate, *, user_id: str
    ) -> MCPToolMock:
        """Apply a partial update, validating the merged target.

        A mock without an ``mcp_server_id`` targets a built-in agent tool, so the
        merged ``tool_name`` must be one A2Flow knows how to stub. Either half of
        the pairing may come from the stored record, which is why this cannot be
        checked on the request body alone.

        Args:
            mock_id: Identifier of the mock to update.
            data: Fields to update.
            user_id: ID of the user performing the update.

        Returns:
            The updated MCPToolMock.

        Raises:
            NotFoundError: If no mock exists with the given ID.
            McpToolMockValidationError: If the merged mock has no
                ``mcp_server_id`` and names a tool outside
                :data:`~models.mcp_tool_mock.BUILTIN_MOCKABLE_TOOLS`.
        """
        existing = await self.get(mock_id)
        sent = data.model_dump(exclude_unset=True)
        server_id = sent.get("mcp_server_id", existing.mcp_server_id)
        tool_name = sent.get("tool_name", existing.tool_name)
        if server_id is None and tool_name not in BUILTIN_MOCKABLE_TOOLS:
            allowed = ", ".join(sorted(BUILTIN_MOCKABLE_TOOLS))
            raise McpToolMockValidationError(
                "A mock without an mcpServerId targets a built-in tool; "
                f"toolName must be one of: {allowed}"
            )
        return await self._repo.update(mock_id, data, user_id=user_id)

    async def delete(self, mock_id: str) -> None:
        """Delete an MCPToolMock.

        Runs already started are unaffected: they carry their own snapshot of the
        mocks they use (see
        :attr:`models.workflow_execution.WorkflowExecution.tool_mocks`).

        Args:
            mock_id: Identifier of the mock to delete.

        Raises:
            NotFoundError: If no mock exists with the given ID.
        """
        await self._repo.delete(mock_id)
