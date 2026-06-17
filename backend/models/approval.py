"""Approval data models for create, update, read, and database persistence.

An Approval is a human-in-the-loop decision the workflow agent asks for while
executing a workflow session. The agent creates an Approval (in the ``pending``
state) via the ``request_approval`` tool, the GUI surfaces it to the approver,
and the approver resolves it to ``approved`` or ``rejected``. The agent then
continues or aborts the task based on the recorded decision.

``workflow_session_id`` links the approval to the workflow session it belongs to
(so the GUI can deep-link to the session chat); the optional ``workflow_task_id``
ties it to the specific task that needs approval. The optional ``approver`` is
the user the agent addresses the request to (the request's destination), set when
the agent creates the approval. ``response`` records an optional free-text comment
supplied when the approver resolves the request.
"""

from enum import StrEnum

from pydantic.alias_generators import to_camel
from sqlalchemy import ForeignKeyConstraint, Index
from sqlmodel import SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity
from models.constraints import BodyText, ShortText

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class ApprovalStatus(StrEnum):
    """Lifecycle states of an approval request."""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ApprovalUpdate(SQLModel):
    """Partial update payload for an Approval.

    Used by the resolve endpoint (``PATCH /approvals/{id}``): the approver moves
    the request to ``approved`` or ``rejected`` and may attach a ``response``
    comment. Both fields are optional so a caller can update either alone.
    """

    model_config = _alias_config
    status: ApprovalStatus | None = None
    response: BodyText | None = None


class ApprovalCreate(ApprovalUpdate):
    """Creation payload for an Approval.

    Adds the required ``workflow_session_id`` and ``title``, the optional
    ``description``, ``workflow_task_id`` link, and ``approver`` (the user the
    request is addressed to), and defaults ``status`` to ``pending`` so a freshly
    requested approval starts unresolved.
    """

    workflow_session_id: str
    title: ShortText
    description: BodyText | None = None
    workflow_task_id: str | None = None
    approver: str | None = None
    status: ApprovalStatus = ApprovalStatus.pending


class Approval(ApprovalCreate, BaseEntity, table=True):
    """Database-persisted approval request.

    ``workflow_session_id`` references the owning workflow session
    (``ON DELETE CASCADE``), so deleting the session removes its approvals. The
    optional ``workflow_task_id`` references the task the approval concerns
    (``ON DELETE SET NULL``), so deleting the task leaves the approval record
    intact but unlinked. The optional ``approver`` references the user the request
    is addressed to (``ON DELETE RESTRICT``), matching the audit user FKs.
    """

    __tablename__ = "approvals"
    __table_args__ = (
        Index("ix_approvals_workflow_session_id", "workflow_session_id"),
        Index("ix_approvals_workflow_task_id", "workflow_task_id"),
        Index("ix_approvals_approver", "approver"),
        ForeignKeyConstraint(
            ["workflow_session_id"],
            ["workflow_sessions.id"],
            ondelete="CASCADE",
            name="fk_approvals_workflow_session_id",
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
