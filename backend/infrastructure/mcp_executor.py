"""Where a proxied MCP operation is actually carried out.

:class:`infrastructure.mcp_gateway.McpGateway` decides *whether* a call may
happen; this decides *where*. Two implementations sit behind one protocol:

:class:`LocalMcpExecutor`
    Opens the connection in this process, as A2Flow always did. The default,
    and what keeps a plain ``uvicorn main:app`` and the test suite working with
    nothing else running.

:class:`RemoteMcpExecutor`
    Hands the operation to the MCP proxy over HTTPS. Selected by setting
    ``MCP_PROXY_URL``, which is what ``compose.yml`` does.

**Why the second one exists.** A registered MCP server is third-party code: a
stdio one is launched as a child process, a remote one is reached over the
network. Doing either in the backend process puts that code beside the database
credentials, the secret encryption key, the Vault credentials and the LLM API
keys. Moving it behind an HTTPS hop puts a container boundary there instead,
and the container on the far side holds none of those.

**What crosses the wire.** A connection spec whose secrets are already
resolved -- the proxy cannot resolve them, having neither the Fernet key nor a
database -- plus, for a call, the tool certificate and the proof of possession
that backs it. The certificate goes over twice, on purpose:

* as the **TLS client certificate**, so nothing without one this deployment
  issued can open a connection to the proxy at all; and
* in the **request body**, where the proxy re-verifies it against the root and
  checks the proof of possession, which binds it to *this* call.

The second is not redundant. A TLS session authenticates a connection, not the
operations that flow down it, and the proxy cannot read the peer certificate
from the ASGI scope in any case -- uvicorn does not implement the ASGI TLS
extension. The proof of possession is what ties the certificate to the specific
server, tool, and arguments being asked for, which is the property that
actually matters.

Every failure normalizes to :class:`repositories.exceptions.McpConnectionError`,
the same exception the local path raises, so the gateway's error handling does
not care which executor it is holding.
"""

import base64
import logging
import os
import ssl
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Any, Protocol

import httpx
from mcp import types
from models.mcp_execution import (
    ExecutorCallToolRequest,
    ExecutorCredential,
    ExecutorListToolsRequest,
    connection_to_spec,
)

from config import get_settings
from infrastructure import mcp_client
from infrastructure.mcp_certificate import McpClientCredential
from infrastructure.mcp_client import McpConnection
from infrastructure.mcp_transport_tls import backend_client_credentials
from repositories.exceptions import McpConnectionError

logger = logging.getLogger(__name__)

#: How many per-certificate TLS contexts are kept. A run reuses one certificate
#: for every call its task makes, so even a handful covers concurrent runs; the
#: cost of a miss is one keypair load, not a network round-trip.
_SSL_CONTEXT_CACHE_SIZE = 32

#: Label used when a remote failure has no server name to attribute it to.
_PROXY_LABEL = "MCP proxy"

#: Cache key for the backend's own service identity. A NUL byte keeps it out of
#: the space of PEM texts, which are ASCII-armoured, so it can never collide
#: with a certificate's own key.
_SERVICE_CACHE_KEY = "\0service"


class McpExecutor(Protocol):
    """Carries out one prepared MCP operation, wherever it runs."""

    async def list_tools(self, connection: McpConnection) -> list[types.Tool]:
        """Return the tools the server behind ``connection`` advertises.

        No credential: a listing is not authorized by any task's grant, so the
        remote implementation authenticates as the backend itself.

        Args:
            connection: The server to query, with secrets already resolved.

        Returns:
            The server's tool list.

        Raises:
            McpConnectionError: If the server cannot be reached or launched, or
                the operation could not be carried out at all.
        """
        ...

    async def call_tool(
        self,
        connection: McpConnection,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        session_id: str,
        credential: McpClientCredential | None,
    ) -> types.CallToolResult:
        """Invoke one tool on the server behind ``connection``.

        Args:
            connection: The server to call, with secrets already resolved.
            tool_name: Name of the tool to invoke.
            arguments: Arguments matching the tool's input schema.
            session_id: The ADK session the call belongs to. Covered by the
                proof-of-possession signature, so the far side needs it to
                recompute the digest.
            credential: The tool certificate backing the call, or ``None``.
                The gateway's policy chain has already refused every call that
                reaches here without one, so ``None`` only occurs where no
                policy chain is configured — a directly constructed gateway in
                a test.

        Returns:
            The raw ``tools/call`` result. A tool that reports a failure does so
            inside it, with ``isError`` set, rather than by raising.

        Raises:
            McpConnectionError: If the server cannot be reached or launched, or
                the operation could not be carried out at all.
        """
        ...


