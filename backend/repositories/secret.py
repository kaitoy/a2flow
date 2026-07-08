"""Secret repository: Protocol interface and SQLModel-backed implementation."""

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.secret import Secret, SecretCreate, SecretUpdate
from repositories._integrity import is_foreign_key_error
from repositories.exceptions import (
    ForeignKeyViolationError,
    NotFoundError,
    ReferencedError,
    UniqueViolationError,
)
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort


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
    ) -> list[Secret]: ...

    async def create(self, data: SecretCreate, *, user_id: str) -> Secret: ...

    async def update(
        self, secret_id: str, data: SecretUpdate, *, user_id: str
    ) -> Secret: ...

    async def delete(self, secret_id: str) -> None: ...

    async def exists(self, secret_id: str) -> bool: ...


class SqlSecretRepository:
    """SQLModel-backed implementation of SecretRepository.

    ``create`` and ``update`` translate a unique-name violation into
    UniqueViolationError. Callers pass the ``value`` field already encrypted
    (see :class:`services.secret.SecretService`); this layer never sees
    plaintext.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Store the SQLModel session used for all operations."""
        self._db = session

    async def get(self, secret_id: str) -> Secret | None:
        """Return the Secret with the given ID, or ``None`` if missing."""
        return await self._db.get(Secret, secret_id)

    async def get_by_name(self, name: str) -> Secret | None:
        """Return the Secret with the given unique name, or ``None`` if missing."""
        result = await self._db.exec(select(Secret).where(Secret.name == name))
        return result.first()

    async def exists(self, secret_id: str) -> bool:
        """Return ``True`` if a Secret with the given ID exists."""
        return (await self._db.get(Secret, secret_id)) is not None

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[Secret]:
        """Return a page of Secrets, defaulting to ``created_at`` descending."""
        stmt = apply_filters(select(Secret), Secret, filters)
        stmt = apply_sort(stmt, Secret, sort, default=[col(Secret.created_at).desc()])
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def create(self, data: SecretCreate, *, user_id: str) -> Secret:
        """Create a new Secret, raising UniqueViolationError on duplicate name."""
        secret = Secret.model_validate(
            {**data.model_dump(), "created_by": user_id, "updated_by": user_id}
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
        secret = await self._db.get(Secret, secret_id)
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
        secret = await self._db.get(Secret, secret_id)
        if secret is None:
            raise NotFoundError("Secret", secret_id)
        await self._db.delete(secret)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            raise ReferencedError("Secret is referenced by other records") from e
