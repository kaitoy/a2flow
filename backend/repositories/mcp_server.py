"""MCPServer repository: Protocol interface and SQLModel-backed implementation."""

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.mcp_server import MCPServer, MCPServerCreate, MCPServerUpdate
from repositories._integrity import is_foreign_key_error
from repositories.exceptions import (
    ForeignKeyViolationError,
    NotFoundError,
    ReferencedError,
    UniqueViolationError,
)
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort


class MCPServerRepository(Protocol):
    """Interface for MCPServer persistence operations."""

    async def get(self, server_id: str) -> MCPServer | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[MCPServer]: ...

    async def create(self, data: MCPServerCreate, *, user_id: str) -> MCPServer: ...

    async def update(
        self, server_id: str, data: MCPServerUpdate, *, user_id: str
    ) -> MCPServer: ...

    async def delete(self, server_id: str) -> None: ...

    async def exists(self, server_id: str) -> bool: ...


class SqlMCPServerRepository:
    """SQLModel-backed implementation of MCPServerRepository.

    ``create`` and ``update`` translate a unique-name violation into
    UniqueViolationError; ``delete`` catches IntegrityError and re-raises it as
    ReferencedError when the server is still referenced by WorkflowTask tool
    bindings (``ondelete=RESTRICT``).
    """

    def __init__(self, session: AsyncSession) -> None:
        """Store the SQLModel session used for all operations."""
        self._db = session

    async def get(self, server_id: str) -> MCPServer | None:
        """Return the MCPServer with the given ID, or ``None`` if missing."""
        return await self._db.get(MCPServer, server_id)

    async def exists(self, server_id: str) -> bool:
        """Return ``True`` if an MCPServer with the given ID exists."""
        return (await self._db.get(MCPServer, server_id)) is not None

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[MCPServer]:
        """Return a page of MCPServers, defaulting to ``created_at`` descending."""
        stmt = apply_filters(select(MCPServer), MCPServer, filters)
        stmt = apply_sort(
            stmt, MCPServer, sort, default=[col(MCPServer.created_at).desc()]
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def create(self, data: MCPServerCreate, *, user_id: str) -> MCPServer:
        """Create a new MCPServer, raising UniqueViolationError on duplicate name."""
        server = MCPServer.model_validate(
            {**data.model_dump(), "created_by": user_id, "updated_by": user_id}
        )
        self._db.add(server)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_foreign_key_error(e):
                raise ForeignKeyViolationError("User", user_id) from e
            raise UniqueViolationError("MCPServer", "name", data.name) from e
        await self._db.refresh(server)
        return server

    async def update(
        self, server_id: str, data: MCPServerUpdate, *, user_id: str
    ) -> MCPServer:
        """Apply a partial update, raising NotFoundError or UniqueViolationError."""
        server = await self._db.get(MCPServer, server_id)
        if server is None:
            raise NotFoundError("MCPServer", server_id)
        update = data.model_dump(exclude_unset=True)
        server.sqlmodel_update(update)
        server.updated_by = user_id
        self._db.add(server)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_foreign_key_error(e):
                raise ForeignKeyViolationError("User", user_id) from e
            raise UniqueViolationError(
                "MCPServer", "name", str(update.get("name", ""))
            ) from e
        await self._db.refresh(server)
        return server

    async def delete(self, server_id: str) -> None:
        """Delete the MCPServer, raising ReferencedError while tool bindings remain."""
        server = await self._db.get(MCPServer, server_id)
        if server is None:
            raise NotFoundError("MCPServer", server_id)
        await self._db.delete(server)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            raise ReferencedError(
                "MCPServer is referenced by one or more WorkflowTask tool bindings"
            ) from e
