"""MCPServer data models for create, update, and database persistence.

An MCPServer is a Model Context Protocol server registered with A2Flow.
Registered servers are the catalog the workflow agent draws from when it binds
MCP tools to WorkflowTasks: at design time the agent lists each server's
tools, and at execution time bound tools are invoked through the
``call_mcp_tool`` proxy (see :mod:`infrastructure.mcp_tools`).

Two transports exist, discriminated by ``transport``:

* ``streamable_http`` — a remote server addressed by ``url``. The optional
  ``headers`` mapping (e.g. ``{"Authorization": "Bearer ..."}``) is sent
  verbatim with every request.
* ``stdio`` — a local server launched as a child process of the backend:
  ``command`` (``npx`` or ``uvx``, the only two runtimes the backend image
  ships) plus ``args``, with ``env`` merged over the small set of variables
  :func:`mcp.client.stdio.get_default_environment` deems safe to inherit.
  ``args`` is passed as a list and never through a shell.

``headers`` and ``env`` values may embed ``${secret:NAME/KEY}`` placeholders,
resolved at connection time (see :mod:`infrastructure.secret_resolver`);
anything else is stored in plaintext, which is acceptable for this app's
local, single-operator deployment model.

A stdio server's ``args`` entries may additionally embed ``${env:NAME}``,
referencing a key of that same server's ``env`` map — useful for a launcher
that expects a value as a CLI flag rather than reading it from the process
environment. ``NAME`` must be a key of ``env``, checked eagerly at write time
(:func:`referenced_env_names`, used by this module's ``_validate_shape`` and
by :class:`services.mcp_server.MCPServerService.update`); expansion itself
happens at connection time in :func:`infrastructure.mcp_client.resolve_connection`,
after ``env``'s own ``${secret:NAME/KEY}`` placeholders are resolved — so
``${env:NAME}`` transparently picks up secret-resolved values too.
"""

import re
from enum import StrEnum
from typing import Any

from pydantic import model_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import Column, Index, UniqueConstraint
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, JSONColumn
from models.constraints import EntityName, HttpUrl, McpArg
from models.tenant_scoped import TenantScoped

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)

#: Maximum number of header entries allowed on an MCP server.
_MAX_HEADERS = 50

#: Maximum length, in characters, of each header key and value.
_MAX_HEADER_VALUE_LENGTH = 1024

#: Maximum number of environment variables allowed on a stdio MCP server.
_MAX_ENV_VARS = 50

#: Maximum length, in characters, of each environment variable key and value.
_MAX_ENV_VALUE_LENGTH = 4096

#: Maximum number of ``argv`` entries allowed on a stdio MCP server.
_MAX_ARGS = 100

#: Matches ``${env:NAME}`` in an ``args`` entry, referencing a key of this
#: same server's ``env`` mapping. ``NAME`` uses the POSIX env-var charset so
#: the closing ``}`` is unambiguous even though ``env`` keys themselves carry
#: no charset restriction of their own.
ENV_ARG_PLACEHOLDER_PATTERN = re.compile(r"\$\{env:([A-Za-z_][A-Za-z0-9_]*)\}")


def referenced_env_names(args: list[str]) -> set[str]:
    """Return every name referenced via ``${env:NAME}`` across ``args``.

    Args:
        args: The ``argv`` entries to scan.

    Returns:
        The set of referenced names, deduplicated.
    """
    names: set[str] = set()
    for arg in args:
        names.update(ENV_ARG_PLACEHOLDER_PATTERN.findall(arg))
    return names


class McpTransport(StrEnum):
    """How A2Flow reaches an MCP server: over HTTP, or as a child process."""

    streamable_http = "streamable_http"
    stdio = "stdio"


class McpCommand(StrEnum):
    """Launcher for a stdio MCP server: the only two runtimes the backend image ships."""

    npx = "npx"
    uvx = "uvx"


class MCPServerUpdate(SQLModel):
    """Partial update payload for an MCPServer — all fields are optional.

    When ``headers``, ``args``, or ``env`` is ``None`` the stored value is left
    unchanged; when it is a mapping (or list) the stored value is replaced
    wholesale. The per-transport shape rules (which fields must be present or
    absent) are enforced against the merged result by
    :class:`services.mcp_server.MCPServerService`, because a PATCH body alone
    cannot know the effective transport.
    """

    model_config = _alias_config
    name: EntityName | None = None
    transport: McpTransport | None = None
    url: HttpUrl | None = None
    headers: dict[str, str] | None = None
    command: McpCommand | None = None
    args: list[McpArg] | None = None
    env: dict[str, str] | None = None

    @model_validator(mode="after")
    def _validate_sizes(self) -> "MCPServerUpdate":
        """Bound the headers/env mappings and the ``args`` list.

        Returns:
            The validated model instance.

        Raises:
            ValueError: If any collection exceeds its entry-count cap, or any
                header/env key or value exceeds its length cap.
        """
        _assert_mapping_within(
            self.headers, _MAX_HEADERS, _MAX_HEADER_VALUE_LENGTH, "Header"
        )
        _assert_mapping_within(
            self.env, _MAX_ENV_VARS, _MAX_ENV_VALUE_LENGTH, "Environment variable"
        )
        if self.args is not None and len(self.args) > _MAX_ARGS:
            raise ValueError(f"At most {_MAX_ARGS} arguments are allowed")
        return self


