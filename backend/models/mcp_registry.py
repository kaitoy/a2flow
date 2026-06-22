"""Read-only models for searching the official MCP registry.

These mirror the subset of the registry's server schema that A2Flow can use:
only the streamable-HTTP remote of each server, because the backend connects to
remote MCP servers over streamable HTTP exclusively (see
:mod:`infrastructure.mcp_client`). They are returned by ``GET /mcp-registry`` so
the admin UI can browse the registry and pre-fill the "New MCP Server" form.
"""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

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


class McpRegistryServerEntry(BaseModel):
    """A registry server reachable over streamable HTTP, flattened for the UI.

    Only the fields A2Flow needs to display a result and pre-fill the create form
    are kept; ``url`` is the server's streamable-HTTP remote endpoint.
    """

    model_config = _alias_config
    name: str
    title: str | None = None
    description: str | None = None
    version: str = ""
    status: str | None = None
    url: str
    headers: list[McpRegistryHeader] = Field(default_factory=list)
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
