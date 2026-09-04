"""Append-only audit of every MCP tool call the proxy decided on.

One row per ``call_tool`` that reached a registered MCP server, or was stopped
on its way to one, written by
:class:`infrastructure.mcp_audit.SqlMcpAuditSink` before the proxy releases its
database session.

Two kinds of operation are deliberately absent. Listings have no side effect and
would bury the calls that do. A call a draft run answers from its
:mod:`tool mocks <infrastructure.tool_mocks>` never reaches a server at all, so
neither its approval nor its refusal is recorded -- a row either way would
misdescribe what happened.

**What makes it non-repudiable.** Every allowed call presents a certificate,
and the row keeps that certificate's serial together with the exact bytes that
were signed for it -- ``arguments_digest``, ``nonce``, ``signed_at`` -- and the
signature itself. Anyone holding the root CA's public half can
recompute the digest and check the signature later, without the private key and
without trusting this table. A tampered row stops verifying.

**No foreign key to the run.** ``workflow_execution_id`` and
``workflow_task_id`` are plain indexed columns, unlike every other reference in
the schema. An audit record has to outlive what it describes: ``CASCADE`` would
delete the evidence along with the run, and ``RESTRICT`` would make a run
undeletable because it was audited. ``tenant_id`` keeps its foreign key, since
tenant deletion is already RESTRICTed everywhere.

Nothing reads this table yet. It exists so the question "which approval
authorized this call, and who granted it" has an answer that does not depend on
log retention.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import field_serializer
from pydantic.alias_generators import to_camel
from sqlalchemy import Index
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, TZDateTime, iso_z_or_none
from models.constraints import ToolName
from models.tenant_scoped import TenantScoped

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class McpAuditDecision(StrEnum):
    """Whether the proxy let the call through."""

    allowed = "allowed"
    denied = "denied"


class McpToolInvocationCreate(SQLModel):
    """Fields recorded for one decided tool call."""

    model_config = _alias_config

    #: The ADK session the call was made in. Recorded because it is one of the
    #: inputs to the signed digest: with it, every field
    #: :func:`infrastructure.mcp_certificate.pop_digest_from_parts` needs is a
    #: column of this table, so a recorded signature stays checkable on its own.
    session_id: str
    #: The run the call belongs to. Never a foreign key; see the module
    #: docstring.
    workflow_execution_id: str | None = None
    #: The task the presented certificate authorized, when one was presented.
    workflow_task_id: str | None = None
    #: Decimal serial of the presented certificate, or ``None`` when the call
    #: presented none.
    certificate_serial: str | None = None
    #: The approval that certificate spoke for, or ``None`` when the run's
    #: initiator granted it themselves -- look the serial up in
    #: ``mcp_tool_certificates`` for who that was.
    approval_id: str | None = None
    mcp_server_id: str
    tool_name: ToolName
    decision: McpAuditDecision
    #: Why the call was refused, verbatim from the policy. ``None`` when allowed.
    denial_reason: str | None = None
    #: SHA-256 (hex) of the canonical JSON of the call's arguments. Recorded for
    #: every call, so an unauthenticated one is still tied to what it asked for.
    arguments_digest: str
    #: Base64 DER of the proof-of-possession signature, when one was presented.
    signature: str | None = None
    #: The nonce that went into the signed digest.
    nonce: str | None = None
    #: The timestamp that went into the signed digest.
    signed_at: datetime | None = None


class MCPToolInvocation(McpToolInvocationCreate, TenantScoped, BaseEntity, table=True):
    """One recorded decision about one MCP tool call."""

    __tablename__ = "mcp_tool_invocations"
    __table_args__ = (
        Index(
            "ix_mcp_tool_invocations_tenant_id_created_at",
            "tenant_id",
            "created_at",
        ),
        Index(
            "ix_mcp_tool_invocations_workflow_execution_id",
            "workflow_execution_id",
        ),
        Index("ix_mcp_tool_invocations_certificate_serial", "certificate_serial"),
    )

    #: Redeclared without ``index=True``: the composite
    #: ``(tenant_id, created_at)`` index above already serves tenant-only
    #: lookups through its leading column.
    tenant_id: str = Field(foreign_key="tenants.id", ondelete="RESTRICT")
    signed_at: datetime | None = Field(default=None, sa_type=TZDateTime)

    @field_serializer("signed_at", when_used="json")
    def _serialize_signed_at(self, dt: datetime | None) -> str | None:
        """Serialize the signing instant, passing ``None`` through."""
        return iso_z_or_none(dt)
