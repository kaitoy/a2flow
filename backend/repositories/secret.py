"""Secret repository: Protocol interface and SQLModel-backed implementation."""

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.secret import Secret, SecretCreate, SecretRead, SecretUpdate
from models.tag import SecretTag
from repositories._integrity import is_foreign_key_error
from repositories.exceptions import (
    ForeignKeyViolationError,
    NotFoundError,
    ReferencedError,
    UniqueViolationError,
)
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort
from repositories.tags import TagLinks

#: Alias for ``list[str]``: the ``list`` method below shadows the builtin
#: inside every class body in this module.
_StrList = list[str]


class SecretRepository(Protocol):
    """Interface for Secret persistence operations."""

    async def get(self, secret_id: str) -> Secret | None: ...

    async def get_by_name(self, name: str) -> Secret | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
        tag_ids: Sequence[str] = (),
    ) -> list[Secret]: ...

    async def create(self, data: SecretCreate, *, user_id: str) -> Secret: ...

    async def update(
        self, secret_id: str, data: SecretUpdate, *, user_id: str
    ) -> Secret: ...

    async def delete(self, secret_id: str) -> None: ...

    async def exists(self, secret_id: str) -> bool: ...

    async def tag_ids_for(self, secret_id: str) -> _StrList: ...

    async def tag_ids_for_many(
        self, secret_ids: Sequence[str]
    ) -> dict[str, _StrList]: ...

    async def set_tags(self, secret_id: str, tag_ids: Sequence[str]) -> Secret: ...


class SqlSecretRepository:
    """SQLModel-backed implementation of SecretRepository.

    ``create`` and ``update`` translate a unique-name violation into
    UniqueViolationError. Callers pass the ``value`` field already encrypted
    (see :class:`services.secret.SecretService`); this layer never sees
    plaintext.
    """

    def __init__(self, session: AsyncSession, *, tenant_id: str) -> None:
        """Store the SQLModel session and the tenant these operations are scoped to."""
        self._db = session
        self._tenant_id = tenant_id
        self._tags = TagLinks(session, SecretTag, tenant_id=tenant_id)

    async def _get_scoped(self, secret_id: str) -> Secret | None:
        """Return the Secret with the given ID within the current tenant, or ``None``."""
        stmt = select(Secret).where(
            Secret.id == secret_id, Secret.tenant_id == self._tenant_id
        )
        result = await self._db.exec(stmt)
        return result.first()

    async def get(self, secret_id: str) -> Secret | None:
        """Return the Secret with the given ID, or ``None`` if missing."""
        return await self._get_scoped(secret_id)

    async def get_by_name(self, name: str) -> Secret | None:
        """Return the Secret with the given unique name, or ``None`` if missing."""
        stmt = select(Secret).where(
            Secret.name == name, Secret.tenant_id == self._tenant_id
        )
        result = await self._db.exec(stmt)
        return result.first()

    async def exists(self, secret_id: str) -> bool:
        """Return ``True`` if a Secret with the given ID exists."""
        return await self._get_scoped(secret_id) is not None

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
        tag_ids: Sequence[str] = (),
    ) -> list[Secret]:
        """Return a page of Secrets, defaulting to ``created_at`` descending.

        ``tag_ids`` narrows the page to secrets carrying **every** listed tag.
        It is applied before the page window, so paging stays consistent with
        the filter.
        """
        stmt = select(Secret).where(Secret.tenant_id == self._tenant_id)
        for clause in self._tags.filter_clauses(col(Secret.id), tag_ids):
            stmt = stmt.where(clause)
        stmt = apply_filters(stmt, Secret, filters, readable=SecretRead)
        stmt = apply_sort(
            stmt,
            Secret,
            sort,
            default=[col(Secret.created_at).desc()],
            readable=SecretRead,
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def create(self, data: SecretCreate, *, user_id: str) -> Secret:
        """Create a new Secret, raising UniqueViolationError on duplicate name."""
        secret = Secret.model_validate(
            {
                **data.model_dump(),
                "tenant_id": self._tenant_id,
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        self._db.add(secret)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_foreign_key_error(e):
                raise ForeignKeyViolationError("User", user_id) from e
            raise UniqueViolationError("Secret", "name", data.name) from e
        await self._db.refresh(secret)
        return secret

    async def update(
        self, secret_id: str, data: SecretUpdate, *, user_id: str
    ) -> Secret:
        """Apply a partial update, raising NotFoundError or UniqueViolationError."""
        secret = await self._get_scoped(secret_id)
        if secret is None:
            raise NotFoundError("Secret", secret_id)
        update = data.model_dump(exclude_unset=True)
        secret.sqlmodel_update(update)
        secret.updated_by = user_id
        self._db.add(secret)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_foreign_key_error(e):
                raise ForeignKeyViolationError("User", user_id) from e
            raise UniqueViolationError(
                "Secret", "name", str(update.get("name", ""))
            ) from e
        await self._db.refresh(secret)
        return secret

    async def delete(self, secret_id: str) -> None:
        """Delete the Secret, raising NotFoundError when missing.

        Header placeholders and skill references point at secrets by name, not
        by foreign key, so deletion never raises ReferencedError; a dangling
        reference instead fails lazily at resolution time.
        """
        secret = await self._get_scoped(secret_id)
        if secret is None:
            raise NotFoundError("Secret", secret_id)
        await self._db.delete(secret)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            raise ReferencedError("Secret is referenced by other records") from e

    async def tag_ids_for(self, secret_id: str) -> _StrList:
        """Return the sorted ids of the tags attached to one Secret."""
        return await self._tags.for_one(secret_id)

    async def tag_ids_for_many(self, secret_ids: Sequence[str]) -> dict[str, _StrList]:
        """Return each Secret's sorted tag ids, in one query."""
        return await self._tags.for_many(secret_ids)

    async def set_tags(self, secret_id: str, tag_ids: Sequence[str]) -> Secret:
        """Replace a Secret's tag attachments wholesale.

        Args:
            secret_id: Id of the secret to retag.
            tag_ids: Ids of the tags it should carry; an empty sequence
                detaches every tag.

        Returns:
            The secret, unchanged apart from its attachments.

        Raises:
            NotFoundError: If the secret does not exist in this tenant.
            ForeignKeyViolationError: If any id does not name a tag of this
                tenant.
        """
        secret = await self._get_scoped(secret_id)
        if secret is None:
            raise NotFoundError("Secret", secret_id)
        await self._tags.validate(tag_ids)
        await self._tags.replace(secret_id, tag_ids)
        await self._db.commit()
        await self._db.refresh(secret)
        return secret
