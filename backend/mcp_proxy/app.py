"""The MCP proxy's HTTP surface: two operations and a liveness probe.

Deliberately small. Everything that decides *whether* an operation may happen
lives in the backend; what happens here is the evidence check in
:mod:`mcp_proxy.auth`, and then the transport in
:mod:`infrastructure.mcp_client`.

The root CA's public certificate is read once at startup, from the read-only
volume the backend published it to. If it is not there, the process refuses to
start rather than coming up unable to verify anything -- which would look
healthy while failing every request.

Responses use the same ``{meta, data, error}`` envelope as the public API, so a
failure reads the same way on both sides of the hop and the request id is in
the logs of both. That is the one place this package borrows from the backend's
own models; a future split of the sandbox's dependencies would start by cutting
it.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography import x509
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config import get_settings
from infrastructure import mcp_client
from infrastructure.mcp_ca import McpCaError, certificate_from_pem
from infrastructure.mcp_executor import CALL_OPERATION, LIST_OPERATION
from infrastructure.mcp_transport_tls import proxy_server_credentials
from mcp_proxy.auth import ProxyAuthError, verify_call_credential, verify_sender
from middleware.envelope import RequestContextMiddleware
from models.mcp_execution import (
    ExecutorCallToolRequest,
    ExecutorCallToolResponse,
    ExecutorListToolsRequest,
    ExecutorListToolsResponse,
    spec_to_connection,
)
from models.response import ApiError, ApiMeta, ApiResponse
from repositories.exceptions import McpConnectionError

logger = logging.getLogger(__name__)

#: Where the loaded root is kept for the lifetime of the process. A module-level
#: holder rather than app state so the route functions stay plain.
_root: dict[str, x509.Certificate] = {}


def load_root_certificate() -> x509.Certificate:
    """Return the root CA the backend published, loading it on first use.

    Returns:
        The parsed root certificate.

    Raises:
        McpCaError: If the file is missing or unreadable. Fatal on purpose: a
            proxy that cannot verify anything must not answer requests.
    """
    cached = _root.get("certificate")
    if cached is not None:
        return cached
    path = proxy_server_credentials().ca_certificate
    try:
        certificate = certificate_from_pem(path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError) as exc:
        raise McpCaError(
            f"Cannot read the root certificate at {path}; the backend publishes "
            "it at startup and this process mounts that directory read-only"
        ) from exc
    _root["certificate"] = certificate
    return certificate


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Load the root certificate before the first request can arrive."""
    load_root_certificate()
    logger.info("MCP proxy ready; trusting the root published by the backend")
    yield


app = FastAPI(title="A2Flow MCP proxy", lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)


def _meta(request: Request) -> ApiMeta:
    """Build the envelope's metadata block for the current request.

    Args:
        request: The incoming request, carrying the middleware's stamps.

    Returns:
        The metadata block.
    """
    return ApiMeta(
        request_id=request.state.request_id,
        received_at=request.state.received_at,
        responded_at=datetime.now(UTC),
    )


def _error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    """Build an error envelope.

    Args:
        request: The incoming request.
        status: HTTP status to answer with.
        code: Machine-readable error code.
        message: Caller-safe explanation.

    Returns:
        The JSON response.
    """
    body = ApiResponse[Any](
        meta=_meta(request), data=None, error=ApiError(code=code, message=message)
    )
    return JSONResponse(
        status_code=status, content=body.model_dump(mode="json", by_alias=True)
    )


def _signature_window() -> timedelta:
    """Return how stale a presented signature may be.

    The same tolerance the backend's own policy layer applies, so a signature
    the gateway accepted is not then refused one hop later for being late.

    Returns:
        The accepted clock-skew window.
    """
    return timedelta(seconds=get_settings().mcp_tool_cert_signature_window_seconds)


@app.get("/health")
async def health(request: Request) -> ApiResponse[dict[str, str]]:
    """Report that the process is up and holds a root to verify against.

    Reaching this endpoint at all already required a client certificate this
    deployment issued, so there is nothing further to check.

    Args:
        request: The incoming request.

    Returns:
        A ``{"status": "ok"}`` envelope.
    """
    load_root_certificate()
    return ApiResponse[dict[str, str]](meta=_meta(request), data={"status": "ok"})


@app.post("/list-tools")
async def list_tools(body: ExecutorListToolsRequest, request: Request) -> JSONResponse:
    """Return what one registered MCP server advertises.

    Args:
        body: The connection to query and the sender block backing the request.
        request: The incoming request.

    Returns:
        The tool list, or an error envelope.
    """
    connection_json = body.connection.model_dump(mode="json")
    try:
        sender = verify_sender(
            body.sender,
            ca_certificate=load_root_certificate(),
            operation=LIST_OPERATION,
            connection=connection_json,
            tool_name="",
            arguments={},
            now=datetime.now(UTC),
            window=_signature_window(),
        )
    except ProxyAuthError as exc:
        logger.warning("Refused a listing: %s", exc.message)
        return _error(request, 403, "MCP_PROXY_FORBIDDEN", exc.message)

    logger.info(
        "Listing tools for %s on behalf of %s", body.connection.transport, sender
    )
    try:
        tools = await mcp_client.list_server_tools(spec_to_connection(body.connection))
    except McpConnectionError as exc:
        return _error(request, 502, "MCP_UNREACHABLE", exc.reason)

    data = ExecutorListToolsResponse(
        tools=[tool.model_dump(mode="json", by_alias=True) for tool in tools]
    )
    return JSONResponse(
        content=ApiResponse[ExecutorListToolsResponse](
            meta=_meta(request), data=data
        ).model_dump(mode="json", by_alias=True)
    )


@app.post("/call-tool")
async def call_tool(body: ExecutorCallToolRequest, request: Request) -> JSONResponse:
    """Invoke one tool on one registered MCP server.

    Both signatures are checked before anything is reached: the sender's, which
    covers the connection spec, and the tool certificate's, which covers this
    call and must grant this exact tool.

    Args:
        body: The call to make and the evidence backing it.
        request: The incoming request.

    Returns:
        The tool result, or an error envelope.
    """
    now = datetime.now(UTC)
    window = _signature_window()
    connection_json = body.connection.model_dump(mode="json")
    try:
        verify_sender(
            body.sender,
            ca_certificate=load_root_certificate(),
            operation=CALL_OPERATION,
            connection=connection_json,
            tool_name=body.tool_name,
            arguments=body.arguments,
            now=now,
            window=window,
        )
        verify_call_credential(
            body.credential,
            ca_certificate=load_root_certificate(),
            session_id=body.session_id,
            mcp_server_id=body.mcp_server_id,
            tool_name=body.tool_name,
            arguments=body.arguments,
            now=now,
            window=window,
        )
    except ProxyAuthError as exc:
        logger.warning(
            "Refused a call to %s on server %s: %s",
            body.tool_name,
            body.mcp_server_id,
            exc.message,
        )
        return _error(request, 403, "MCP_PROXY_FORBIDDEN", exc.message)

    try:
        result = await mcp_client.call_server_tool(
            spec_to_connection(body.connection), body.tool_name, body.arguments
        )
    except McpConnectionError as exc:
        return _error(request, 502, "MCP_UNREACHABLE", exc.reason)

    data = ExecutorCallToolResponse(
        result=result.model_dump(mode="json", by_alias=True)
    )
    return JSONResponse(
        content=ApiResponse[ExecutorCallToolResponse](
            meta=_meta(request), data=data
        ).model_dump(mode="json", by_alias=True)
    )
