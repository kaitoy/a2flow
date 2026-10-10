"""MCP elicitation model: a question an MCP server asked in the middle of a tool call.

The MCP protocol lets a server stop partway through ``tools/call`` and ask the
client something (``elicitation/create``): a message and a small form, flat
primitive fields described by a JSON schema. The Azure MCP Server, for one,
asks before every operation that touches a secret. A2Flow holds the call open,
shows the question in the workflow session's chat, and lets the run's initiator
answer it; an :class:`MCPElicitation` is that question and, once given, its
answer.

The row is the hand-off between two processes that never meet: the one holding
the tool call open polls it, and the request that carries the person's answer --
which may reach any replica -- writes it. ``expires_at`` bounds the wait; past
it the question can no longer be answered, whether or not the waiting side has
noticed yet, so a question left behind by a process that died needs no clean-up
to stop being answerable.

The row cascades with its run, like the run's files and approvals.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import field_serializer
from pydantic.alias_generators import to_camel
from sqlalchemy import Column, ForeignKeyConstraint, Index
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, JSONColumn, TZDateTime, iso_z_or_none
from models.tenant_scoped import TenantScoped

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class MCPElicitationStatus(StrEnum):
    """Where a question stands.

    Declared in lifecycle order, since enum columns sort by declaration
    position (see ``.claude/rules/api-conventions.md``). Every state but
    :attr:`pending` is final.
    """

    pending = "pending"
    """Shown in the chat, waiting on the run's initiator."""

    accepted = "accepted"
    """The initiator submitted the form; ``content`` holds the values."""

    declined = "declined"
    """The initiator explicitly refused to answer."""

    cancelled = "cancelled"
    """The initiator dismissed the question without choosing."""

    expired = "expired"
    """Nobody answered before ``expires_at``, or the call stopped waiting."""


class MCPElicitationAnswer(SQLModel):
    """Body of the request that answers a question.

    Mirrors the MCP ``ElicitResult``: ``content`` is required for ``accept``
    and ignored otherwise.
    """

    model_config = _alias_config
    action: Literal["accept", "decline", "cancel"]
    content: dict[str, Any] | None = None


class MCPElicitationCreate(SQLModel):
    """What is recorded when a server asks a question."""

    model_config = _alias_config

    workflow_execution_id: str
    """Identifier of the WorkflowExecution whose tool call asked."""

    session_id: str
    """The ADK session (the chat) the tool call ran in."""

    mcp_server_id: str
    """Id of the registered MCP server that asked. Not a foreign key: the
    question outlives nothing but its run, and a server deleted afterwards
    should not take the record of what it asked with it."""

    server_name: str
    """The server's name when it asked, shown in the chat."""

    tool_name: str
    """The tool whose call the question interrupted."""

    message: str
    """The server's question, shown to the person verbatim."""

    requested_schema: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONColumn, nullable=False)
    )
    """JSON schema of the form: an object of flat primitive properties."""

    expires_at: datetime = Field(sa_type=TZDateTime)
    """Past this instant the question can no longer be answered."""


class MCPElicitation(MCPElicitationCreate, TenantScoped, BaseEntity, table=True):
    """Database-persisted question an MCP server asked during a workflow run.

    ``status``, ``content``, ``answered_by`` and ``answered_at`` are written
    once, when the question leaves :attr:`MCPElicitationStatus.pending` (see
    :meth:`repositories.mcp_elicitation.SqlMCPElicitationRepository.answer`).
    """

    __tablename__ = "mcp_elicitations"

    status: MCPElicitationStatus = MCPElicitationStatus.pending
    content: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSONColumn, nullable=True)
    )
    """The submitted form values, for an accepted question."""

    answered_by: str | None = None
    """Id of the user who answered; ``None`` until then, and for an expiry."""

    answered_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    """When the question left ``pending``."""

    __table_args__ = (
        Index("ix_mcp_elicitations_workflow_execution_id", "workflow_execution_id"),
        ForeignKeyConstraint(
            ["workflow_execution_id"],
            ["workflow_executions.id"],
            ondelete="CASCADE",
            name="fk_mcp_elicitations_workflow_execution_id",
        ),
        ForeignKeyConstraint(
            ["answered_by"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_mcp_elicitations_answered_by",
        ),
    )

    @field_serializer("expires_at", "answered_at", when_used="json")
    def _serialize_instants(self, dt: datetime | None) -> str | None:
        """Serialize the instants as ISO-8601 with a ``Z`` suffix, or ``None``.

        Args:
            dt: The instant, or ``None`` while unset.

        Returns:
            The ISO-8601 string with a ``Z`` suffix, or ``None``.
        """
        return iso_z_or_none(dt)
