"""MCP tool-invocation audit repository: Protocol and SQLModel implementation.

Append-only: there is no ``update`` or ``delete``, and no ``get``/``list`` yet
either -- nothing in the application reads these rows. They exist to be read out
of the database when someone asks which approval authorized a call.
"""

from typing import Protocol

from sqlmodel.ext.asyncio.session import AsyncSession

from models.mcp_tool_invocation import (
    MCPToolInvocation,
    McpToolInvocationCreate,
)
from repositories._integrity import commit_or_translate_user_fk


class McpToolInvocationRepository(Protocol):
    """Interface for recording MCP tool-call decisions."""

    async def record(
        self, data: McpToolInvocationCreate, *, user_id: str
    ) -> MCPToolInvocation: ...


class SqlMcpToolInvocationRepository:
    """SQLModel-backed implementation of McpToolInvocationRepository."""

    def __init__(self, session: AsyncSession, *, tenant_id: str) -> None:
        """Store the session and the tenant these records belong to.

        Args:
            session: The proxy's open database session.
            tenant_id: Tenant the audited run belongs to.
        """
        self._db = session
        self._tenant_id = tenant_id

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
            tenant_id=self._tenant_id,
            created_by=user_id,
            updated_by=user_id,
        )
        self._db.add(invocation)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(invocation)
        return invocation
