"""Helpers for classifying and translating SQLite ``IntegrityError`` causes.

SQLite reports constraint failures through a single ``IntegrityError`` whose
message text identifies the kind of constraint that failed. These helpers inspect
that text so repositories can translate low-level database errors into the
domain exceptions in :mod:`repositories.exceptions`.
"""

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from repositories.exceptions import ForeignKeyViolationError


def is_foreign_key_error(error: IntegrityError) -> bool:
    """Return ``True`` if the error was caused by a foreign-key violation.

    Args:
        error: The IntegrityError raised on commit.

    Returns:
        ``True`` when the underlying SQLite message reports a failed foreign key.
    """
    return "FOREIGN KEY constraint failed" in str(error.orig)


def is_unique_error(error: IntegrityError) -> bool:
    """Return ``True`` if the error was caused by a unique-constraint violation.

    Args:
        error: The IntegrityError raised on commit.

    Returns:
        ``True`` when the underlying SQLite message reports a failed unique constraint.
    """
    return "UNIQUE constraint failed" in str(error.orig)


async def commit_or_translate_user_fk(session: AsyncSession, *, user_id: str) -> None:
    """Commit, translating a ``created_by`` / ``updated_by`` foreign-key violation.

    When the acting ``user_id`` does not reference an existing user, the
    ``created_by`` / ``updated_by`` foreign key fails and the commit is rolled
    back and re-raised as :class:`ForeignKeyViolationError`. Any other
    IntegrityError is rolled back and re-raised unchanged so callers can handle
    their own constraints (e.g. unique names).

    Args:
        session: The session to commit.
        user_id: The acting user id recorded in ``created_by`` / ``updated_by``.

    Raises:
        ForeignKeyViolationError: If the acting user does not exist.
    """
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if is_foreign_key_error(e):
            raise ForeignKeyViolationError("User", user_id) from e
        raise
