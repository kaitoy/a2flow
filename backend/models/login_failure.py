"""Failed sign-in attempt model, the store behind login throttling.

Each :class:`LoginFailure` row records one rejected login against the
submitted account's throttle key, ``<tenant name>/<username>``, so every
backend replica counts the same recent failures. Rows older than the throttle window
are pruned whenever a new failure is recorded.

Like :class:`~models.auth_session.AuthSession`, this model does **not**
inherit :class:`~models.base.BaseEntity`: the attempts are anonymous by
definition, so there is no user to attribute them to.
"""

from datetime import UTC, datetime

import uuid_utils
from sqlalchemy import Index
from sqlmodel import Field, SQLModel

from models.base import TZDateTime


class LoginFailure(SQLModel, table=True):
    """One failed login attempt counted against a throttle key."""

    __tablename__ = "login_failures"
    __table_args__ = (Index("ix_login_failures_key_failed_at", "key", "failed_at"),)

    id: str = Field(
        default_factory=lambda: str(uuid_utils.uuid7()),
        primary_key=True,
    )
    key: str
    failed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TZDateTime,
    )
