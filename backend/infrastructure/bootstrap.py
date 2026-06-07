"""Bootstrap helpers that seed required baseline records on application startup."""

import secrets

from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.password import hash_password
from models.user import SYSTEM_USER_ID, User


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
