"""Use case service for MCPServer resources.

Wraps the :class:`MCPServerRepository` with the business rules the routers need
(raising :class:`NotFoundError` when a server is missing, and validating the
*merged* per-transport shape — ``MCPServerCreate``'s validator covers POST
bodies, but only the service can see what a PATCH merges into) and hosts the
one orchestration the admin UI's tool picker needs: connecting to a registered
server to list the tools it advertises.
"""

from collections.abc import Sequence
from typing import Any

from infrastructure.mcp_connection import resolve_connection
from infrastructure.mcp_executor import get_mcp_executor
from infrastructure.secret_resolver import SecretResolver
from models.mcp_server import (
    MCPServer,
    MCPServerCreate,
    McpServerRead,
    MCPServerUpdate,
    McpToolInfo,
    McpTransport,
    referenced_env_names,
)
from repositories import MCPServerRepository
from repositories.exceptions import McpServerValidationError, NotFoundError
from repositories.query import FilterSpec, SortSpec

# Module-level alias for ``list[McpToolInfo]``. The service defines a method
# named ``list``, which causes mypy to resolve a bare ``list[...]`` annotation
# in methods declared after it to that method rather than the builtin; the
# alias is evaluated in module scope where ``list`` is unambiguously the builtin.
_McpToolInfoList = list[McpToolInfo]


#: Alias for ``list[McpServerRead]``: the ``list`` method below shadows the
#: builtin inside the service class body.
_ReadList = list[McpServerRead]


