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
from pydantic import field_serializer
from pydantic.alias_generators import to_camel
from sqlalchemy import ForeignKeyConstraint, Index
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import TZDateTime, iso_z, iso_z_or_none


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


class ImpersonationEventRead(SQLModel):
    """Read view of one impersonation session, returned by the admin audit API.

    The table class above is deliberately not the response model, unlike most
    read-only entities here. It inherits plain :class:`~sqlmodel.SQLModel`
    rather than :class:`~models.base.BaseEntity`, so it carries neither the
    camelCase alias generator every other payload uses nor the ``Z``-suffixed
    datetime serialization the generated frontend Zod schemas require. This
    schema supplies both.

    ``target_tenant_id`` is the one field with no column behind it: it is filled
    from the join :meth:`repositories.impersonation_event.SqlImpersonationEventRepository.list`
    already performs to scope rows by tenant, so an all-tenants listing can label
    which tenant each session touched. Because it is absent from the table class,
    :func:`repositories.query._resolve_column` will not resolve it -- filtering
    and sorting stay on the real columns, which is the intended behavior.
    """

    model_config = SQLModelConfig(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: str
    impersonator_id: str
    target_user_id: str
    started_at: datetime
    ended_at: datetime | None = None
    #: Tenant of the impersonated user, resolved through the join. ``None`` when
    #: the target is platform-scoped (a super admin or the seeded system user).
    target_tenant_id: str | None = None

    @field_serializer("started_at", when_used="json")
    def _serialize_started_at(self, dt: datetime) -> str:
        """Serialize the start instant as ISO-8601 with a ``Z`` suffix."""
        return iso_z(dt)

    @field_serializer("ended_at", when_used="json")
    def _serialize_ended_at(self, dt: datetime | None) -> str | None:
        """Serialize the end instant, passing ``None`` through for an open session."""
        return iso_z_or_none(dt)
