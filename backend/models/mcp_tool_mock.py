"""MCPToolMock data models for create, update, and database persistence.

A mock stands in for one tool during a **draft** workflow run so the run can be
exercised end to end without the tool's side effects: no request reaches the MCP
server, no ``approvals`` row is written, nobody is notified. Which mocks apply is
chosen per run (see :meth:`services.workflow.WorkflowService.execute`), so a
read-only tool can keep hitting the real server while the destructive one next
to it is stubbed.

A mock names its target by ``(mcp_server_id, tool_name)``. ``mcp_server_id`` is
``None`` for the built-in agent tools listed in :data:`BUILTIN_MOCKABLE_TOOLS`,
which belong to A2Flow itself rather than to a registered server.

``responses`` is an **ordered** list indexed by call ordinal: the first entry is
returned the first time the tool is called in a run, the second entry the second
time, and so on. Once the list is exhausted the **last entry repeats** for every
further call, so a single-entry mock behaves as a constant. That ordering is what
lets one mock express a scenario -- approve the first request, reject the second
-- rather than only a fixed value.

Mocks are resolved by :mod:`infrastructure.tool_mocks`, which is consulted
*before* the MCP proxy. A mocked call therefore never reaches
:class:`infrastructure.mcp_proxy.McpProxy` and is deliberately absent from the
``mcp_tool_invocations`` audit trail: that table records real, authorized calls,
and a stub that never went upstream is not one.
"""

import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import Column, Index, UniqueConstraint
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, JSONColumn
from models.constraints import DescText, EntityName, ToolName
from models.tenant_scoped import TenantScoped

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)

#: Name of the built-in approval-request tool
#: (:func:`infrastructure.approval_tools.request_approval`), the one A2Flow tool
#: whose side effects -- an ``approvals`` row, notifications, an email -- make a
#: draft run unrunnable without a human.
REQUEST_APPROVAL_TOOL = "request_approval"

#: Built-in agent tools that may be mocked. These are A2Flow's own tools rather
#: than tools of a registered MCP server, so a mock naming one carries no
#: ``mcp_server_id``. Only tools with a side effect belong here: a read-only tool
#: is cheap to let through, and stubbing it only makes a dry run less faithful.
BUILTIN_MOCKABLE_TOOLS = frozenset({REQUEST_APPROVAL_TOOL})

#: Maximum number of per-ordinal responses one mock may define.
_MAX_RESPONSES = 20

#: Maximum length, in characters, of a ``text`` or ``error`` response value.
_MAX_TEXT_VALUE_LENGTH = 8000

#: Maximum length, in characters, of a ``structured`` response value once
#: serialized as JSON.
_MAX_STRUCTURED_VALUE_LENGTH = 16384


class MockResponseKind(StrEnum):
    """Which half of an MCP tool result a mocked response fills in.

    Attributes:
        structured: ``value`` is a JSON object placed in the result's
            ``structuredContent``. Use this for a tool whose caller reads
            fields off the result.
        text: ``value`` is a string placed in the result's textual ``content``.
        error: ``value`` is a message returned as a failed call, so the agent
            sees the tool report an error.
    """

    structured = "structured"
    text = "text"
    error = "error"


