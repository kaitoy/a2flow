"""Helpers for classifying and translating database ``IntegrityError`` causes.

Both SQLite and PostgreSQL report constraint failures through a single
``IntegrityError`` whose message text identifies the kind of constraint that
failed (each dialect with its own wording). These helpers inspect that text so
repositories can translate low-level database errors into the domain
exceptions in :mod:`repositories.exceptions`.
"""

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from repositories.exceptions import ForeignKeyViolationError

_FK_MARKERS = (
    "FOREIGN KEY constraint failed",  # SQLite
    "violates foreign key constraint",  # PostgreSQL
)
_UNIQUE_MARKERS = (
    "UNIQUE constraint failed",  # SQLite
    "duplicate key value violates unique constraint",  # PostgreSQL
)


def is_foreign_key_error(error: IntegrityError) -> bool:
    """Return ``True`` if the error was caused by a foreign-key violation.

    Args:
        error: The IntegrityError raised on commit.

    Returns:
        ``True`` when the underlying SQLite or PostgreSQL message reports a
        failed foreign key.
    """
    message = str(error.orig)
    return any(marker in message for marker in _FK_MARKERS)


def is_unique_error(error: IntegrityError) -> bool:
    """Return ``True`` if the error was caused by a unique-constraint violation.

    Args:
        error: The IntegrityError raised on commit.

    Returns:
        ``True`` when the underlying SQLite or PostgreSQL message reports a
        failed unique constraint.
    """
    message = str(error.orig)
    return any(marker in message for marker in _UNIQUE_MARKERS)


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
