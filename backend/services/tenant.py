"""Use case service for Tenant resources.

Wraps the :class:`TenantRepository` with the business rule the routers need:
raising :class:`NotFoundError` when a tenant is missing. Authorization (the
``super_admin`` role gate) lives entirely in the router — tenants have no
ownership rules to enforce here.
"""

from collections.abc import Sequence

from models.tenant import Tenant, TenantCreate, TenantUpdate
from repositories import TenantRepository
from repositories.exceptions import NotFoundError
from repositories.query import FilterSpec, SortSpec


class TenantService:
    """Application service orchestrating Tenant operations."""

    def __init__(self, repo: TenantRepository) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing Tenant persistence.
        """
        self._repo = repo

    async def get(self, tenant_id: str) -> Tenant:
        """Return the Tenant with the given ID.

        Args:
            tenant_id: Identifier of the tenant to fetch.

        Returns:
            The matching Tenant.

        Raises:
            NotFoundError: If no tenant exists with the given ID.
        """
        tenant = await self._repo.get(tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant", tenant_id)
        return tenant

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[Tenant]:
        """Return a page of Tenant records.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of tenants.
        """
        return await self._repo.list(
            limit=limit, offset=offset, sort=sort, filters=filters
        )

    async def create(self, data: TenantCreate, *, user_id: str) -> Tenant:
        """Create a new Tenant.

        Args:
            data: Fields for the new tenant.
            user_id: Identifier of the acting user, recorded as the creator.

        Returns:
            The created Tenant.
        """
        return await self._repo.create(data, user_id=user_id)

    async def update(
        self, tenant_id: str, data: TenantUpdate, *, user_id: str
    ) -> Tenant:
        """Apply a partial update to a Tenant.

        Args:
            tenant_id: Identifier of the tenant to update.
            data: Fields to update.
            user_id: Identifier of the acting user, recorded as the updater.

        Returns:
            The updated Tenant.

        Raises:
            NotFoundError: If no tenant exists with the given ID.
        """
        return await self._repo.update(tenant_id, data, user_id=user_id)

    async def delete(self, tenant_id: str) -> None:
        """Delete a Tenant.

        Args:
            tenant_id: Identifier of the tenant to delete.

        Raises:
            NotFoundError: If no tenant exists with the given ID.
            ReferencedError: If users remain assigned to the tenant.
        """
        await self._repo.delete(tenant_id)