def _assert_mapping_within(
    mapping: dict[str, str] | None, max_entries: int, max_length: int, label: str
) -> None:
    """Reject a mapping that exceeds its entry-count or key/value length caps.

    Args:
        mapping: The mapping to check; ``None`` passes (the field is unset).
        max_entries: Maximum number of entries allowed.
        max_length: Maximum length, in characters, of each key and each value.
        label: Human-readable field name used in the error messages.

    Raises:
        ValueError: If the mapping has too many entries, or any key or value is
            too long.
    """
    if mapping is None:
        return
    if len(mapping) > max_entries:
        raise ValueError(f"At most {max_entries} {label.lower()} entries are allowed")
    for key, value in mapping.items():
        if len(key) > max_length or len(value) > max_length:
            raise ValueError(
                f"{label} keys and values must be at most {max_length} characters"
            )


class MCPServerCreate(MCPServerUpdate):
    """Creation payload for an MCPServer with required fields.

    ``transport`` defaults to ``streamable_http`` so an existing remote-server
    payload stays valid unchanged.
    """

    name: EntityName
    transport: McpTransport = McpTransport.streamable_http
    url: HttpUrl | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    command: McpCommand | None = None
    args: list[McpArg] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_shape(self) -> "MCPServerCreate":
        """Enforce exactly one shape per transport.

        Returns:
            The validated model instance.

        Raises:
            ValueError: If a ``streamable_http`` server is missing ``url`` or
                carries stdio fields, a ``stdio`` server is missing
                ``command`` or carries remote fields, or its ``args`` embed a
                ``${env:NAME}`` placeholder naming a key absent from ``env``.
        """
        if self.transport is McpTransport.streamable_http:
            if self.url is None:
                raise ValueError("A streamable_http server requires a url")
            if self.command is not None or self.args or self.env:
                raise ValueError(
                    "A streamable_http server must not set command, args, or env"
                )
        else:
            if self.command is None:
                raise ValueError("A stdio server requires a command")
            if self.url is not None or self.headers:
                raise ValueError("A stdio server must not set url or headers")
            missing = referenced_env_names(self.args) - self.env.keys()
            if missing:
                raise ValueError(
                    "args reference undefined env vars: " + ", ".join(sorted(missing))
                )
        return self


class MCPServer(MCPServerCreate, TenantScoped, BaseEntity, table=True):
    """Database-persisted MCP server, remote over streamable HTTP or local stdio."""

    __tablename__ = "mcp_servers"
    tenant_id: str = Field(foreign_key="tenants.id", ondelete="RESTRICT")
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_mcp_servers_tenant_id_name"),
        Index("ix_mcp_servers_tenant_id_name", "tenant_id", "name"),
    )

    headers: dict[str, str] = Field(
        default_factory=dict, sa_column=Column(JSONColumn, nullable=False)
    )
    args: list[str] = Field(
        default_factory=list, sa_column=Column(JSONColumn, nullable=False)
    )
    env: dict[str, str] = Field(
        default_factory=dict, sa_column=Column(JSONColumn, nullable=False)
    )


class McpServerRead(BaseEntity):
    """Read view of an MCPServer returned by the API, including its tags.

    Mirrors every column of :class:`MCPServer` and adds ``tag_ids``, which lives
    in :class:`models.tag.McpServerTag` rather than on the server row. The
    mirroring is not cosmetic: this class is what
    :meth:`repositories.mcp_server.SqlMCPServerRepository.list` passes as
    ``readable=``, and a column missing here becomes unfilterable and
    unsortable through the list API.
    """

    model_config = _alias_config
    tenant_id: str
    name: str
    transport: McpTransport = McpTransport.streamable_http
    url: str | None = None
    headers: dict[str, str] = {}
    command: McpCommand | None = None
    args: list[str] = []
    env: dict[str, str] = {}
    #: Ids of the tags attached to this server.
    tag_ids: list[str] = []

    @classmethod
    def from_server(cls, server: MCPServer, *, tag_ids: list[str]) -> "McpServerRead":
        """Build the read view of a stored MCP server with its tags attached.

        Args:
            server: The persisted server to project.
            tag_ids: Ids of the tags attached to ``server``.

        Returns:
            A read view carrying the server's columns plus its tags.
        """
        return cls(**server.model_dump(), tag_ids=tag_ids)


class McpToolInfo(SQLModel):
    """A tool advertised by a registered MCP server.

    Returned by ``GET /mcp-servers/{id}/tools`` so the admin UI (and the agent,
    via ``list_mcp_tools``) can present the server's catalog when binding tools
    to WorkflowTasks.
    """

    model_config = _alias_config
    name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
