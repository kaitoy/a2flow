"""Bootstrap helpers that seed required baseline records on application startup."""

import logging
import os
import secrets

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.password import hash_password
from models.user import SYSTEM_USER_ID, User

logger = logging.getLogger(__name__)

#: Bytes of entropy for the admin password generated when ``ADMIN_PASSWORD`` is
#: unset. ``token_urlsafe`` renders ~1.3 chars/byte, so 16 bytes yields a
#: ~22-character password: comfortably above the model's 12-character minimum
#: and short enough to copy out of a log line.
_GENERATED_ADMIN_PASSWORD_BYTES = 16


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
    environment variable; if unset (or empty), a random password is generated
    and logged once at ``WARNING`` level, since it cannot be recovered
    afterwards. The user is created with ``created_by`` / ``updated_by``
    pointing at the seeded system user (:data:`SYSTEM_USER_ID`); its own ``id``
    is an auto-generated UUID7.

    Args:
        session: Database session used to read and insert the user.
    """
    stmt = select(User).where(col(User.id) != SYSTEM_USER_ID).limit(1)
    if (await session.exec(stmt)).first() is not None:
        return
    password = os.getenv("ADMIN_PASSWORD")
    if not password:
        password = secrets.token_urlsafe(_GENERATED_ADMIN_PASSWORD_BYTES)
        logger.warning(
            "ADMIN_PASSWORD not set; generated a random password for the "
            "'admin' user. This is logged once and cannot be recovered "
            "afterwards - copy it now, then change it after logging in: %s",
            password,
        )
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
