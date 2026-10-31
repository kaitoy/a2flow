"""Use case service for Tenant resources.

Wraps the :class:`TenantRepository` with the business rules the routers need:
raising :class:`NotFoundError` when a tenant is missing, encrypting the
tenant's Vault credential before it is stored, and refusing a Vault connection
that could never authenticate. Authorization (the ``super_admin`` role gate)
lives entirely in the router — tenants have no ownership rules to enforce here.
"""

from collections.abc import Sequence
from typing import Any

from infrastructure.secret_cipher import SecretCipher
from models.tenant import Tenant, TenantCreate, TenantUpdate, VaultAuthMethod
from repositories.exceptions import NotFoundError, TenantValidationError
from repositories.query import FilterSpec, SortSpec
from repositories.tenant import TenantRepository


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
        """Encrypt the submitted Vault credential and validate the merged result.

        Mutates ``payload`` in place. A non-empty credential is replaced by its
        ciphertext; an empty one is dropped so the stored ciphertext is kept
        (the admin form never receives it, so a blank field means "unchanged");
        an explicit ``None`` is kept and clears it.

        Args:
            current: The stored tenant, or ``None`` on create.
            payload: The fields the caller set.

        Raises:
            TenantValidationError: If the merged result names a Vault address
                without an auth method or credential, switches the auth method
                while keeping the old method's credential, or names the AppRole
                method without a role id.
        """
        new_credential = False
        if "vault_credential" in payload:
            credential = payload["vault_credential"]
            if credential:
                payload["vault_credential"] = self._cipher.encrypt(credential)
                new_credential = True
            elif credential is not None:
                payload.pop("vault_credential")

        def merged(field: str) -> object:
            if field in payload:
                return payload[field]
            return getattr(current, field) if current is not None else None

        if not merged("vault_addr"):
            return
        method = merged("vault_auth_method")
        if method is None:
            raise TenantValidationError(
                "vaultAuthMethod is required when vaultAddr is set"
            )
        if not merged("vault_credential"):
            raise TenantValidationError(
                "vaultCredential is required when vaultAddr is set"
            )
        if (
            current is not None
            and current.vault_credential
            and method != current.vault_auth_method
            and not new_credential
        ):
            # A stored token must never be replayed as an AppRole secret id
            # (or the reverse): a method switch needs its own credential.
            raise TenantValidationError(
                "vaultCredential is required when vaultAuthMethod changes"
            )
        if method == VaultAuthMethod.approle and not merged("vault_role_id"):
            raise TenantValidationError(
                "vaultRoleId is required for the approle auth method"
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
            TenantValidationError: If the merged Vault connection would be
                unusable.
        """
        current = await self.get(tenant_id)
        payload = data.model_dump(exclude_unset=True)
        self._prepare(current, payload)
        return await self._repo.update(
            tenant_id, TenantUpdate.model_construct(**payload), user_id=user_id
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
