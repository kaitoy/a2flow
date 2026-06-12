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

from pydantic.alias_generators import to_camel
from sqlalchemy import JSON, Column, Index, UniqueConstraint
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class MCPServerUpdate(SQLModel):
    """Partial update payload for an MCPServer — all fields are optional.

    When ``headers`` is ``None`` the stored headers are left unchanged; when it
    is a mapping the full set of headers is replaced with that mapping.
    """

    model_config = _alias_config
    name: str | None = None
    url: str | None = None
    headers: dict[str, str] | None = None


class MCPServerCreate(MCPServerUpdate):
    """Creation payload for an MCPServer with required fields."""

    name: str
    url: str
    headers: dict[str, str] = Field(default_factory=dict)


class MCPServer(MCPServerCreate, BaseEntity, table=True):
    """Database-persisted remote MCP server reachable over streamable HTTP."""

    __tablename__ = "mcp_servers"
    __table_args__ = (
        UniqueConstraint("name", name="uq_mcp_servers_name"),
        Index("ix_mcp_servers_name", "name"),
    )

    headers: dict[str, str] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
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
