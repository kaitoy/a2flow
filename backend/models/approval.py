"""Approval data models for create, update, read, and database persistence.

An Approval is a human-in-the-loop decision the workflow agent asks for while
executing a workflow execution. The agent creates an Approval (in the ``pending``
state) via the ``request_approval`` tool, the GUI surfaces it to the approver,
and the approver resolves it to ``approved``, ``rejected``, or ``returned``. The
agent then continues or aborts the task based on the recorded decision.

``workflow_execution_id`` links the approval to the workflow execution it belongs to
(so the GUI can deep-link to the session chat); the optional ``workflow_task_id``
ties it to the specific task that needs approval. The optional ``approver`` is
the user the agent addresses the request to (the request's destination), set when
the agent creates the approval. ``response`` records an optional free-text comment
supplied when the approver resolves the request.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import field_serializer
from pydantic.alias_generators import to_camel
from sqlalchemy import ForeignKeyConstraint, Index
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, TZDateTime, iso_z_or_none
from models.constraints import BodyText, ShortText
from models.tenant_scoped import TenantScoped

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class ApprovalStatus(StrEnum):
    """Lifecycle states of an approval request.

    Every state other than :attr:`pending` is a *decision*: reaching one stamps
    :attr:`Approval.decided_at` (see
    :meth:`repositories.approval.SqlApprovalRepository.resolve`) and is what the
    approval-rate and approval-latency metrics count.
    """

    pending = "pending"
    """Awaiting the designated approver's decision."""

    approved = "approved"
    """The approver approved the request; the agent may continue."""

    rejected = "rejected"
    """The approver rejected the request outright; the agent should abort."""

    returned = "returned"
    """The approver sent the request back for rework rather than deciding it.

    Distinct from :attr:`rejected`: the work is expected to be revised and
    re-submitted, so a high ``returned`` rate points at an upstream quality
    problem rather than at work that should not have been requested at all.
    """


class ApprovalUpdate(SQLModel):
    """Partial update payload for an Approval.

    Used by the resolve endpoint (``PATCH /approvals/{id}``): the approver moves
    the request to ``approved``, ``rejected``, or ``returned`` and may attach a
    ``response`` comment. Both fields are optional so a caller can update either
    alone.

    ``decided_at`` is deliberately absent — it is stamped server-side on the
    transition out of ``pending`` (see :class:`Approval`), so a client cannot
    backdate a decision.
    """

    model_config = _alias_config
    status: ApprovalStatus | None = None
    response: BodyText | None = None


class ApprovalCreate(ApprovalUpdate):
    """Creation payload for an Approval.

    Adds the required ``workflow_execution_id`` and ``title``, the optional
    ``description``, ``workflow_task_id`` link, and ``approver`` (the user the
    request is addressed to), and defaults ``status`` to ``pending`` so a freshly
    requested approval starts unresolved.
    """

    workflow_execution_id: str
    title: ShortText
    description: BodyText | None = None
    workflow_task_id: str | None = None
    approver: str | None = None
    status: ApprovalStatus = ApprovalStatus.pending


class Approval(ApprovalCreate, TenantScoped, BaseEntity, table=True):
    """Database-persisted approval request.

    ``workflow_execution_id`` references the owning workflow execution
    (``ON DELETE CASCADE``), so deleting the session removes its approvals. The
    optional ``workflow_task_id`` references the task the approval concerns
    (``ON DELETE SET NULL``), so deleting the task leaves the approval record
    intact but unlinked. The optional ``approver`` references the user the request
    is addressed to (``ON DELETE RESTRICT``), matching the audit user FKs.

    ``decided_at`` is server-managed: it is declared on the table class only, so
    it is absent from ``ApprovalCreate`` / ``ApprovalUpdate`` and cannot be
    written through the API. It is stamped once, by
    :meth:`repositories.approval.SqlApprovalRepository.resolve`, when the status
    first leaves ``pending``. The generic ``update`` never touches it, so a
    later edit to the ``response`` comment cannot move the recorded decision
    time. Together with ``created_at`` it gives the approver's turnaround time —
    the basis of the pending-age and approval-rate metrics
    (``repositories/metrics.py``).
    """

    __tablename__ = "approvals"
    decided_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    __table_args__ = (
        Index("ix_approvals_workflow_execution_id", "workflow_execution_id"),
        Index("ix_approvals_workflow_task_id", "workflow_task_id"),
        Index("ix_approvals_approver", "approver"),
        Index("ix_approvals_tenant_id_status", "tenant_id", "status"),
        Index("ix_approvals_tenant_id_decided_at", "tenant_id", "decided_at"),
        ForeignKeyConstraint(
            ["workflow_execution_id"],
            ["workflow_executions.id"],
            ondelete="CASCADE",
            name="fk_approvals_workflow_execution_id",
        ),
        ForeignKeyConstraint(
            ["workflow_task_id"],
            ["workflow_tasks.id"],
            ondelete="SET NULL",
            name="fk_approvals_workflow_task_id",
        ),
        ForeignKeyConstraint(
            ["approver"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_approvals_approver",
        ),
    )

    @field_serializer("decided_at", when_used="json")
    def _serialize_decided_at(self, dt: datetime | None) -> str | None:
        """Serialize ``decided_at`` as ISO-8601 with a ``Z`` suffix, or ``None``.

        Args:
            dt: The decision timestamp, or ``None`` while still pending.

        Returns:
            The ISO-8601 string with a ``Z`` suffix, or ``None``.
        """
        return iso_z_or_none(dt)
