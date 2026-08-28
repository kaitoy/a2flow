"""MCPToolMock repository: Protocol interface and SQLModel-backed implementation."""

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.mcp_tool_mock import (
    MCPToolMock,
    McpToolMockCreate,
    McpToolMockRead,
    McpToolMockUpdate,
)
from repositories._integrity import is_foreign_key_error
from repositories.exceptions import (
    ForeignKeyViolationError,
    NotFoundError,
    UniqueViolationError,
)
from repositories.mcp_server import MCPServerRepository
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort


class MCPToolMockRepository(Protocol):
    """Interface for MCPToolMock persistence operations."""

    async def get(self, mock_id: str) -> MCPToolMock | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[MCPToolMock]: ...

    async def create(self, data: McpToolMockCreate, *, user_id: str) -> MCPToolMock: ...

    async def update(
        self, mock_id: str, data: McpToolMockUpdate, *, user_id: str
    ) -> MCPToolMock: ...

    async def delete(self, mock_id: str) -> None: ...

    async def exists(self, mock_id: str) -> bool: ...


class SqlMcpToolMockRepository:
    """SQLModel-backed implementation of MCPToolMockRepository.

    ``create`` and ``update`` validate ``mcp_server_id`` against the MCPServer
    repository before writing, so a mock naming an unregistered server fails with
    a message that names the server rather than with a bare integrity error. A
    ``None`` ``mcp_server_id`` targets a built-in agent tool and is not checked.

    ``delete`` needs no ``ReferencedError`` branch: a run copies the mocks it
    uses into :attr:`models.workflow_execution.WorkflowExecution.tool_mocks`
    rather than referencing this row, precisely so deleting a mock cannot change
    how an existing run behaves.
    """

    def __init__(
        self,
        session: AsyncSession,
        server_repo: MCPServerRepository,
        *,
        tenant_id: str | None,
    ) -> None:
        """Store the session, the MCPServer repository, and the tenant scope."""
        self._db = session
        self._servers = server_repo
        self._tenant_id = tenant_id

    def _require_tenant(self) -> str:
        """Return ``self._tenant_id``, raising if this instance has no concrete tenant.

        Only a write method should call this -- see
        ``repositories.mcp_server.SqlMCPServerRepository._require_tenant``.
        """
        if self._tenant_id is None:
            raise RuntimeError(
                f"{type(self).__name__} mutation requires a concrete tenant_id"
            )
        return self._tenant_id

    async def _get_scoped(self, mock_id: str) -> MCPToolMock | None:
        """Return the MCPToolMock with the given ID within the current tenant, or ``None``."""
        stmt = select(MCPToolMock).where(MCPToolMock.id == mock_id)
        if self._tenant_id is not None:
            stmt = stmt.where(MCPToolMock.tenant_id == self._tenant_id)
        result = await self._db.exec(stmt)
        return result.first()

    async def _assert_server(self, mcp_server_id: str | None) -> None:
        """Reject a mock whose ``mcp_server_id`` names no server of this tenant.

        Args:
            mcp_server_id: The referenced server, or ``None`` for a built-in tool.

        Raises:
            ForeignKeyViolationError: If the id names no MCPServer in this tenant.
        """
        if mcp_server_id is None:
            return
        if not await self._servers.exists(mcp_server_id):
            raise ForeignKeyViolationError("MCPServer", mcp_server_id)

    async def get(self, mock_id: str) -> MCPToolMock | None:
        """Return the MCPToolMock with the given ID, or ``None`` if missing."""
        return await self._get_scoped(mock_id)

    async def exists(self, mock_id: str) -> bool:
        """Return ``True`` if an MCPToolMock with the given ID exists."""
        return await self._get_scoped(mock_id) is not None

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[MCPToolMock]:
        """Return a page of MCPToolMocks, defaulting to ``created_at`` descending."""
        stmt = select(MCPToolMock)
        if self._tenant_id is not None:
            stmt = stmt.where(MCPToolMock.tenant_id == self._tenant_id)
        stmt = apply_filters(stmt, MCPToolMock, filters, readable=McpToolMockRead)
        stmt = apply_sort(
            stmt,
            MCPToolMock,
            sort,
            default=[col(MCPToolMock.created_at).desc()],
            readable=McpToolMockRead,
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def create(self, data: McpToolMockCreate, *, user_id: str) -> MCPToolMock:
        """Create a new MCPToolMock, raising UniqueViolationError on duplicate name."""
        tenant_id = self._require_tenant()
        await self._assert_server(data.mcp_server_id)
        mock = MCPToolMock.model_validate(
            {
                **data.model_dump(),
                "tenant_id": tenant_id,
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        self._db.add(mock)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_foreign_key_error(e):
                raise ForeignKeyViolationError("User", user_id) from e
            raise UniqueViolationError("MCPToolMock", "name", data.name) from e
        await self._db.refresh(mock)
        return mock

    async def update(
        self, mock_id: str, data: McpToolMockUpdate, *, user_id: str
    ) -> MCPToolMock:
        """Apply a partial update, raising NotFoundError or UniqueViolationError."""
        self._require_tenant()
        mock = await self._get_scoped(mock_id)
        if mock is None:
            raise NotFoundError("MCPToolMock", mock_id)
        update = data.model_dump(exclude_unset=True)
        if "mcp_server_id" in update:
            await self._assert_server(update["mcp_server_id"])
        mock.sqlmodel_update(update)
        mock.updated_by = user_id
        self._db.add(mock)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_foreign_key_error(e):
                raise ForeignKeyViolationError("User", user_id) from e
            raise UniqueViolationError(
                "MCPToolMock", "name", str(update.get("name", ""))
            ) from e
        await self._db.refresh(mock)
        return mock

    async def delete(self, mock_id: str) -> None:
        """Delete the MCPToolMock, raising NotFoundError when it does not exist."""
        self._require_tenant()
        mock = await self._get_scoped(mock_id)
        if mock is None:
            raise NotFoundError("MCPToolMock", mock_id)
        await self._db.delete(mock)
        await self._db.commit()
