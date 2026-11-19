"""Use case service for Tenant resources.

Wraps the :class:`TenantRepository` with the business rules the routers need:
raising :class:`NotFoundError` when a tenant is missing, encrypting (with the
tenant's own data key, see :mod:`infrastructure.secret_cipher`) the tenant's
Vault credentials (for its own Vault and for the global one) before
they are stored, refusing a Vault connection that could never authenticate,
validating and encrypting the OIDC single sign-on settings, keeping each stored
credential (OIDC client secret, LLM API key) exclusive with the secret reference
that may stand in for it, and resetting the users' linked OIDC subjects when the
provider changes. Authorization (the
``super_admin`` role gate) lives entirely in the router — tenants have no
ownership rules to enforce here.
"""

from collections.abc import Callable, Sequence
from typing import Any
from urllib.parse import urlsplit

from config import get_settings
from infrastructure.secret_cipher import SecretCipher, data_key_cipher, new_data_key
from infrastructure.secret_resolver import split_secret_ref
from infrastructure.url_safety import assert_public_http_url
from models.tenant import (
    AdminSettingsUpdate,
    LlmMode,
    Tenant,
    TenantCreate,
    TenantUpdate,
)
from repositories.exceptions import (
    ForbiddenError,
    ForeignKeyViolationError,
    NotFoundError,
    TenantLimitReachedError,
    TenantValidationError,
)
from repositories.query import FilterSpec, SortSpec
from repositories.secret import SecretRepository
from repositories.tenant import TenantRepository
from repositories.user import UserRepository
from services.llm_settings import prepare_llm_fields
from services.vault_settings import prepare_vault_fields

#: Each stored credential paired with the secret reference that can stand in
#: for it. The two are exclusive (see :meth:`TenantService._prefer_one`).
_CREDENTIAL_REFS = (
    ("oidc_client_secret", "oidc_client_secret_ref"),
    ("llm_api_key", "llm_api_key_ref"),
)


class _TenantWrite(TenantUpdate, AdminSettingsUpdate):
    """Every writable tenant field, for handing a prepared payload to the repository.

    A payload is built from either write schema, but the rules in
    :class:`TenantService` may touch fields only the other one declares (a
    super admin's new LLM key clears the admin's key reference), and
    ``model_construct`` would silently drop those on the narrower class.
    """


