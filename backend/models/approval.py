"""Approval data models for create, update, read, and database persistence.

An Approval is a human-in-the-loop decision the workflow agent asks for while
executing a workflow execution. The agent creates an Approval (in the ``pending``
state) via the ``request_approval`` tool, the GUI surfaces it to the approver,
and the approver resolves it to ``approved``, ``rejected``, or ``returned``. The
agent then continues or aborts the task based on the recorded decision.

``workflow_execution_id`` links the approval to the workflow execution it belongs to
(so the GUI can deep-link to the session chat); the optional ``workflow_task_id``
ties it to the specific task that needs approval. ``response`` records an optional
free-text comment supplied when the approver resolves the request.

``workflow_task_id`` is optional only because the column has to survive its task
being deleted (``ON DELETE SET NULL``). Every approval an agent requests names
one, and it must name the task that *performs* the approved action rather than a
step that merely asks for the go-ahead: both the gate
(:class:`infrastructure.mcp_policies.ApprovedTaskCertificatePolicy`) and the
grant (:class:`services.approval_certificate.ApprovalCertificateService`) are
that task's. :func:`infrastructure.approval_tools.request_approval` requires the
argument and rejects the inverted shape.

**A request has exactly one destination**, expressed as one of two mutually
exclusive fields the agent sets when it creates the approval:

* ``approver`` -- a single user. Only that user may resolve the request.
* ``approver_group_id`` -- a :class:`~models.user_group.UserGroup`. **Any**
  member of that group whose *effective* roles include
  :attr:`~models.user.Role.approver` may resolve it, and the first such
  decision completes the request. This is what lets a team share an approval
  queue instead of blocking on one named person's availability.

``decided_by`` records which user actually made the decision -- for a group
destination that is not knowable from ``approver_group_id`` alone.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import field_serializer, model_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index
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
    ``description`` and ``workflow_task_id`` link, the request's destination,
    and defaults ``status`` to ``pending`` so a freshly requested approval
    starts unresolved.

    The destination is one of ``approver`` (a user) or ``approver_group_id`` (a
    user group), never both -- see the module docstring and
    :meth:`_reject_two_destinations`. That a destination is *required* is
    enforced by :func:`infrastructure.approval_tools.request_approval`, the only
    path that creates an approval, rather than here: :class:`Approval` inherits
    this schema, and FastAPI validates it on the way *out* too, so a rule
    rejecting "neither" would make any pre-existing destination-less row
    unreadable instead of merely uncreatable.
    """

    workflow_execution_id: str
    title: ShortText
    description: BodyText | None = None
    workflow_task_id: str | None = None
    #: Id of the single user the request is addressed to; mutually exclusive
    #: with :attr:`approver_group_id`.
    approver: str | None = None
    #: Id of the user group the request is addressed to; mutually exclusive
    #: with :attr:`approver`. Any member of the group holding the ``approver``
    #: role may resolve the request.
    approver_group_id: str | None = None
    status: ApprovalStatus = ApprovalStatus.pending

    @model_validator(mode="after")
    def _reject_two_destinations(self) -> "ApprovalCreate":
        """Reject a payload naming both a user and a group destination.

        Mirrors ``ck_approvals_single_destination`` exactly, so the schema and
        the table agree on what a valid row is. Deliberately does **not** also
        reject "neither": :class:`Approval` inherits this validator and FastAPI
        runs it when serializing a response, so the stricter rule would turn a
        legacy destination-less row from readable into an HTTP 500. "Exactly
        one" belongs to the creation path and lives in
        :func:`infrastructure.approval_tools.request_approval`, which can also
        say *which* tool to use to pick a destination.

        Returns:
            The payload unchanged when at most one destination is set.

        Raises:
            ValueError: If both destinations are set.
        """
        if self.approver is not None and self.approver_group_id is not None:
            raise ValueError(
                "An approval cannot name both approver and approverGroupId"
            )
        return self


class Approval(ApprovalCreate, TenantScoped, BaseEntity, table=True):
    """Database-persisted approval request.

    ``workflow_execution_id`` references the owning workflow execution
    (``ON DELETE CASCADE``), so deleting the session removes its approvals. The
    optional ``workflow_task_id`` references the task the approval concerns
    (``ON DELETE SET NULL``), so deleting the task leaves the approval record
    intact but unlinked. Both destination columns -- ``approver`` (a user) and
    ``approver_group_id`` (a user group) -- and ``decided_by`` use
    ``ON DELETE RESTRICT``, matching the audit user FKs: a destination that
    could vanish would leave an approval nobody can resolve.

    ``ck_approvals_single_destination`` enforces only that the two destinations
    are not *both* set. It is deliberately weaker than the ``XOR`` precedent at
    ``ck_message_meta_single_parent`` (:mod:`models.message_meta`), which also
    rejects rows with neither: ``approver`` has always been nullable, so
    approvals with no destination at all may already exist and must stay
    readable. "Exactly one" is enforced on the write path instead, by
    :meth:`ApprovalCreate._exactly_one_destination`.

    ``decided_at`` and ``decided_by`` are server-managed: they are declared on
    the table class only, so they are absent from ``ApprovalCreate`` /
    ``ApprovalUpdate`` and cannot be written through the API. Both are stamped
    once, by :meth:`repositories.approval.SqlApprovalRepository.resolve`, when
    the status first leaves ``pending``. The generic ``update`` never touches
    them, so a later edit to the ``response`` comment cannot move the recorded
    decision time or reassign the decision. ``decided_by`` answers "who
    decided", which for a group destination the record does not otherwise say.
    Together with ``created_at``, ``decided_at`` gives the turnaround time —
    the basis of the pending-age and approval-rate metrics
    (``repositories/metrics.py``).
    """

    __tablename__ = "approvals"
    decided_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    #: Id of the user who made the decision, stamped alongside ``decided_at``.
    #: ``None`` while the request is still ``pending``.
    decided_by: str | None = None
    __table_args__ = (
        Index("ix_approvals_workflow_execution_id", "workflow_execution_id"),
        Index("ix_approvals_workflow_task_id", "workflow_task_id"),
        Index("ix_approvals_approver", "approver"),
        Index("ix_approvals_approver_group_id", "approver_group_id"),
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
        ForeignKeyConstraint(
            ["approver_group_id"],
            ["user_groups.id"],
            ondelete="RESTRICT",
            name="fk_approvals_approver_group_id",
        ),
        ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_approvals_decided_by",
        ),
        CheckConstraint(
            "approver IS NULL OR approver_group_id IS NULL",
            name="ck_approvals_single_destination",
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