class MockResponse(BaseModel):
    """One mocked tool result, returned for one call ordinal."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    kind: MockResponseKind
    #: A JSON object when ``kind`` is ``structured``; a string otherwise.
    value: Any

    @model_validator(mode="after")
    def _validate_value(self) -> "MockResponse":
        """Enforce the value's type and size for the declared kind.

        Returns:
            The validated response.

        Raises:
            ValueError: If a ``structured`` value is not a JSON object or does
                not serialize, if a ``text``/``error`` value is not a string, or
                if either exceeds its length cap.
        """
        if self.kind is MockResponseKind.structured:
            if not isinstance(self.value, dict):
                raise ValueError("A structured response value must be a JSON object")
            try:
                encoded = json.dumps(self.value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "A structured response value must be JSON-serializable"
                ) from exc
            if len(encoded) > _MAX_STRUCTURED_VALUE_LENGTH:
                raise ValueError(
                    "A structured response value must be at most "
                    f"{_MAX_STRUCTURED_VALUE_LENGTH} characters once serialized"
                )
            return self
        if not isinstance(self.value, str):
            raise ValueError(f"A {self.kind.value} response value must be a string")
        if len(self.value) > _MAX_TEXT_VALUE_LENGTH:
            raise ValueError(
                f"A {self.kind.value} response value must be at most "
                f"{_MAX_TEXT_VALUE_LENGTH} characters"
            )
        return self


def _validate_target(mcp_server_id: str | None, tool_name: str | None) -> None:
    """Reject a mock whose server/tool pairing names nothing mockable.

    Args:
        mcp_server_id: The registered MCP server the tool belongs to, or
            ``None`` for a built-in agent tool.
        tool_name: The tool being mocked; ``None`` when a PATCH leaves it unset.

    Raises:
        ValueError: If a built-in mock names a tool outside
            :data:`BUILTIN_MOCKABLE_TOOLS`.
    """
    if (
        mcp_server_id is None
        and tool_name is not None
        and tool_name not in BUILTIN_MOCKABLE_TOOLS
    ):
        allowed = ", ".join(sorted(BUILTIN_MOCKABLE_TOOLS))
        raise ValueError(
            "A mock without an mcpServerId targets a built-in tool; "
            f"toolName must be one of: {allowed}"
        )


def _validate_responses(responses: list[MockResponse] | None) -> None:
    """Reject an empty or oversized response list.

    Args:
        responses: The per-ordinal responses, or ``None`` when a PATCH leaves
            them unset.

    Raises:
        ValueError: If the list is empty or exceeds :data:`_MAX_RESPONSES`.
    """
    if responses is None:
        return
    if not responses:
        raise ValueError("A mock must define at least one response")
    if len(responses) > _MAX_RESPONSES:
        raise ValueError(f"At most {_MAX_RESPONSES} responses are allowed")


class McpToolMockUpdate(SQLModel):
    """Partial update payload for an MCPToolMock — all fields are optional.

    When ``responses`` is ``None`` the stored list is left unchanged; when it is
    a list the stored list is replaced wholesale. The built-in-tool rule can only
    be checked against the merged result, so it is enforced by
    :class:`services.mcp_tool_mock.MCPToolMockService` as well as here.
    """

    model_config = _alias_config
    name: EntityName | None = None
    description: DescText | None = None
    mcp_server_id: str | None = None
    tool_name: ToolName | None = None
    responses: list[MockResponse] | None = None

    @model_validator(mode="after")
    def _validate(self) -> "McpToolMockUpdate":
        """Validate the response list of a partial update.

        The target pairing is not checked here: a PATCH that sets only
        ``toolName`` cannot know whether the stored row has an
        ``mcpServerId``. :class:`services.mcp_tool_mock.MCPToolMockService`
        checks the merged result instead.

        Returns:
            The validated payload.

        Raises:
            ValueError: If ``responses`` is present but empty or too long.
        """
        _validate_responses(self.responses)
        return self


class McpToolMockCreate(McpToolMockUpdate):
    """Creation payload for an MCPToolMock with required fields."""

    name: EntityName
    description: DescText | None = None
    mcp_server_id: str | None = None
    tool_name: ToolName
    responses: list[MockResponse]

    @model_validator(mode="after")
    def _validate_shape(self) -> "McpToolMockCreate":
        """Validate the target pairing and the response list together.

        Returns:
            The validated payload.

        Raises:
            ValueError: If the mock names an unmockable built-in tool, or its
                ``responses`` list is empty or too long.
        """
        _validate_target(self.mcp_server_id, self.tool_name)
        _validate_responses(self.responses)
        return self


class MCPToolMock(TenantScoped, BaseEntity, table=True):
    """Database-persisted stand-in for one tool during a draft workflow run.

    Declared independently of :class:`McpToolMockCreate` rather than inheriting
    it — the same shape :class:`models.workflow_task.WorkflowTask` uses — because
    ``responses`` cannot carry the payload's type here: SQLAlchemy's JSON
    serializer has no way to encode a Pydantic model, so the column stores plain
    dicts. The wire shape stays typed through :class:`McpToolMockRead`, and the
    ``*Create``/``*Update`` payloads above still validate incoming entries as
    :class:`MockResponse`.
    """

    __tablename__ = "mcp_tool_mocks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_mcp_tool_mocks_tenant_id_name"),
        Index("ix_mcp_tool_mocks_tenant_id_name", "tenant_id", "name"),
    )

    #: Redeclared without ``index=True``: the composite ``(tenant_id, name)``
    #: index above already serves tenant-only lookups through its leading column.
    tenant_id: str = Field(foreign_key="tenants.id", ondelete="RESTRICT")
    name: str
    description: str | None = None
    mcp_server_id: str | None = Field(
        default=None, foreign_key="mcp_servers.id", ondelete="RESTRICT", index=True
    )
    tool_name: str
    responses: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSONColumn, nullable=False)
    )


class McpToolMockRead(BaseEntity):
    """Read view of an MCPToolMock returned by the API.

    Mirrors every column of :class:`MCPToolMock`, restoring ``responses`` to its
    typed shape so the generated frontend bindings describe it. The mirroring is
    not cosmetic: this class is what
    :meth:`repositories.mcp_tool_mock.SqlMcpToolMockRepository.list` passes as
    ``readable=``, and a column missing here becomes unfilterable and unsortable
    through the list API.
    """

    model_config = _alias_config
    tenant_id: str
    name: str
    description: str | None = None
    mcp_server_id: str | None = None
    tool_name: str
    #: Required, unlike the table column's defaulted list: a stored mock always
    #: has at least one response (the write schemas reject an empty list), so
    #: leaving it optional here would only make the generated client treat a
    #: guaranteed field as possibly absent.
    responses: list[MockResponse]

    @classmethod
    def from_mock(cls, mock: MCPToolMock) -> "McpToolMockRead":
        """Build the read view of a stored mock.

        Args:
            mock: The persisted mock to project.

        Returns:
            A read view carrying the mock's columns with typed responses.
        """
        return cls.model_validate(mock.model_dump())
