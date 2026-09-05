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
one, and it marks where the approval takes effect rather than the single task it
authorizes: the approval covers that task **and every task downstream of it up
to the next approval** (:mod:`infrastructure.approval_scope`). Both the gate
(:class:`infrastructure.mcp_policies.TaskCertificatePolicy`) and the grant
(:class:`services.mcp_tool_certificate.McpToolCertificateService`) work from
that scope, so naming a step whose whole job is to ask for a go-ahead is the
natural shape -- the decision reaches the steps that follow it.
:func:`infrastructure.approval_tools.request_approval` requires the argument.

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

``approved_calls`` is what the decision is *about*. An approval used to grant a
capability and nothing more: the tool certificate it mints freezes *which* tools
the covered tasks may call, never *with what*, so a decision made on a
description of one action authorized every other use of the same tool. The
declaration closes that gap. It names each MCP call the request authorizes and
constrains the arguments it may carry, the approver reads it before deciding,
and :class:`infrastructure.mcp_policies.ApprovedArgumentsPolicy` refuses any call
that deviates from it. The constraint vocabulary and the matching rules live in
:mod:`infrastructure.approved_calls`, shared by the request path and the gate so
the two cannot disagree about what a declaration means.

A tool the workflow's design marked as not requiring input approval is named in
the declaration too, as an entry carrying ``unconstrained_arguments`` -- so the
list stays the complete account of what the decision authorizes, and the
approver can see which tools were left unbounded. See :class:`ApprovedCall`.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import field_serializer, model_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import CheckConstraint, Column, ForeignKeyConstraint, Index
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, JSONColumn, TZDateTime, iso_z_or_none
from models.constraints import BodyText, ShortText, ToolName
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


class ApprovedCall(SQLModel):
    """One MCP call an approval authorizes, and the arguments it may carry.

    ``arguments`` maps an argument name to the constraint its value must
    satisfy. A constraint is an object holding exactly one operator -- ``eq``,
    ``in``, ``lte``, ``gte`` or ``matches`` -- optionally alongside the
    ``optional`` modifier, which lets that argument be absent altogether. The
    operator is always spelled out rather than a bare literal standing in for
    equality, so an argument whose own value is an object or a list is never
    mistaken for a constraint.

    ``unconstrained_arguments`` says the opposite of everything above: this
    tool may be called with **any** arguments. It is set only by
    :func:`infrastructure.approval_tools.request_approval`, for a tool the
    workflow's design marked as not requiring input approval
    (:class:`models.workflow_task.ToolBinding`), and an entry the requesting
    agent supplies carrying it is rejected -- otherwise a run could exempt
    itself. Recording it here rather than resolving the binding at call time is
    what keeps the declaration the whole picture: the approver reads one list
    naming every tool the decision authorizes, and the gate matches against that
    same list and nothing else. ``arguments`` is empty on such an entry; a
    declaration setting both is refused as contradictory.

    The vocabulary is deliberately not modelled as a Pydantic union here.
    :func:`infrastructure.approved_calls.validate_declaration` checks it on the
    write path, where it can report every problem at once and name the tool to
    fix -- which is what the requesting agent needs. A model validator would
    instead also run on the way *out*, over rows written before this field
    existed, turning them from readable into an HTTP 500. That is the same split
    :meth:`ApprovalCreate._reject_two_destinations` documents.
    """

    model_config = _alias_config
    mcp_server_id: str
    tool_name: ToolName
    #: Argument name to its constraint. An argument absent from this mapping may
    #: not be passed at all: the approver never saw it.
    arguments: dict[str, dict[str, Any]] = {}
    #: Whether this tool may be called with any arguments at all. Server-set,
    #: for a tool the workflow's design exempted from input approval.
    unconstrained_arguments: bool = False


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
    #: The MCP calls this approval authorizes. Empty only for an approval
    #: gating an action no MCP tool performs, or one recorded before the field
    #: existed -- see the module docstring.
    approved_calls: list[ApprovedCall] = []

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
    #: Stored as plain dicts, unlike the typed declaration this class inherits:
    #: SQLAlchemy's JSON serializer has no way to encode a Pydantic model, the
    #: same reason :class:`models.mcp_tool_mock.MCPToolMock` declares its
    #: ``responses`` column this way. :class:`ApprovalRead` restores the typed
    #: shape on the way out, so the generated frontend bindings still describe
    #: it.
    approved_calls: list[dict[str, Any]] = Field(  # type: ignore[assignment]
        default_factory=list, sa_column=Column(JSONColumn, nullable=False)
    )
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


class ApprovalRead(ApprovalCreate, TenantScoped, BaseEntity):
    """Read view of an Approval returned by the API.

    Mirrors :class:`Approval` field for field, restoring ``approved_calls`` to
    the typed shape :class:`ApprovalCreate` declares. The table class stores
    plain dicts, which would otherwise reach the OpenAPI schema as untyped
    objects and leave the approval UI nothing to render the approved calls from.

    Used as the routes' ``response_model`` rather than replacing
    :class:`Approval` in the repository: filtering and sorting still resolve
    against the table class, and ``approved_calls`` is a JSON column no query
    orders by.
    """

    model_config = _alias_config
    decided_at: datetime | None = None
    decided_by: str | None = None

    @field_serializer("decided_at", when_used="json")
    def _serialize_decided_at(self, dt: datetime | None) -> str | None:
        """Serialize ``decided_at`` as ISO-8601 with a ``Z`` suffix, or ``None``.

        Args:
            dt: The decision timestamp, or ``None`` while still pending.

        Returns:
            The ISO-8601 string with a ``Z`` suffix, or ``None``.
        """
        return iso_z_or_none(dt)