class TenantService:
    """Application service orchestrating Tenant operations."""

    def __init__(
        self,
        repo: TenantRepository,
        users: UserRepository,
        secrets_for_tenant: Callable[[str], SecretRepository],
    ) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing Tenant persistence.
            users: Repository used to reset linked OIDC subjects when a
                tenant's identity provider changes.
            secrets_for_tenant: Builds the secret repository of a tenant, used
                to check that a credential's secret reference names one of
                that tenant's secrets.
        """
        self._repo = repo
        self._users = users
        self._secrets_for_tenant = secrets_for_tenant

    def _prepare_oidc(
        self, current: Tenant | None, payload: dict[str, Any], cipher: SecretCipher
    ) -> None:
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
            cipher: The tenant's data-key cipher.

        Raises:
            TenantValidationError: If a changed issuer is not an https URL on a
                public host (an allowlisted host may also use http, and skips
                the address check), or SSO would be enabled without an issuer,
                a client id and a secret (stored, or referenced from one of the
                tenant's secrets). An issuer resent unchanged is not
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
                payload["oidc_client_secret"] = cipher.encrypt(secret)
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
            merged("issuer")
            and merged("client_id")
            and (merged("client_secret") or merged("client_secret_ref"))
        ):
            raise TenantValidationError(
                "oidcIssuer, oidcClientId and oidcClientSecret (or "
                "oidcClientSecretRef) are required when oidcEnabled is true"
            )

    @staticmethod
    def _prefer_one(payload: dict[str, Any]) -> None:
        """Make a stored credential and its secret reference exclusive.

        Mutates ``payload`` in place, after the credentials were encrypted (so a
        truthy value means one is being set): setting a reference clears the
        stored credential, and setting a credential clears the reference.

        Args:
            payload: The fields the caller set.

        Raises:
            TenantValidationError: If one write sets both a credential and its
                reference, which leaves no telling which was meant.
        """
        for value, ref in _CREDENTIAL_REFS:
            if payload.get(ref) and payload.get(value):
                raise TenantValidationError(f"set either {value} or {ref}, not both")
            if payload.get(ref):
                payload[value] = None
            elif payload.get(value):
                payload[ref] = None

    async def _check_refs(self, tenant_id: str, payload: dict[str, Any]) -> None:
        """Refuse a secret reference naming no secret of the tenant.

        Resolution stays lazy -- a secret deleted later fails the next sign-in
        or agent run, not this write -- but a reference must name a secret
        that exists when it is set.

        Args:
            tenant_id: The tenant whose secrets a reference may name.
            payload: The fields the caller set.

        Raises:
            ForeignKeyViolationError: If a reference names no such secret.
        """
        for _, ref in _CREDENTIAL_REFS:
            if not payload.get(ref):
                continue
            name, _ = split_secret_ref(payload[ref])
            if await self._secrets_for_tenant(tenant_id).get_by_name(name) is None:
                raise ForeignKeyViolationError("Secret", name)

    def _prepare(
        self, current: Tenant | None, payload: dict[str, Any], cipher: SecretCipher
    ) -> None:
        """Drop null sign-in limits and run the shared Vault and OIDC write rules.

        Mutates ``payload`` in place. An explicit ``None`` for a sign-in limit
        is dropped, since those columns cannot be empty; both Vault connections
        (``vault_*`` and ``global_vault_*``) go through
        :func:`services.vault_settings.prepare_vault_fields`, and the
        ``oidc_*`` fields through :meth:`_prepare_oidc`.

        Args:
            current: The stored tenant, or ``None`` on create.
            payload: The fields the caller set.
            cipher: The tenant's data-key cipher, which encrypts every
                credential in ``payload``.

        Raises:
            TenantValidationError: If the merged Vault connection would be
                unusable, or the OIDC settings invalid.
        """
        # The sign-in limits and the LLM mode are non-nullable columns with
        # defaults; an explicit null means "leave as is", not "clear".
        for field in ("login_max_failures", "login_lockout_minutes", "llm_mode"):
            if payload.get(field, 0) is None:
                payload.pop(field)
        for prefix in ("vault_", "global_vault_"):
            prepare_vault_fields(
                current, payload, cipher, TenantValidationError, prefix=prefix
            )
        self._prepare_oidc(current, payload, cipher)
        prepare_llm_fields(payload, cipher)
        self._prefer_one(payload)

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
            TenantLimitReachedError: If the deployment already holds its
                maximum number of tenants (``system_settings.max_tenants``).
            TenantValidationError: If the Vault connection would be unusable.
        """
        # ponytail: count-then-insert, so creations racing within a few
        # milliseconds can overshoot the limit by one; take a lock if that matters.
        if await self._repo.at_capacity():
            raise TenantLimitReachedError()
        payload = data.model_dump()
        # The row does not exist yet, so its data key is made here: the
        # credentials in the payload are encrypted with it before the insert.
        data_key = new_data_key()
        self._prepare(None, payload, data_key_cipher(data_key))
        return await self._repo.create(
            TenantCreate.model_construct(**payload), user_id=user_id, data_key=data_key
        )

    async def update(
        self,
        tenant_id: str,
        data: TenantUpdate | AdminSettingsUpdate,
        *,
        user_id: str,
    ) -> Tenant:
        """Apply a partial update to a Tenant.

        Handing the tenant's LLM to its ``admin`` (``llm_mode`` turning
        ``tenant_admin``) clears the stored model, API key and key reference,
        except one the same write sets: what a super admin entered is not the
        admin's. A stored credential and its secret reference replace each
        other (:meth:`_prefer_one`).

        Args:
            tenant_id: Identifier of the tenant to update.
            data: Fields to update: the super admin's tenant fields, or the
                tenant's own admin-managed settings.
            user_id: Identifier of the acting user, recorded as the updater.

        Returns:
            The updated Tenant.

        Raises:
            NotFoundError: If no tenant exists with the given ID.
            ForbiddenError: If the tenant's own ``admin`` sets an ``llm_*`` field
                while a ``super_admin`` has not handed the tenant's LLM to it
                (:attr:`~models.tenant.LlmMode.tenant_admin`).
            TenantValidationError: If the merged Vault connection would be
                unusable, the OIDC settings invalid, the tenant's own ``admin``
                would leave an LLM model without an API key (stored or
                referenced), or one write sets a credential and its reference.
            ForeignKeyViolationError: If a secret reference names no secret of
                the tenant.
        """
        current = await self.get(tenant_id)
        payload = data.model_dump(exclude_unset=True)
        if (
            isinstance(data, AdminSettingsUpdate)
            and any(field.startswith("llm_") for field in payload)
            and current.llm_mode != LlmMode.tenant_admin
        ):
            raise ForbiddenError(
                "The LLM of this tenant is not set by its admin; ask a super admin."
            )
        if (
            current.llm_mode != LlmMode.tenant_admin
            and payload.get("llm_mode") == LlmMode.tenant_admin
        ):
            # Any stored model and key are ones a super admin entered (the admin
            # could not write them before this hand-over), and not the admin's
            # to inherit: the admin starts from an empty LLM, unless this same
            # write names a model or key. A blank key normally means "keep the
            # stored one", which is exactly what is not wanted here.
            payload.setdefault("llm_model", None)
            if not payload.get("llm_api_key"):
                payload["llm_api_key"] = None
            payload.setdefault("llm_api_key_ref", None)
        self._prepare(current, payload, data_key_cipher(current.data_key))
        await self._check_refs(tenant_id, payload)
        if isinstance(data, AdminSettingsUpdate) and any(
            field.startswith("llm_") for field in payload
        ):
            # An admin's model needs the tenant's own key, or the platform's
            # would pay for it (``LlmSettingsResolver`` ignores such a model
            # anyway; this makes the save say so).
            model = payload.get("llm_model", current.llm_model)
            key = payload.get("llm_api_key", current.llm_api_key)
            ref = payload.get("llm_api_key_ref", current.llm_api_key_ref)
            if model and not (key or ref):
                raise TenantValidationError("llmApiKey is required with llmModel")
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
            tenant_id, _TenantWrite.model_construct(**payload), user_id=user_id
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
