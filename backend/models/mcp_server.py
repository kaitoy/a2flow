"""MCPServer data models for create, update, and database persistence.

An MCPServer is a remote Model Context Protocol server registered with A2Flow.
Registered servers are the catalog the workflow agent draws from when it binds
MCP tools to WorkflowTasks: at planning time the agent lists each server's
tools, and at execution time bound tools are invoked through the
``call_mcp_tool`` proxy (see :mod:`infrastructure.mcp_tools`).

Connections use streamable HTTP. The optional ``headers`` mapping (e.g.
``{"Authorization": "Bearer ..."}``) is sent verbatim with every request to the
server; values are stored in plaintext, which is acceptable for this app's
local, single-operator deployment model.
"""

from typing import Any

from pydantic import model_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import Column, Index, UniqueConstraint
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, JSONColumn
from models.constraints import EntityName, HttpUrl

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)

#: Maximum number of header entries allowed on an MCP server.
_MAX_HEADERS = 50

#: Maximum length, in characters, of each header key and value.
_MAX_HEADER_VALUE_LENGTH = 1024


class MCPServerUpdate(SQLModel):
    """Partial update payload for an MCPServer — all fields are optional.

    When ``headers`` is ``None`` the stored headers are left unchanged; when it
    is a mapping the full set of headers is replaced with that mapping.
    """

    model_config = _alias_config
    name: EntityName | None = None
    url: HttpUrl | None = None
    headers: dict[str, str] | None = None

    @model_validator(mode="after")
    def _validate_headers(self) -> "MCPServerUpdate":
        """Bound the headers mapping size and the length of each key and value.

        Returns:
            The validated model instance.

        Raises:
            ValueError: If there are more than ``_MAX_HEADERS`` entries, or any
                header key or value exceeds ``_MAX_HEADER_VALUE_LENGTH`` characters.
        """
        if self.headers is not None:
            if len(self.headers) > _MAX_HEADERS:
                raise ValueError(f"At most {_MAX_HEADERS} headers are allowed")
            for key, value in self.headers.items():
                if (
                    len(key) > _MAX_HEADER_VALUE_LENGTH
                    or len(value) > _MAX_HEADER_VALUE_LENGTH
                ):
                    raise ValueError(
                        "Header keys and values must be at most "
                        f"{_MAX_HEADER_VALUE_LENGTH} characters"
                    )
        return self


class MCPServerCreate(MCPServerUpdate):
    """Creation payload for an MCPServer with required fields."""

    name: EntityName
    url: HttpUrl
    headers: dict[str, str] = Field(default_factory=dict)


class MCPServer(MCPServerCreate, BaseEntity, table=True):
    """Database-persisted remote MCP server reachable over streamable HTTP."""

    __tablename__ = "mcp_servers"
    __table_args__ = (
        UniqueConstraint("name", name="uq_mcp_servers_name"),
        Index("ix_mcp_servers_name", "name"),
    )

    headers: dict[str, str] = Field(
        default_factory=dict, sa_column=Column(JSONColumn, nullable=False)
    )


class McpToolInfo(SQLModel):
    """A tool advertised by a remote MCP server.

    Returned by ``GET /mcp-servers/{id}/tools`` so the admin UI (and the agent,
    via ``list_mcp_tools``) can present the server's catalog when binding tools
    to WorkflowTasks.
    """

    model_config = _alias_config
    name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
