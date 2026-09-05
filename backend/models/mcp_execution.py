"""The wire format between the backend and the MCP proxy.

Both ends import this module, so it is deliberately plain Pydantic: no
``table=True``, no SQLModel, nothing that would drag the ORM into the container
that runs user-registered MCP servers.

**Why a connection spec crosses at all.** The proxy holds neither the secret
encryption key nor Vault credentials, so it cannot expand a registered server's
``${secret:NAME/KEY}`` placeholders. The backend resolves them
(:func:`infrastructure.mcp_connection.resolve_connection`) and sends the result
for the one server being reached — which is the least the far side can be given
and still make the call.

Field names go over the wire in camelCase, like every other JSON surface in
A2Flow, and both spellings are accepted on the way in.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from infrastructure.mcp_client import HttpConnection, McpConnection, StdioConnection


class _Wire(BaseModel):
    """Base config shared by every model here."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class HttpConnectionSpec(_Wire):
    """A remote MCP server reachable over streamable HTTP.

    Attributes:
        transport: Discriminator selecting this shape.
        url: The server's streamable HTTP endpoint.
        headers: Headers sent with every request, secrets already resolved.
    """

    transport: Literal["streamable_http"] = "streamable_http"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)


class StdioConnectionSpec(_Wire):
    """An MCP server the proxy launches as a child process.

    Attributes:
        transport: Discriminator selecting this shape.
        command: The executable to run.
        args: ``argv`` entries, ``${env:NAME}`` already expanded.
        env: Environment for the child, secrets already resolved.
        raw_args: ``args`` before expansion, used only for error messages and
            logs so a secret-derived value never appears in one.
    """

    transport: Literal["stdio"] = "stdio"
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    raw_args: list[str] | None = None


#: One registered server, resolved and ready to reach.
ConnectionSpec = Annotated[
    HttpConnectionSpec | StdioConnectionSpec, Field(discriminator="transport")
]


class ExecutorCredential(_Wire):
    """The tool certificate and proof of possession backing one call.

    The private key is deliberately absent. It stays on the presenting side,
    where it signs the proof and authenticates the TLS connection; the proxy
    needs only the public half to check both.

    Attributes:
        certificate_pem: The leaf certificate the call is made under.
        signature: Base64 of the DER-encoded ECDSA signature over
            :func:`infrastructure.mcp_certificate.pop_digest`.
        nonce: The per-call random value that went into the digest.
        timestamp: When the signature was made; bounds replay.
    """

    certificate_pem: str
    signature: str
    nonce: str
    timestamp: datetime


class ExecutorListToolsRequest(_Wire):
    """Ask the proxy what one registered server advertises.

    Attributes:
        connection: The server to query.
    """

    connection: ConnectionSpec


class ExecutorCallToolRequest(_Wire):
    """Ask the proxy to invoke one tool on one registered server.

    Attributes:
        connection: The server to call.
        tool_name: Name of the tool to invoke.
        arguments: Arguments matching the tool's input schema. Also covered by
            the credential's signature, so the proxy can tell that the call it
            was asked to make is the call that was signed for.
        session_id: The ADK session the call belongs to, needed to recompute
            the signed digest.
        credential: The certificate backing the call.
    """

    connection: ConnectionSpec
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    session_id: str
    credential: ExecutorCredential | None = None


class ExecutorListToolsResponse(_Wire):
    """What one registered server advertises.

    Attributes:
        tools: The server's tool list, as MCP wire types.
    """

    tools: list[dict[str, Any]] = Field(default_factory=list)


class ExecutorCallToolResponse(_Wire):
    """The outcome of one proxied tool call.

    A tool that reports a failure does so inside ``result`` with ``isError``
    set — that is an answer, not a transport problem, and it travels as one.

    Attributes:
        result: The raw ``tools/call`` result, as an MCP wire type.
    """

    result: dict[str, Any]


def connection_to_spec(connection: McpConnection) -> ConnectionSpec:
    """Project a resolved connection into the shape that crosses the wire.

    Args:
        connection: The connection the backend built.

    Returns:
        The equivalent spec.
    """
    if isinstance(connection, StdioConnection):
        return StdioConnectionSpec(
            command=connection.command,
            args=list(connection.args),
            env=dict(connection.env),
            raw_args=None if connection.raw_args is None else list(connection.raw_args),
        )
    return HttpConnectionSpec(url=connection.url, headers=dict(connection.headers))


def spec_to_connection(spec: ConnectionSpec) -> McpConnection:
    """Rebuild a connection from the shape that crossed the wire.

    Args:
        spec: The spec the proxy received.

    Returns:
        The connection to open.
    """
    if isinstance(spec, StdioConnectionSpec):
        return StdioConnection(
            command=spec.command,
            args=list(spec.args),
            env=dict(spec.env),
            raw_args=None if spec.raw_args is None else list(spec.raw_args),
        )
    return HttpConnection(url=spec.url, headers=dict(spec.headers))
