"""Bootstrap helpers that seed required baseline records on application startup."""

import os
import secrets

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.password import hash_password
from models.user import SYSTEM_USER_ID, User

#: Fallback password for the seeded ``admin`` user when ``ADMIN_PASSWORD`` is
#: unset. Twelve characters to satisfy the model's minimum password length.
DEFAULT_ADMIN_PASSWORD = "admin12345678"


async def seed_system_user(session: AsyncSession) -> None:
    """Insert the system user if it does not already exist.

    The system user owns the bootstrap records as their ``created_by`` /
    ``updated_by`` — including itself, via a self-referential foreign key. It is
    hidden from the user list and cannot log in (its password hash matches no
    input). The first real user is created with ``X-User-Id`` set to
    :data:`SYSTEM_USER_ID`.

    Args:
        session: Database session used to read and insert the user.
    """
    if await session.get(User, SYSTEM_USER_ID) is not None:
        return
    system = User(
        id=SYSTEM_USER_ID,
        username="system",
        first_name="System",
        last_name="User",
        password=hash_password(secrets.token_urlsafe(32)),
        email="system@localhost",
        enabled=False,
        email_verified=False,
        created_by=SYSTEM_USER_ID,
        updated_by=SYSTEM_USER_ID,
    )
    session.add(system)
    await session.commit()


async def seed_admin_user(session: AsyncSession) -> None:
    """Create the initial ``admin`` user on first bootstrap.

    Skipped when any real (non-system) user already exists, so it runs only on
    the very first startup. The password is read from the ``ADMIN_PASSWORD``
    environment variable, falling back to :data:`DEFAULT_ADMIN_PASSWORD` when
    unset. The user is created with ``created_by`` / ``updated_by`` pointing at
    the seeded system user (:data:`SYSTEM_USER_ID`); its own ``id`` is an
    auto-generated UUID7.

    Args:
        session: Database session used to read and insert the user.
    """
    stmt = select(User).where(col(User.id) != SYSTEM_USER_ID).limit(1)
    if (await session.exec(stmt)).first() is not None:
        return
    password = os.getenv("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
    admin = User(
        username="admin",
        first_name="Admin",
        last_name="User",
        password=hash_password(password),
        email="admin@localhost",
        enabled=True,
        email_verified=False,
        created_by=SYSTEM_USER_ID,
        updated_by=SYSTEM_USER_ID,
    )
    session.add(admin)
    await session.commit()