class LocalMcpExecutor:
    """Opens the connection in this process.

    What A2Flow did before the proxy existed, kept as the default so a local
    checkout needs one process rather than two. The credential is accepted and
    ignored: it authorizes the call, and authorization already happened in the
    gateway — there is no channel here for it to authenticate over.
    """

    async def list_tools(self, connection: McpConnection) -> list[types.Tool]:
        """Query the server's tool catalog directly.

        Args:
            connection: The server to query.

        Returns:
            The server's tool list.

        Raises:
            McpConnectionError: If the server cannot be reached or launched.
        """
        return await mcp_client.list_server_tools(connection)

    async def call_tool(
        self,
        connection: McpConnection,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        session_id: str,
        credential: McpClientCredential | None,
    ) -> types.CallToolResult:
        """Invoke the tool directly.

        Args:
            connection: The server to call.
            tool_name: Name of the tool to invoke.
            arguments: Arguments matching the tool's input schema.
            session_id: Unused; there is no far side to prove anything to.
            credential: Unused, for the same reason.

        Returns:
            The raw ``tools/call`` result.

        Raises:
            McpConnectionError: If the server cannot be reached or launched.
        """
        return await mcp_client.call_server_tool(connection, tool_name, arguments)


def _write_temporary_pem(directory: Path, name: str, pem: str) -> Path:
    """Write one PEM into a private directory, readable only by this process.

    ``ssl`` has no in-memory equivalent of
    :meth:`ssl.SSLContext.load_cert_chain`, so a certificate that lives in the
    database has to reach the filesystem to be presented at all. The directory
    is created with owner-only permissions and removed as soon as the context
    has read from it.

    Args:
        directory: The private directory to write into.
        name: File name within it.
        pem: The PEM text.

    Returns:
        The path written.
    """
    path = directory / name
    path.write_text(pem, encoding="ascii")
    os.chmod(path, 0o600)
    return path


def _file_context(certificate: Path, private_key: Path, ca: Path) -> ssl.SSLContext:
    """Build a TLS context from material already on disk.

    Args:
        certificate: The client certificate to present.
        private_key: Its key.
        ca: The root the proxy's own certificate must chain to.

    Returns:
        A context with the material loaded.
    """
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(ca))
    context.load_cert_chain(str(certificate), str(private_key))
    return context


def _client_context(
    certificate_pem: str, private_key_pem: str, ca: Path
) -> ssl.SSLContext:
    """Build a TLS context presenting a certificate that lives in the database.

    Args:
        certificate_pem: The client certificate to present.
        private_key_pem: Its private key.
        ca: The root certificate the proxy's own certificate must chain to.

    Returns:
        A context with the material already loaded; the temporary files it was
        read from are gone by the time this returns.
    """
    with tempfile.TemporaryDirectory() as staging:
        directory = Path(staging)
        os.chmod(directory, 0o700)
        certificate_path = _write_temporary_pem(
            directory, "client.crt", certificate_pem
        )
        key_path = _write_temporary_pem(directory, "client.key", private_key_pem)
        # load_cert_chain reads eagerly, so the files are not needed after this.
        return _file_context(certificate_path, key_path, ca)


