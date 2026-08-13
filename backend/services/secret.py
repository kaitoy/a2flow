"""Use case service for Secret resources.

Wraps the :class:`SecretRepository` with the two business rules the routers
need: plaintext entry values are encrypted before they reach the repository (so
the persistence layer never sees them), and partial updates are validated
against the *merged* per-type shape — ``SecretCreate``'s validator covers POST
bodies, but only the service can combine a PATCH body with the stored record.

Listing a secret's entry keys is delegated to
:class:`~infrastructure.secret_resolver.SecretResolver`, the one component that
already knows how to reach both storage backends, so the "can this Vault path
be read" guards are not restated here.
"""

from collections.abc import Sequence

from infrastructure.secret_cipher import SecretCipher
from infrastructure.secret_resolver import SecretResolver
from models.secret import Secret, SecretCreate, SecretRead, SecretType, SecretUpdate
from repositories import SecretRepository
from repositories.exceptions import NotFoundError, SecretValidationError
from repositories.query import FilterSpec, SortSpec

#: Alias for ``list[SecretRead]``: the ``list`` method below shadows the
#: builtin inside the service class body.
_ReadList = list[SecretRead]

#: The Vault reference fields that must all be present on a ``vault`` secret
#: and all be absent on a ``local`` one.
_VAULT_FIELDS = ("vault_mount", "vault_path")


class SecretService:
    """Application service orchestrating Secret operations."""

    def __init__(
        self, repo: SecretRepository, cipher: SecretCipher, resolver: SecretResolver
    ) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing Secret persistence.
            cipher: Cipher used to encrypt local secret values before storage.
            resolver: Resolver used to enumerate a secret's entry keys, which
                for a ``vault`` secret means a live read of its KV v2 path.
        """
        self._repo = repo
        self._cipher = cipher
        self._resolver = resolver

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

    async def list_keys(self, secret_id: str) -> list[str]:
        """Return the entry keys of one Secret, exposing no value.

        Args:
            secret_id: Identifier of the secret whose keys are wanted.

        Returns:
            The entry keys in sorted order.

        Raises:
            NotFoundError: If no secret exists with the given ID.
            SecretResolutionError: If the secret is ``vault``-typed and its
                path cannot be read.
        """
        return await self._resolver.list_keys(await self.get(secret_id))

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
        tag_ids: Sequence[str] = (),
    ) -> list[Secret]:
        """Return a page of Secret records.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.
            tag_ids: Narrows the page to secrets carrying every listed tag.

        Returns:
            The requested page of secrets.
        """
        return await self._repo.list(
            limit=limit, offset=offset, sort=sort, filters=filters, tag_ids=tag_ids
        )

    async def to_read(self, secret: Secret) -> SecretRead:
        """Project one Secret into its API read view, attaching its tags.

        Args:
            secret: The persisted secret to project.

        Returns:
            The read view, with values dropped and tag ids attached.
        """
        return SecretRead.from_secret(
            secret, tag_ids=await self._repo.tag_ids_for(secret.id)
        )

    async def to_read_many(self, secrets: Sequence[Secret]) -> _ReadList:
        """Project a page of Secrets into read views, reading their tags in one query.

        Args:
            secrets: The persisted secrets to project.

        Returns:
            The read views, in the order they were given.
        """
        by_id = await self._repo.tag_ids_for_many([s.id for s in secrets])
        return [SecretRead.from_secret(s, tag_ids=by_id.get(s.id, [])) for s in secrets]

    async def set_tags(self, secret_id: str, tag_ids: Sequence[str]) -> Secret:
        """Replace a Secret's tag attachments wholesale.

        Args:
            secret_id: Identifier of the secret to retag.
            tag_ids: Ids of the tags it should carry.

        Returns:
            The secret, unchanged apart from its attachments.

        Raises:
            NotFoundError: If no secret exists with the given ID.
            ForeignKeyViolationError: If any id does not name a tag of this
                tenant.
        """
        return await self._repo.set_tags(secret_id, tag_ids)

    async def create(self, data: SecretCreate, *, user_id: str) -> Secret:
        """Create a new Secret, encrypting local entry values before persistence.

        Args:
            data: Fields for the new secret; shape already validated by
                :class:`SecretCreate`.
            user_id: ID of the user creating the secret.

        Returns:
            The created Secret.
        """
        if data.type is SecretType.local and data.entries:
            encrypted = {
                key: self._cipher.encrypt(value) for key, value in data.entries.items()
            }
            data = data.model_copy(update={"entries": encrypted})
        return await self._repo.create(data, user_id=user_id)

    async def update(
        self, secret_id: str, data: SecretUpdate, *, user_id: str
    ) -> Secret:
        """Apply a partial update, validating the merged per-type shape.

        The effective type is ``data.type`` when provided, else the stored
        type. Fields explicitly sent in the PATCH must fit the effective
        type's shape; fields belonging to the *other* shape that merely remain
        on the stored record (a type switch) are cleared automatically.

        Omitting ``entries`` on a local secret keeps the stored map. Supplying
        it replaces the map wholesale — keys left out are removed — with an
        empty-string value meaning "keep the ciphertext already stored under
        this key", the only way a client can preserve a value it never sees.

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
        updates: dict[str, str | dict[str, str] | None] = {}

        provided_vault = [
            field for field in _VAULT_FIELDS if getattr(data, field) is not None
        ]
        if effective_type is SecretType.local:
            if provided_vault:
                raise SecretValidationError("A local secret must not set Vault fields")
            if data.entries is not None:
                updates["entries"] = self._merge_entries(data.entries, existing)
            elif existing.type is not SecretType.local:
                raise SecretValidationError(
                    "Switching to a local secret requires at least one entry"
                )
            if existing.type is not SecretType.local:
                updates.update(dict.fromkeys(_VAULT_FIELDS))
        else:
            if data.entries:
                raise SecretValidationError("A vault secret must not set entries")
            for field in _VAULT_FIELDS:
                effective = getattr(data, field) or (
                    getattr(existing, field)
                    if existing.type is SecretType.vault
                    else None
                )
                if effective is None:
                    raise SecretValidationError(
                        "A vault secret requires vaultMount and vaultPath"
                    )
            if existing.type is not SecretType.vault:
                updates["entries"] = {}

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

    def _merge_entries(
        self, submitted: dict[str, str], existing: Secret
    ) -> dict[str, str]:
        """Build the replacement entry map, encrypting every new value.

        Args:
            submitted: The plaintext map from the PATCH body, where an empty
                value means "keep the stored ciphertext for this key".
            existing: The stored secret supplying those retained ciphertexts.

        Returns:
            The full replacement map of key to ciphertext.

        Raises:
            SecretValidationError: If the result would be empty, or a key with
                an empty value has no stored ciphertext to keep.
        """
        if not submitted:
            raise SecretValidationError("A local secret requires at least one entry")
        stored = existing.entries if existing.type is SecretType.local else {}
        merged: dict[str, str] = {}
        for key, value in submitted.items():
            if value == "":
                if key not in stored:
                    raise SecretValidationError("A new entry requires a value")
                merged[key] = stored[key]
            else:
                merged[key] = self._cipher.encrypt(value)
        return merged
