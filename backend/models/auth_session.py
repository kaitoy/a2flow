"""Server-side login session model.

An :class:`AuthSession` row backs one logged-in browser. The session cookie
carries a random opaque token whose SHA-256 hash is stored in ``token_hash``;
the row is looked up by that hash. ``csrf_token`` holds the double-submit CSRF
value handed to the client in a readable cookie. ``last_active_at`` drives the
sliding idle-timeout: each authenticated request refreshes it, and a session
whose idle window has elapsed is treated as expired.

This model deliberately does **not** inherit :class:`~models.base.BaseEntity`:
auth sessions are not audited domain records and they exist precisely to
establish the identity that the audit foreign keys would reference.
"""

from datetime import UTC, datetime

import uuid_utils
from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from models.base import TZDateTime


class AuthSession(SQLModel, table=True):
    """Database-persisted login session keyed by a hashed cookie token."""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
        Index("ix_auth_sessions_token_hash", "token_hash"),
    )

    id: str = Field(
        default_factory=lambda: str(uuid_utils.uuid7()),
        primary_key=True,
    )
    token_hash: str
    csrf_token: str
    user_id: str = Field(foreign_key="users.id", ondelete="CASCADE")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TZDateTime,
    )
    last_active_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TZDateTime,
    )
