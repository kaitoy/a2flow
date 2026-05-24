"""WorkflowTask data models for create, update, and database persistence.

A WorkflowTask represents a single actionable item belonging to a WorkflowSession.
Tasks are intended to capture the steps produced by the agent under the workflow
instruction "use the provided skill to produce an actionable task list".
"""

from enum import StrEnum

from pydantic.alias_generators import to_camel
from sqlalchemy import ForeignKeyConstraint, Index
from sqlmodel import SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class WorkflowTaskStatus(StrEnum):
    """Lifecycle states a WorkflowTask can occupy."""

    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class WorkflowTaskUpdate(SQLModel):
    """Partial update payload for a WorkflowTask — every field is optional.

    Does not include ``workflow_session_id``: tasks cannot be re-parented to a
    different session after creation.
    """

    model_config = _alias_config
    title: str | None = None
    description: str | None = None
    status: WorkflowTaskStatus | None = None
    position: int | None = None


class WorkflowTaskCreate(WorkflowTaskUpdate):
    """Creation payload for a WorkflowTask.

    Inherits the optional fields from :class:`WorkflowTaskUpdate` and tightens
    ``title`` to required, supplies defaults for ``status`` and ``position``,
    and adds the required parent ``workflow_session_id`` foreign key.
    """

    workflow_session_id: str
    title: str
    status: WorkflowTaskStatus = WorkflowTaskStatus.pending
    position: int = 0


class WorkflowTask(WorkflowTaskCreate, BaseEntity, table=True):
    """Database-persisted WorkflowTask record belonging to a WorkflowSession."""

    __tablename__ = "workflow_tasks"
    __table_args__ = (
        Index("ix_workflow_tasks_session_id", "workflow_session_id"),
        ForeignKeyConstraint(
            ["workflow_session_id"],
            ["workflow_sessions.id"],
            ondelete="CASCADE",
        ),
    )
