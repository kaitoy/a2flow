"""Pending sign-up model: a sign-up form waiting for its email to be confirmed.

Self-service sign-up (``services/signup.py``) does not create anything when the
form is submitted. It stores the form here, with the password already hashed,
and mails a link carrying a random token; only the hash of that token is
stored. Opening the link and confirming turns the row into a tenant and its
admin, and deletes it. Rows whose link has expired are pruned on the next
sign-up.

Like :class:`~models.login_failure.LoginFailure`, this model does **not**
inherit :class:`~models.base.BaseEntity`: the visitor has no account yet, so
there is no user to attribute it to, and it never belongs to a tenant.
"""

from datetime import UTC, datetime

import uuid_utils
from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from models.base import TZDateTime


class PendingSignup(SQLModel, table=True):
    """A submitted sign-up form, kept until its confirmation link is used or expires."""

    __tablename__ = "pending_signups"
    __table_args__ = (
        # The per-address throttle looks up the newest request for an email.
        Index("ix_pending_signups_email_created_at", "email", "created_at"),
        UniqueConstraint("token_hash", name="uq_pending_signups_token_hash"),
    )

    id: str = Field(
        default_factory=lambda: str(uuid_utils.uuid7()),
        primary_key=True,
    )
    email: str
    username: str
    first_name: str
    last_name: str
    #: The bcrypt hash of the chosen password, copied to the user on completion.
    password: str
    #: SHA-256 of the token mailed in the confirmation link.
    token_hash: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TZDateTime,
    )
    expires_at: datetime = Field(sa_type=TZDateTime)
