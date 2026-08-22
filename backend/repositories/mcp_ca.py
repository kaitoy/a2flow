"""MCP certificate authority repository: Protocol interface and SQLModel implementation.

Not tenant-scoped, for the same reason :mod:`repositories.system_settings` isn't:
one root CA serves the whole platform (see :mod:`models.mcp_ca` for why).

Unlike the settings singleton there is no ``update`` — a root is written once
and thereafter only read. Retiring one is a rotation concern that this version
deliberately does not implement.
"""

from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.mcp_ca import MCPCertificateAuthority, McpCertificateAuthorityCreate
from repositories._integrity import is_unique_error
from repositories.exceptions import UniqueViolationError


class McpCertificateAuthorityRepository(Protocol):
    """Interface for reading and creating root certificate authorities."""

    async def get_active(self) -> MCPCertificateAuthority | None: ...

    async def get(self, ca_id: str) -> MCPCertificateAuthority | None: ...

    async def create(
        self, data: McpCertificateAuthorityCreate, *, user_id: str
    ) -> MCPCertificateAuthority: ...


class SqlMcpCertificateAuthorityRepository:
    """SQLModel-backed implementation of McpCertificateAuthorityRepository."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: The request-scoped (or job-scoped) database session.
        """
        self._db = session

    async def get_active(self) -> MCPCertificateAuthority | None:
        """Return the root CA new certificates are signed with, if one exists.

        Returns:
            The single row with ``active`` true, or ``None`` before the root has
            been generated.
        """
        result = await self._db.exec(
            select(MCPCertificateAuthority).where(
                MCPCertificateAuthority.active == True  # noqa: E712
            )
        )
        return result.first()

    async def get(self, ca_id: str) -> MCPCertificateAuthority | None:
        """Return a root CA by id, active or retired.

        Args:
            ca_id: The certificate authority's primary key.

        Returns:
            The row, or ``None`` when no such CA exists.
        """
        return await self._db.get(MCPCertificateAuthority, ca_id)

    async def create(
        self, data: McpCertificateAuthorityCreate, *, user_id: str
    ) -> MCPCertificateAuthority:
        """Persist a freshly generated root CA as the active one.

        Args:
            data: The generated certificate, encrypted key, and validity window.
            user_id: The acting user, recorded as ``created_by``/``updated_by``.

        Returns:
            The persisted row.

        Raises:
            UniqueViolationError: If another writer won the race to create the
                active root. Callers are expected to swallow this and re-read
                via :meth:`get_active` rather than retry the generation.
        """
        ca = MCPCertificateAuthority(
            **data.model_dump(),
            active=True,
            created_by=user_id,
            updated_by=user_id,
        )
        self._db.add(ca)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_unique_error(e):
                raise UniqueViolationError(
                    "MCPCertificateAuthority", "active", "true"
                ) from e
            raise
        await self._db.refresh(ca)
        return ca