class MCPServerService:
    """Application service orchestrating MCPServer operations."""

    def __init__(self, repo: MCPServerRepository, resolver: SecretResolver) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing MCPServer persistence.
            resolver: Resolver expanding ``${secret:NAME/KEY}`` placeholders in
                header values before connecting to a server.
        """
        self._repo = repo
        self._resolver = resolver

    async def get(self, server_id: str) -> MCPServer:
        """Return the MCPServer with the given ID.

        Args:
            server_id: Identifier of the server to fetch.

        Returns:
            The matching MCPServer.

        Raises:
            NotFoundError: If no server exists with the given ID.
        """
        server = await self._repo.get(server_id)
        if server is None:
            raise NotFoundError("MCPServer", server_id)
        return server

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
        tag_ids: Sequence[str] = (),
    ) -> list[MCPServer]:
        """Return a page of MCPServer records.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.
            tag_ids: Narrows the page to servers carrying every listed tag.

        Returns:
            The requested page of servers.
        """
        return await self._repo.list(
            limit=limit, offset=offset, sort=sort, filters=filters, tag_ids=tag_ids
        )

    async def to_read(self, server: MCPServer) -> McpServerRead:
        """Project one MCPServer into its API read view, attaching its tags.

        Args:
            server: The persisted server to project.

        Returns:
            The read view, with tag ids attached.
        """
        return McpServerRead.from_server(
            server, tag_ids=await self._repo.tag_ids_for(server.id)
        )

    async def to_read_many(self, servers: Sequence[MCPServer]) -> _ReadList:
        """Project a page of MCPServers into read views, reading their tags in one query.

        Args:
            servers: The persisted records to project.

        Returns:
            The read views, in the order they were given.
        """
        by_id = await self._repo.tag_ids_for_many([x.id for x in servers])
        return [
            McpServerRead.from_server(x, tag_ids=by_id.get(x.id, [])) for x in servers
        ]

    async def set_tags(self, server_id: str, tag_ids: Sequence[str]) -> MCPServer:
        """Replace a MCPServer's tag attachments wholesale.

        Args:
            server_id: Identifier of the server to retag.
            tag_ids: Ids of the tags it should carry.

        Returns:
            The server, unchanged apart from its attachments.

        Raises:
            NotFoundError: If no server exists with the given ID.
            ForeignKeyViolationError: If any id does not name a tag of this
                tenant.
        """
        return await self._repo.set_tags(server_id, tag_ids)

    async def create(self, data: MCPServerCreate, *, user_id: str) -> MCPServer:
        """Create a new MCPServer.

        Args:
            data: Fields for the new server.
            user_id: ID of the user creating the server.

        Returns:
            The created MCPServer.
        """
        return await self._repo.create(data, user_id=user_id)

    async def update(
        self, server_id: str, data: MCPServerUpdate, *, user_id: str
    ) -> MCPServer:
        """Apply a partial update, validating the merged per-transport shape.

        The effective transport is ``data.transport`` when provided, else the
        stored one. Fields explicitly sent in the PATCH must fit the effective
        transport's shape; fields belonging to the *other* transport that
        merely remain on the stored record (a transport switch) are cleared
        automatically. For a stdio server, any ``${env:NAME}`` placeholder in
        the effective ``args`` must name a key of the effective ``env`` — both
        computed the same way as ``effective`` itself, since a PATCH may touch
        only one of the two fields.

        Args:
            server_id: Identifier of the server to update.
            data: Fields to update.
            user_id: ID of the user performing the update.

        Returns:
            The updated MCPServer.

        Raises:
            NotFoundError: If no server exists with the given ID.
            McpServerValidationError: If the merged result violates the
                effective transport's shape, or its ``args`` embed a
                ``${env:NAME}`` placeholder naming a key absent from the
                effective ``env``.
        """
        existing = await self.get(server_id)
        effective = data.transport or existing.transport
        updates: dict[str, Any] = {}

        if effective is McpTransport.streamable_http:
            if data.command is not None or data.args or data.env:
                raise McpServerValidationError(
                    "A streamable_http server must not set command, args, or env"
                )
            if existing.transport is not McpTransport.streamable_http:
                if data.url is None:
                    raise McpServerValidationError(
                        "Switching to a streamable_http server requires a url"
                    )
                updates.update({"command": None, "args": [], "env": {}})
        else:
            if data.url is not None or data.headers:
                raise McpServerValidationError(
                    "A stdio server must not set url or headers"
                )
            if existing.transport is not McpTransport.stdio:
                if data.command is None:
                    raise McpServerValidationError(
                        "Switching to a stdio server requires a command"
                    )
                updates.update({"url": None, "headers": {}})
            effective_args = data.args if data.args is not None else existing.args
            effective_env = data.env if data.env is not None else existing.env
            missing = referenced_env_names(effective_args) - effective_env.keys()
            if missing:
                raise McpServerValidationError(
                    "args reference undefined env vars: " + ", ".join(sorted(missing))
                )

        if updates:
            data = data.model_copy(update=updates)
        return await self._repo.update(server_id, data, user_id=user_id)

    async def delete(self, server_id: str) -> None:
        """Delete an MCPServer.

        Args:
            server_id: Identifier of the server to delete.

        Raises:
            NotFoundError: If no server exists with the given ID.
            ReferencedError: If WorkflowTask tool bindings still reference it.
        """
        await self._repo.delete(server_id)

    async def list_tools(self, server_id: str) -> _McpToolInfoList:
        """Connect to a registered server and return its advertised tools.

        Goes through the same executor as the agent's own listings, so a stdio
        server is launched wherever the deployment launches them -- in the MCP
        proxy container, when one is configured. Nothing about *this* call is
        authorized by a task, so no tool certificate is presented; the backend
        authenticates as itself.

        Args:
            server_id: Identifier of the registered server to query.

        Returns:
            The tools the server advertises, as :class:`McpToolInfo` records.

        Raises:
            NotFoundError: If no server exists with the given ID.
            McpConnectionError: If the server cannot be reached or launched.
            SecretResolutionError: If a ``${secret:NAME/KEY}`` placeholder in the
                server's headers or environment cannot be resolved.
        """
        server = await self.get(server_id)
        connection = await resolve_connection(server, self._resolver)
        tools = await get_mcp_executor().list_tools(connection)
        return [
            McpToolInfo(
                name=tool.name,
                description=tool.description,
                input_schema=tool.inputSchema,
                output_schema=tool.outputSchema,
            )
            for tool in tools
        ]
