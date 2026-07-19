"""User repository: Protocol interface and SQLModel-backed implementation."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.user import SYSTEM_USER_ID, User, UserCreate, UserUpdate
from repositories._integrity import is_foreign_key_error
from repositories.exceptions import (
    ForeignKeyViolationError,
    NotFoundError,
    UniqueViolationError,
)
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort


class UserRepository(Protocol):
    """Interface for User persistence operations."""

    async def get(self, user_id: str) -> User | None: ...

    async def get_by_username(
        self, username: str, *, tenant_id: str | None
    ) -> User | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[User]: ...

    async def create(self, data: UserCreate, *, user_id: str) -> User: ...

    async def update(
        self, target_id: str, data: UserUpdate, *, user_id: str
    ) -> User: ...

    async def delete(self, user_id: str) -> None: ...

    async def exists(self, user_id: str) -> bool: ...


class SqlUserRepository:
    """SQLModel-backed implementation of UserRepository.

    ``create`` and ``update`` catch IntegrityError on the ``username`` unique
    constraint and re-raise it as :class:`UniqueViolationError`. Passwords are
    expected to be already hashed by the service layer before reaching here.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def get(self, user_id: str) -> User | None:
        return await self._db.get(User, user_id)

    async def get_by_username(
        self, username: str, *, tenant_id: str | None
    ) -> User | None:
        """Return the user with the given username scoped to ``tenant_id``.

        ``tenant_id=None`` matches only platform-scoped users (``tenant_id IS
        NULL`` -- the seeded system user, ``root``, or any other
        super_admin); a non-``None`` value matches only users belonging to
        that tenant. This mirrors the two-tier uniqueness enforced by
        ``uq_users_tenant_id_username`` and the partial unique index on
        ``username`` where ``tenant_id IS NULL`` (see :class:`~models.user.User`).

        Soft-deleted users are included so the auth layer can reject a login
        with an explicit "disabled" decision rather than silently missing them.

        Args:
            username: The username to look up.
            tenant_id: The tenant to scope the lookup to, or ``None`` for a
                platform-scoped user.

        Returns:
            The matching ``User`` or ``None``.
        """
        tenant_filter = (
            col(User.tenant_id).is_(None)
            if tenant_id is None
            else col(User.tenant_id) == tenant_id
        )
        stmt = select(User).where(col(User.username) == username, tenant_filter)
        return (await self._db.exec(stmt)).first()

    async def exists(self, user_id: str) -> bool:
        return (await self._db.get(User, user_id)) is not None

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[User]:
        stmt = (
            select(User)
            .where(col(User.deleted_at).is_(None))
            .where(col(User.id) != SYSTEM_USER_ID)
        )
        stmt = apply_filters(stmt, User, filters)
        stmt = apply_sort(stmt, User, sort, default=[col(User.created_at).desc()])
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def create(self, data: UserCreate, *, user_id: str) -> User:
        user = User.model_validate(
            {**data.model_dump(), "created_by": user_id, "updated_by": user_id}
        )
        self._db.add(user)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_foreign_key_error(e):
                raise ForeignKeyViolationError("User", user_id) from e
            raise UniqueViolationError("User", "username", data.username) from e
        await self._db.refresh(user)
        return user

    async def update(self, target_id: str, data: UserUpdate, *, user_id: str) -> User:
        user = await self._db.get(User, target_id)
        if user is None:
            raise NotFoundError("User", target_id)
        update = data.model_dump(exclude_unset=True)
        user.sqlmodel_update(update)
        user.updated_by = user_id
        self._db.add(user)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_foreign_key_error(e):
                raise ForeignKeyViolationError("User", user_id) from e
            raise UniqueViolationError(
                "User", "username", str(update.get("username", ""))
            ) from e
        await self._db.refresh(user)
        return user

    async def delete(self, user_id: str) -> None:
        """Delete a user, falling back to a soft delete when still referenced.

        A hard delete is attempted first. If the user is referenced by other
        records through ``created_by`` / ``updated_by`` (``ondelete=RESTRICT``),
        the database raises an IntegrityError; the user is then soft-deleted by
        setting ``deleted_at`` and disabling the account, so existing references
        stay valid and the name can still be resolved.

        Args:
            user_id: Identifier of the user to delete.

        Raises:
            NotFoundError: If no user exists with the given ID.
        """
        user = await self._db.get(User, user_id)
        if user is None:
            raise NotFoundError("User", user_id)
        try:
            await self._db.delete(user)
            await self._db.commit()
        except IntegrityError:
            await self._db.rollback()
            user = await self._db.get(User, user_id)
            if user is None:
                raise NotFoundError("User", user_id) from None
            user.deleted_at = datetime.now(UTC)
            user.enabled = False
            self._db.add(user)
            await self._db.commit()
