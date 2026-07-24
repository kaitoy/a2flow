"""Audit trail of impersonation sessions.

An :class:`ImpersonationEvent` row records one admin/super_admin acting as
another user, from the moment they start until they stop (or the target
becomes ineligible mid-session and the request layer auto-closes it). Unlike
:class:`~models.auth_session.AuthSession`, this table's whole purpose *is* to
be a durable audit record, so its user foreign keys use ``ondelete=RESTRICT``
rather than ``CASCADE`` -- hard-deleting a user who appears in one falls back
to the existing soft-delete path in ``SqlUserRepository.delete``, the same as
any other ``RESTRICT`` reference to ``users.id``.
"""

from datetime import UTC, datetime

import uuid_utils
from sqlalchemy import ForeignKeyConstraint, Index
from sqlmodel import Field, SQLModel

from models.base import TZDateTime


class ImpersonationEvent(SQLModel, table=True):
    """One impersonation session: an actor acting as a target user."""

    __tablename__ = "impersonation_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["impersonator_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_impersonation_events_impersonator_id",
        ),
        ForeignKeyConstraint(
            ["target_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_impersonation_events_target_user_id",
        ),
        Index(
            "ix_impersonation_events_impersonator_id_ended_at",
            "impersonator_id",
            "ended_at",
        ),
        Index("ix_impersonation_events_target_user_id", "target_user_id"),
    )

    id: str = Field(
        default_factory=lambda: str(uuid_utils.uuid7()),
        primary_key=True,
    )
    impersonator_id: str
    target_user_id: str
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=TZDateTime,
    )
    ended_at: datetime | None = Field(default=None, sa_type=TZDateTime)
