"""SystemSettings repository: Protocol interface and SQLModel-backed implementation.

Not tenant-scoped, for the same reason :mod:`repositories.tenant` isn't: the
settings apply to the whole platform, so there is no tenant to filter by. The
row is a singleton pinned to :data:`~models.system_settings.SYSTEM_SETTINGS_ID`
and seeded at startup by :func:`infrastructure.bootstrap.seed_system_settings`,
so there is no ``create`` here — only ``get`` and ``update``.
"""

from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from models.system_settings import (
    SYSTEM_SETTINGS_ID,
    SystemSettings,
    SystemSettingsUpdate,
)
from repositories._integrity import is_foreign_key_error
from repositories.exceptions import ForeignKeyViolationError, NotFoundError


class SystemSettingsRepository(Protocol):
    """Interface for the singleton SystemSettings row."""

    async def get(self) -> SystemSettings | None: ...

    async def update(
        self, data: SystemSettingsUpdate, *, user_id: str
    ) -> SystemSettings: ...


class SqlSystemSettingsRepository:
    """SQLModel-backed implementation of SystemSettingsRepository.

    ``update`` applies only the fields the caller actually set and stamps
    ``updated_by`` from the acting user, per the audit-field convention: the
    repository is the only layer that writes those columns.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: The request-scoped (or job-scoped) database session.
        """
        self._db = session

    async def get(self) -> SystemSettings | None:
        """Return the settings row, or ``None`` if it has not been seeded yet."""
        return await self._db.get(SystemSettings, SYSTEM_SETTINGS_ID)

    async def update(
        self, data: SystemSettingsUpdate, *, user_id: str
    ) -> SystemSettings:
        """Apply a partial update to the settings row.

        Args:
            data: Fields to apply; unset fields are left untouched.
            user_id: The acting user, recorded as ``updated_by``.

        Returns:
            The updated settings row.

        Raises:
            NotFoundError: If the settings row has not been seeded.
            ForeignKeyViolationError: If ``user_id`` does not name a real user.
        """
        settings = await self._db.get(SystemSettings, SYSTEM_SETTINGS_ID)
        if settings is None:
            raise NotFoundError("SystemSettings", SYSTEM_SETTINGS_ID)
        settings.sqlmodel_update(data.model_dump(exclude_unset=True))
        settings.updated_by = user_id
        self._db.add(settings)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_foreign_key_error(e):
                raise ForeignKeyViolationError("User", user_id) from e
            raise
        await self._db.refresh(settings)
        return settings
