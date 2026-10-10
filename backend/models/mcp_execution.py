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


class ExecutorSender(_Wire):
    """Who sent this request, and proof that its contents are what they sent.

    Present on *every* request. The certificate is a service certificate —
    :func:`infrastructure.mcp_certificate.service_name` reads which component —
    and the signature covers
    :func:`infrastructure.mcp_certificate.request_digest`, which includes the
    connection spec.

    That last part is why this exists alongside :class:`ExecutorCredential` on a
    call. A tool certificate's grant names an ``mcp_server_id``; it says nothing
    about the command or URL the proxy would actually reach. Signing the
    resolved spec is what stops a request from keeping a valid grant while
    pointing the proxy somewhere else.

    Attributes:
        certificate_pem: The sending component's service certificate.
        signature: Base64 of the DER-encoded ECDSA signature over the request
            digest.
        nonce: The per-request random value that went into the digest.
        timestamp: When the signature was made; bounds replay.
    """

    certificate_pem: str
    signature: str
    nonce: str
    timestamp: datetime


class ExecutorListToolsRequest(_Wire):
    """Ask the proxy what one registered server advertises.

    No tool certificate: a listing is not authorized by any task's grant. What
    it does need is the sender block — the proxy will launch a command from
    this spec, so the request has to be provably one the backend sent.

    Attributes:
        connection: The server to query.
        sender: Who is asking, and proof the spec is unaltered.
    """

    connection: ConnectionSpec
    sender: ExecutorSender


class ExecutorCallToolRequest(_Wire):
    """Ask the proxy to invoke one tool on one registered server.

    Two signatures, answering two questions. ``sender`` says the backend sent
    exactly this request; ``credential`` says a live task grant covers exactly
    this tool. Neither implies the other.

    Attributes:
        connection: The server to call.
        mcp_server_id: Id of the registered server, as the grant names it. Not
            in the sender's digest and it does not need to be: the
            proof-of-possession digest covers it, so altering it in flight
            invalidates the credential's own signature.
        tool_name: Name of the tool to invoke.
        arguments: Arguments matching the tool's input schema, covered by both
            signatures.
        session_id: The ADK session the call belongs to, needed to recompute
            the proof-of-possession digest.
        sender: Who is asking, and proof the request is unaltered.
        credential: The tool certificate backing the call.
        elicit: Whether the backend will answer the server's elicitation
            requests. Only then does the proxy advertise the capability and
            relay a request as an ``elicit`` frame (see
            :class:`ExecutorCallFrame`). Not signed: all it changes is whether
            the server may ask a question, never what is called.
    """

    connection: ConnectionSpec
    mcp_server_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    session_id: str
    sender: ExecutorSender
    credential: ExecutorCredential | None = None
    elicit: bool = False


class ExecutorCallFrame(_Wire):
    """One message the proxy sends on ``/call-tool``'s WebSocket.

    A call is a WebSocket rather than one request because the server may stop
    mid-call to ask a person something (an MCP elicitation): the question goes
    down the socket and the answer (:class:`ExecutorElicitationAnswer`) comes
    back up the same one, so whichever proxy replica took the call is the one
    the answer reaches. The proxy sends any number of ``elicit`` frames and
    ends with exactly one ``result`` or ``error`` frame -- also for a call it
    refuses before starting.

    Attributes:
        type: ``elicit`` (a question to answer on the same socket), ``result``
            (the call finished), or ``error`` (it was refused or could not be
            made).
        key: For ``elicit``, the handle the answer is sent back under.
        params: For ``elicit``, the server's ``elicitation/create`` parameters
            as an MCP wire type.
        result: For ``result``, the raw ``tools/call`` result as an MCP wire
            type.
        code: For ``error``, the machine-readable error code.
        message: For ``error``, a caller-safe explanation.
    """

    type: Literal["elicit", "result", "error"]
    key: str | None = None
    params: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    code: str | None = None
    message: str | None = None


class ExecutorElicitationAnswer(_Wire):
    """The backend's answer to one ``elicit`` frame, sent on the call's socket.

    Unsigned: it travels on the mutually authenticated connection the signed
    call was made over, and can only answer that call's own questions.

    Attributes:
        key: The ``key`` of the ``elicit`` frame being answered.
        result: The answer, an MCP ``ElicitResult`` wire type.
    """

    key: str
    result: dict[str, Any]


class ExecutorTestCallToolRequest(_Wire):
    """Ask the proxy to invoke one tool of a script being tested.

    A test run from the MCP server form has no task behind it, so there is no
    grant to present -- only the sender block, as for a listing. The proxy
    confines it to script runners, whose listing already executes the whole
    script under the same sender check, so this adds nothing a listing could
    not already do.

    Attributes:
        connection: The script runner to launch.
        tool_name: Name of the tool to invoke.
        arguments: Arguments for the tool, covered by the sender signature.
        sender: Who is asking, and proof the request is unaltered.
    """

    connection: ConnectionSpec
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    sender: ExecutorSender


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
