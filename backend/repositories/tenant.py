"""Tenant repository: Protocol interface and SQLModel-backed implementation."""

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.system_settings import SystemSettings
from models.tenant import (
    AdminSettingsUpdate,
    LlmMode,
    Tenant,
    TenantCreate,
    TenantRead,
    TenantUpdate,
)
from repositories._integrity import is_foreign_key_error, is_unique_error
from repositories.exceptions import (
    ForeignKeyViolationError,
    NotFoundError,
    ReferencedError,
    UniqueViolationError,
)
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort


class TenantRepository(Protocol):
    """Interface for Tenant persistence operations."""

    async def get(self, tenant_id: str) -> Tenant | None: ...

    async def get_by_name(self, name: str) -> Tenant | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[Tenant]: ...

    async def create(
        self, data: TenantCreate, *, user_id: str, data_key: str | None = None
    ) -> Tenant: ...

    async def update(
        self,
        tenant_id: str,
        data: TenantUpdate | AdminSettingsUpdate,
        *,
        user_id: str,
    ) -> Tenant: ...

    async def delete(self, tenant_id: str) -> None: ...

    async def exists(self, tenant_id: str) -> bool: ...

    async def at_capacity(self) -> bool: ...

    async def default_llm_mode(self) -> LlmMode: ...


class SqlTenantRepository:
    """SQLModel-backed implementation of TenantRepository.

    ``create`` and ``update`` catch IntegrityError on the
    ``display_name``/``name`` unique constraints and re-raise as
    :class:`UniqueViolationError`. ``delete`` catches IntegrityError raised
    by ``users.tenant_id``'s ``ondelete=RESTRICT`` foreign key and re-raises
    as :class:`ReferencedError`.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def get(self, tenant_id: str) -> Tenant | None:
        return await self._db.get(Tenant, tenant_id)

    async def exists(self, tenant_id: str) -> bool:
        return (await self._db.get(Tenant, tenant_id)) is not None

    async def at_capacity(self) -> bool:
        """Return whether the deployment already holds its maximum number of tenants.

        Compares every row of ``tenants`` (disabled ones included) with
        ``system_settings.max_tenants``. No limit set, or no settings row yet,
        means there is room.

        Returns:
            ``True`` if no further tenant may be created.
        """
        limit = (await self._db.exec(select(SystemSettings.max_tenants))).first()
        if limit is None:
            return False
        count = (await self._db.exec(select(func.count()).select_from(Tenant))).one()
        return count >= limit

    async def default_llm_mode(self) -> LlmMode:
        """Return who sets the LLM of a tenant created without saying so.

        Reads ``system_settings.default_tenant_llm_mode``. No settings row yet
        means the LLM stays on the system's.

        Returns:
            The mode a new tenant starts with.
        """
        mode = (
            await self._db.exec(select(SystemSettings.default_tenant_llm_mode))
        ).first()
        return LlmMode.system_default if mode is None else LlmMode(mode)

    async def get_by_name(self, name: str) -> Tenant | None:
        """Return the tenant with the given name, or ``None`` if no match exists.

        Used by :meth:`services.auth.AuthService.login` to resolve a submitted
        tenant name into a ``tenant_id`` before looking up the user, without
        exposing a public tenant-lookup endpoint.

        Args:
            name: The tenant's unique URL-safe name.

        Returns:
            The matching ``Tenant`` or ``None``.
        """
        stmt = select(Tenant).where(col(Tenant.name) == name)
        return (await self._db.exec(stmt)).first()

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[Tenant]:
        stmt = select(Tenant)
        stmt = apply_filters(stmt, Tenant, filters, readable=TenantRead)
        stmt = apply_sort(
            stmt,
            Tenant,
            sort,
            default=[col(Tenant.created_at).desc()],
            readable=TenantRead,
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def create(
        self, data: TenantCreate, *, user_id: str, data_key: str | None = None
    ) -> Tenant:
        """Insert a tenant.

        Args:
            data: Fields of the new tenant.
            user_id: Identifier of the acting user, recorded as the creator.
            data_key: The tenant's wrapped data key, when the caller already
                encrypted credentials in ``data`` with it; a fresh one is
                generated otherwise.

        Returns:
            The created tenant.

        Raises:
            ForeignKeyViolationError: If ``user_id`` names no user.
            UniqueViolationError: If the name or display name is taken.
        """
        extra = {"data_key": data_key} if data_key else {}
        tenant = Tenant.model_validate(
            {**data.model_dump(), "created_by": user_id, "updated_by": user_id, **extra}
        )
        self._db.add(tenant)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_foreign_key_error(e):
                raise ForeignKeyViolationError("User", user_id) from e
            field = (
                "name"
                if is_unique_error(e) and "uq_tenants_name" in str(e.orig)
                else "display_name"
            )
            raise UniqueViolationError("Tenant", field, getattr(data, field)) from e
        await self._db.refresh(tenant)
        return tenant

    async def update(
        self,
        tenant_id: str,
        data: TenantUpdate | AdminSettingsUpdate,
        *,
        user_id: str,
    ) -> Tenant:
        tenant = await self._db.get(Tenant, tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant", tenant_id)
        update = data.model_dump(exclude_unset=True)
        tenant.sqlmodel_update(update)
        tenant.updated_by = user_id
        self._db.add(tenant)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_foreign_key_error(e):
                raise ForeignKeyViolationError("User", user_id) from e
            field = (
                "name"
                if is_unique_error(e) and "uq_tenants_name" in str(e.orig)
                else "display_name"
            )
            raise UniqueViolationError(
                "Tenant", field, str(update.get(field, ""))
            ) from e
        await self._db.refresh(tenant)
        return tenant

    async def delete(self, tenant_id: str) -> None:
        """Delete a tenant, raising ReferencedError while users remain assigned to it."""
        tenant = await self._db.get(Tenant, tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant", tenant_id)
        await self._db.delete(tenant)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            raise ReferencedError("Tenant is referenced by one or more users") from e
