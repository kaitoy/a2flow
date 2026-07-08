"""Use case service for Secret resources.

Wraps the :class:`SecretRepository` with the two business rules the routers
need: plaintext values are encrypted before they reach the repository (so the
persistence layer never sees them), and partial updates are validated against
the *merged* per-type shape — ``SecretCreate``'s validator covers POST bodies,
but only the service can combine a PATCH body with the stored record.
"""

from collections.abc import Sequence

from infrastructure.secret_cipher import SecretCipher
from models.secret import Secret, SecretCreate, SecretType, SecretUpdate
from repositories import SecretRepository
from repositories.exceptions import NotFoundError, SecretValidationError
from repositories.query import FilterSpec, SortSpec

#: The Vault reference fields that must all be present on a ``vault`` secret
#: and all be absent on a ``local`` one.
_VAULT_FIELDS = ("vault_mount", "vault_path", "vault_key")


class SecretService:
    """Application service orchestrating Secret operations."""

    def __init__(self, repo: SecretRepository, cipher: SecretCipher) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing Secret persistence.
            cipher: Cipher used to encrypt local secret values before storage.
        """
        self._repo = repo
        self._cipher = cipher

    async def get(self, secret_id: str) -> Secret:
        """Return the Secret with the given ID.

        Args:
            secret_id: Identifier of the secret to fetch.

        Returns:
            The matching Secret.

        Raises:
            NotFoundError: If no secret exists with the given ID.
        """
        secret = await self._repo.get(secret_id)
        if secret is None:
            raise NotFoundError("Secret", secret_id)
        return secret

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[Secret]:
        """Return a page of Secret records.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of secrets.
        """
        return await self._repo.list(
            limit=limit, offset=offset, sort=sort, filters=filters
        )

    async def create(self, data: SecretCreate, *, user_id: str) -> Secret:
        """Create a new Secret, encrypting a local value before persistence.

        Args:
            data: Fields for the new secret; shape already validated by
                :class:`SecretCreate`.
            user_id: ID of the user creating the secret.

        Returns:
            The created Secret.
        """
        if data.type is SecretType.local and data.value is not None:
            data = data.model_copy(update={"value": self._cipher.encrypt(data.value)})
        return await self._repo.create(data, user_id=user_id)

    async def update(
        self, secret_id: str, data: SecretUpdate, *, user_id: str
    ) -> Secret:
        """Apply a partial update, validating the merged per-type shape.

        The effective type is ``data.type`` when provided, else the stored
        type. Fields explicitly sent in the PATCH must fit the effective
        type's shape; fields belonging to the *other* shape that merely remain
        on the stored record (a type switch) are cleared automatically.
        Omitting ``value`` on a local secret keeps the stored ciphertext.

        Args:
            secret_id: Identifier of the secret to update.
            data: Fields to update.
            user_id: ID of the user performing the update.

        Returns:
            The updated Secret.

        Raises:
            NotFoundError: If no secret exists with the given ID.
            SecretValidationError: If the merged result violates the effective
                type's shape.
        """
        existing = await self.get(secret_id)
        effective_type = data.type or existing.type
        updates: dict[str, str | None] = {}

        provided_vault = [
            field for field in _VAULT_FIELDS if getattr(data, field) is not None
        ]
        if effective_type is SecretType.local:
            if provided_vault:
                raise SecretValidationError("A local secret must not set Vault fields")
            if data.value is not None:
                updates["value"] = self._cipher.encrypt(data.value)
            elif existing.type is not SecretType.local:
                raise SecretValidationError(
                    "Switching to a local secret requires a value"
                )
            if existing.type is not SecretType.local:
                updates.update(dict.fromkeys(_VAULT_FIELDS))
        else:
            if data.value is not None:
                raise SecretValidationError("A vault secret must not set a value")
            for field in _VAULT_FIELDS:
                effective = getattr(data, field) or (
                    getattr(existing, field)
                    if existing.type is SecretType.vault
                    else None
                )
                if effective is None:
                    raise SecretValidationError(
                        "A vault secret requires vaultMount, vaultPath, and vaultKey"
                    )
            if existing.type is not SecretType.vault:
                updates["value"] = None

        if updates:
            data = data.model_copy(update=updates)
        return await self._repo.update(secret_id, data, user_id=user_id)

    async def delete(self, secret_id: str) -> None:
        """Delete a Secret.

        Header placeholders and skill references that still name the deleted
        secret fail lazily at their next resolution.

        Args:
            secret_id: Identifier of the secret to delete.

        Raises:
            NotFoundError: If no secret exists with the given ID.
        """
        await self._repo.delete(secret_id)