class RemoteMcpExecutor:
    """Hands the operation to the MCP proxy over mutually authenticated HTTPS.

    One TLS context per client certificate, kept in a small LRU: a run presents
    the same tool certificate for every call its task makes, so the keypair is
    loaded once rather than per call.
    """

    def __init__(self, base_url: str) -> None:
        """Initialize the executor.

        Args:
            base_url: Where the proxy is reached, e.g.
                ``https://mcp-proxy:8443``.
        """
        self._base_url = base_url.rstrip("/")
        self._contexts: OrderedDict[str, ssl.SSLContext] = OrderedDict()

    def _context_for(self, credential: McpClientCredential | None) -> ssl.SSLContext:
        """Return the TLS context this operation is made under.

        Args:
            credential: The tool certificate backing a call, or ``None`` for a
                listing — which no task authorizes, so the backend's own
                service certificate is presented instead.

        Returns:
            The context, from the cache when the same certificate was used
            before.

        Raises:
            McpConnectionError: If the material cannot be read. A missing
                backend identity means startup never provisioned it, which is a
                deployment fault rather than something the call can recover
                from.
        """
        paths = backend_client_credentials()
        material = (
            (credential.certificate_pem, credential.private_key_pem)
            if credential is not None and credential.private_key_pem is not None
            else None
        )
        key = material[0] if material is not None else _SERVICE_CACHE_KEY
        cached = self._contexts.get(key)
        if cached is not None:
            self._contexts.move_to_end(key)
            return cached
        try:
            if material is not None:
                context = _client_context(
                    material[0], material[1], paths.ca_certificate
                )
            else:
                context = _file_context(
                    paths.certificate, paths.private_key, paths.ca_certificate
                )
        except (OSError, ssl.SSLError) as exc:
            raise McpConnectionError(
                _PROXY_LABEL, f"cannot load this deployment's TLS material: {exc}"
            ) from exc
        self._contexts[key] = context
        if len(self._contexts) > _SSL_CONTEXT_CACHE_SIZE:
            self._contexts.popitem(last=False)
        return context

    async def _post(
        self, path: str, body: dict[str, Any], context: ssl.SSLContext, timeout: float
    ) -> dict[str, Any]:
        """Send one request to the proxy and unwrap its envelope.

        Args:
            path: Endpoint path, e.g. ``/call-tool``.
            body: JSON request body.
            context: The TLS context to connect under.
            timeout: Upper bound for the whole exchange, taken from the
                connection so a stdio spawn keeps its longer budget.

        Returns:
            The envelope's ``data`` object.

        Raises:
            McpConnectionError: If the proxy cannot be reached, refuses the
                request, or answers with an error envelope.
        """
        verify_name = get_settings().mcp_proxy_server_name
        try:
            async with httpx.AsyncClient(
                verify=context,
                timeout=timeout,
                follow_redirects=False,
                headers={"Host": verify_name},
            ) as client:
                response = await client.post(f"{self._base_url}{path}", json=body)
        except httpx.HTTPError as exc:
            raise McpConnectionError(_PROXY_LABEL, str(exc)) from exc

        try:
            envelope = response.json()
        except ValueError as exc:
            raise McpConnectionError(
                _PROXY_LABEL, f"answered with a non-JSON body ({response.status_code})"
            ) from exc
        error = envelope.get("error")
        if error is not None:
            raise McpConnectionError(_PROXY_LABEL, str(error.get("message", error)))
        if response.status_code >= 400:
            raise McpConnectionError(_PROXY_LABEL, f"answered {response.status_code}")
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise McpConnectionError(_PROXY_LABEL, "answered without a result")
        return data

    async def list_tools(self, connection: McpConnection) -> list[types.Tool]:
        """Ask the proxy for the server's tool catalog.

        Args:
            connection: The server to query, with secrets already resolved.

        Returns:
            The server's tool list.

        Raises:
            McpConnectionError: If the proxy or the server cannot be reached.
        """
        request = ExecutorListToolsRequest(connection=connection_to_spec(connection))
        data = await self._post(
            "/list-tools",
            request.model_dump(mode="json", by_alias=True),
            self._context_for(None),
            connection.timeout_seconds,
        )
        return [types.Tool.model_validate(tool) for tool in data.get("tools", [])]

    async def call_tool(
        self,
        connection: McpConnection,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        session_id: str,
        credential: McpClientCredential | None,
    ) -> types.CallToolResult:
        """Ask the proxy to invoke one tool.

        Args:
            connection: The server to call, with secrets already resolved.
            tool_name: Name of the tool to invoke.
            arguments: Arguments matching the tool's input schema.
            session_id: The ADK session, needed to recompute the signed digest.
            credential: The tool certificate backing the call.

        Returns:
            The raw ``tools/call`` result.

        Raises:
            McpConnectionError: If the proxy refuses the call, or the server
                cannot be reached.
        """
        request = ExecutorCallToolRequest(
            connection=connection_to_spec(connection),
            tool_name=tool_name,
            arguments=arguments,
            session_id=session_id,
            credential=(
                None
                if credential is None
                else ExecutorCredential(
                    certificate_pem=credential.certificate_pem,
                    signature=base64.b64encode(credential.signature).decode("ascii"),
                    nonce=credential.nonce,
                    timestamp=credential.timestamp,
                )
            ),
        )
        data = await self._post(
            "/call-tool",
            request.model_dump(mode="json", by_alias=True),
            self._context_for(credential),
            connection.timeout_seconds,
        )
        return types.CallToolResult.model_validate(data["result"])


def get_mcp_executor() -> McpExecutor:
    """Return the executor this deployment runs MCP operations through.

    Not cached: :class:`RemoteMcpExecutor` holds a TLS-context cache keyed by
    certificate, and the gateway singleton that owns it is built once anyway.
    Reading the setting per construction keeps a test free to flip
    ``MCP_PROXY_URL`` without clearing a second cache.

    Returns:
        A remote executor when ``MCP_PROXY_URL`` is set, else the local one.
    """
    proxy_url = get_settings().mcp_proxy_url
    if not proxy_url:
        return LocalMcpExecutor()
    logger.info("MCP operations run in the MCP proxy at %s", proxy_url)
    return RemoteMcpExecutor(proxy_url)
