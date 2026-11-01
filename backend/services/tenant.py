"""Use case service for Tenant resources.

Wraps the :class:`TenantRepository` with the business rules the routers need:
raising :class:`NotFoundError` when a tenant is missing, encrypting the
tenant's Vault credentials (for its own Vault and for the global one) before
they are stored, and refusing a Vault connection that could never authenticate. Authorization (the ``super_admin`` role gate)
lives entirely in the router — tenants have no ownership rules to enforce here.
"""

from collections.abc import Sequence
from typing import Any

from infrastructure.secret_cipher import SecretCipher
from models.tenant import Tenant, TenantCreate, TenantSettingsUpdate, TenantUpdate
from repositories.exceptions import NotFoundError, TenantValidationError
from repositories.query import FilterSpec, SortSpec
from repositories.tenant import TenantRepository
from services.vault_settings import prepare_vault_fields


class TenantService:
    """Application service orchestrating Tenant operations."""

    def __init__(self, repo: TenantRepository, cipher: SecretCipher) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing Tenant persistence.
            cipher: Cipher used to encrypt the Vault credential before storage.
        """
        self._repo = repo
        self._cipher = cipher

    def _prepare(self, current: Tenant | None, payload: dict[str, Any]) -> None:
        """Drop null sign-in limits and run the shared Vault write rules.

        Mutates ``payload`` in place. An explicit ``None`` for a sign-in limit
        is dropped, since those columns cannot be empty; both Vault connections
        (``vault_*`` and ``global_vault_*``) go through
        :func:`services.vault_settings.prepare_vault_fields`.

        Args:
            current: The stored tenant, or ``None`` on create.
            payload: The fields the caller set.

        Raises:
            TenantValidationError: If the merged Vault connection would be
                unusable.
        """
        # The sign-in limits are non-nullable columns with defaults; an
        # explicit null means "leave as is", not "clear".
        for field in ("login_max_failures", "login_lockout_minutes"):
            if payload.get(field, 0) is None:
                payload.pop(field)
        for prefix in ("vault_", "global_vault_"):
            prepare_vault_fields(
                current, payload, self._cipher, TenantValidationError, prefix=prefix
            )

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

        Raises:
            TenantValidationError: If the Vault connection would be unusable.
        """
        payload = data.model_dump()
        self._prepare(None, payload)
        return await self._repo.create(
            TenantCreate.model_construct(**payload), user_id=user_id
        )

    async def update(
        self,
        tenant_id: str,
        data: TenantUpdate | TenantSettingsUpdate,
        *,
        user_id: str,
    ) -> Tenant:
        """Apply a partial update to a Tenant.

        Args:
            tenant_id: Identifier of the tenant to update.
            data: Fields to update: the super admin's tenant fields, or the
                tenant's own admin-managed settings.
            user_id: Identifier of the acting user, recorded as the updater.

        Returns:
            The updated Tenant.

        Raises:
            NotFoundError: If no tenant exists with the given ID.
            TenantValidationError: If the merged Vault connection would be
                unusable.
        """
        current = await self.get(tenant_id)
        payload = data.model_dump(exclude_unset=True)
        self._prepare(current, payload)
        return await self._repo.update(
            tenant_id, type(data).model_construct(**payload), user_id=user_id
        )

    async def delete(self, tenant_id: str) -> None:
        """Delete a Tenant.

        Args:
            tenant_id: Identifier of the tenant to delete.

        Raises:
            NotFoundError: If no tenant exists with the given ID.
            ReferencedError: If users remain assigned to the tenant.
        """
        await self._repo.delete(tenant_id)
