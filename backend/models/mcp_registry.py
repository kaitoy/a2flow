"""Read-only models for searching the official MCP registry.

These mirror the subset of the registry's server schema that A2Flow can
register, flattened into one entry per server. A registry server is surfaced
through whichever of A2Flow's two transports fits it (see
:mod:`infrastructure.mcp_client`):

* ``streamable_http`` — the server's streamable-HTTP remote, carrying ``url``
  and its ``headers`` definitions. Preferred when a server offers both.
* ``stdio`` — one of the server's stdio ``packages``, flattened into the
  ``command`` / ``args`` / ``env`` a stdio MCP server needs.

They are returned by ``GET /mcp-registry`` so the admin UI can browse the
registry and pre-fill the "New MCP Server" form.
"""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from models.mcp_server import McpTransport

_alias_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class McpRegistryHeader(BaseModel):
    """An HTTP header a registry server's streamable-HTTP remote expects.

    Registry headers are *definitions* (name plus metadata), not concrete values:
    secret headers carry no value and must be filled in by the operator. The
    admin UI uses these to pre-fill header keys on the create form.
    """

    model_config = _alias_config
    name: str
    description: str | None = None
    is_required: bool = False
    is_secret: bool = False
    value: str | None = None


class McpRegistryEnvVar(BaseModel):
    """An environment variable a registry server's stdio package expects.

    The stdio counterpart of :class:`McpRegistryHeader`, and definitions in the
    same sense: a secret variable carries no value and must be filled in by the
    operator (or pointed at a ``${secret:NAME/KEY}`` reference).
    """

    model_config = _alias_config
    name: str
    description: str | None = None
    is_required: bool = False
    is_secret: bool = False
    value: str | None = None


class McpRegistryServerEntry(BaseModel):
    """A registrable registry server, flattened for the UI.

    Only the fields A2Flow needs to display a result and pre-fill the create
    form are kept. Which of the two field groups is populated follows
    ``transport``: ``url``/``headers`` for ``streamable_http``,
    ``command``/``args``/``env`` for ``stdio``.
    """

    model_config = _alias_config
    name: str
    title: str | None = None
    description: str | None = None
    version: str = ""
    status: str | None = None
    transport: McpTransport = McpTransport.streamable_http
    url: str | None = None
    headers: list[McpRegistryHeader] = Field(default_factory=list)
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: list[McpRegistryEnvVar] = Field(default_factory=list)
    website_url: str | None = None
    repository_url: str | None = None


class McpRegistrySearchResult(BaseModel):
    """A page of registry search results plus the cursor for the next page.

    The cursor lives on the result body (not :class:`ApiMeta`) so the "Load more"
    control in the admin UI can request the following page.
    """

    model_config = _alias_config
    servers: list[McpRegistryServerEntry]
    next_cursor: str | None = None
