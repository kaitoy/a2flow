"""Use case service for Tenant resources.

Wraps the :class:`TenantRepository` with the business rules the routers need:
raising :class:`NotFoundError` when a tenant is missing, encrypting the
tenant's Vault credentials (for its own Vault and for the global one) before
they are stored, refusing a Vault connection that could never authenticate,
validating and encrypting the OIDC single sign-on settings, and resetting the
users' linked OIDC subjects when the provider changes. Authorization (the
``super_admin`` role gate) lives entirely in the router — tenants have no
ownership rules to enforce here.
"""

from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit

from config import get_settings
from infrastructure.secret_cipher import SecretCipher
from infrastructure.url_safety import assert_public_http_url
from models.tenant import Tenant, TenantCreate, TenantSettingsUpdate, TenantUpdate
from repositories.exceptions import NotFoundError, TenantValidationError
from repositories.query import FilterSpec, SortSpec
from repositories.tenant import TenantRepository
from repositories.user import UserRepository
from services.vault_settings import prepare_vault_fields


class TenantService:
    """Application service orchestrating Tenant operations."""

    def __init__(
        self, repo: TenantRepository, cipher: SecretCipher, users: UserRepository
    ) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing Tenant persistence.
            cipher: Cipher used to encrypt the Vault and OIDC credentials
                before storage.
            users: Repository used to reset linked OIDC subjects when a
                tenant's identity provider changes.
        """
        self._repo = repo
        self._cipher = cipher
        self._users = users

    def _prepare_oidc(self, current: Tenant | None, payload: dict[str, Any]) -> None:
        """Encrypt the OIDC client secret and validate the merged SSO settings.

        Mutates ``payload`` in place. A non-empty secret is replaced by its
        ciphertext, an empty one clears the stored secret, and a null one
        (like an omitted one) leaves it unchanged; an empty issuer or client id
        clears it, while a null ``oidc_enabled``, ``oidc_groups_claim`` or
        ``oidc_trust_email`` is dropped since those columns cannot be empty. A
        payload that sets no ``oidc_*`` field is left alone.

        Args:
            current: The stored tenant, or ``None`` on create.
            payload: The fields the caller set.

        Raises:
            TenantValidationError: If a changed issuer is not an https URL on a
                public host (an allowlisted host may also use http, and skips
                the address check), or SSO would be enabled without an issuer,
                a client id and a secret. An issuer resent unchanged is not
                checked again, so a later DNS change cannot block unrelated
                edits.
        """
        if not any(field.startswith("oidc_") for field in payload):
            return
        for field in ("oidc_enabled", "oidc_groups_claim", "oidc_trust_email"):
            if payload.get(field, 0) is None:
                payload.pop(field)
        for field in ("oidc_issuer", "oidc_client_id"):
            if payload.get(field) == "":
                payload[field] = None
        if "oidc_client_secret" in payload:
            secret = payload["oidc_client_secret"]
            if secret is None:
                payload.pop("oidc_client_secret")
            elif secret == "":
                payload["oidc_client_secret"] = None
            else:
                payload["oidc_client_secret"] = self._cipher.encrypt(secret)
        issuer = payload.get("oidc_issuer")
        if issuer and issuer != getattr(current, "oidc_issuer", None):
            allowed = get_settings().oidc_allowed_private_hosts
            parts = urlsplit(issuer)
            try:
                if parts.scheme != "https" and (parts.hostname or "").lower() not in (
                    allowed
                ):
                    raise ValueError("the issuer must use https")
                assert_public_http_url(issuer, allowed_hosts=allowed)
            except ValueError as exc:
                raise TenantValidationError(
                    f"oidcIssuer is not allowed: {exc}"
                ) from exc

        def merged(name: str) -> object:
            field = f"oidc_{name}"
            return payload[field] if field in payload else getattr(current, field, None)

        if merged("enabled") and not (
            merged("issuer") and merged("client_id") and merged("client_secret")
        ):
            raise TenantValidationError(
                "oidcIssuer, oidcClientId and oidcClientSecret are required "
                "when oidcEnabled is true"
            )

    def _prepare(self, current: Tenant | None, payload: dict[str, Any]) -> None:
        """Drop null sign-in limits and run the shared Vault and OIDC write rules.

        Mutates ``payload`` in place. An explicit ``None`` for a sign-in limit
        is dropped, since those columns cannot be empty; both Vault connections
        (``vault_*`` and ``global_vault_*``) go through
        :func:`services.vault_settings.prepare_vault_fields`, and the
        ``oidc_*`` fields through :meth:`_prepare_oidc`.

        Args:
            current: The stored tenant, or ``None`` on create.
            payload: The fields the caller set.

        Raises:
            TenantValidationError: If the merged Vault connection would be
                unusable, or the OIDC settings invalid.
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
        self._prepare_oidc(current, payload)

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
                unusable, or the OIDC settings invalid.
        """
        current = await self.get(tenant_id)
        payload = data.model_dump(exclude_unset=True)
        self._prepare(current, payload)
        # Stage the reset before the tenant write: ``clear_oidc_subjects`` does
        # not commit, so the repository's commit lands both together and a
        # failed write rolls the reset back too. The provider can therefore
        # never change while old subjects stay linked.
        if any(
            field in payload and payload[field] != getattr(current, field)
            for field in ("oidc_issuer", "oidc_client_id")
        ):
            await self._users.clear_oidc_subjects(tenant_id)
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
