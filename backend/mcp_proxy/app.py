"""The MCP proxy's HTTP surface: three operations and a liveness probe.

Deliberately small. Everything that decides *whether* an operation may happen
lives in the backend; what happens here is the evidence check in
:mod:`mcp_proxy.auth`, and then the transport in
:mod:`infrastructure.mcp_client`.

The root CA's public certificate is read once at startup, from the read-only
volume the backend published it to. If it is not there, the process refuses to
start rather than coming up unable to verify anything -- which would look
healthy while failing every request.

A tool call is a WebSocket rather than a request (see
:class:`models.mcp_execution.ExecutorCallFrame`): the server may stop mid-call
to ask a person something (an MCP elicitation), and the question and its answer
travel on the call's own connection. Nothing about a call outlives its socket,
so the proxy can run as any number of replicas.

HTTP responses use the same ``{meta, data, error}`` envelope as the public API, so a
failure reads the same way on both sides of the hop and the request id is in
the logs of both. That is the one place this package borrows from the backend's
own models; a future split of the sandbox's dependencies would start by cutting
it.
"""

import asyncio
import contextlib
import logging
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography import x509
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from mcp import types
from pydantic import ValidationError

from config import get_settings
from infrastructure import mcp_client
from infrastructure.mcp_ca import McpCaError, certificate_from_pem
from infrastructure.mcp_executor import (
    CALL_OPERATION,
    LIST_OPERATION,
    TEST_CALL_OPERATION,
)
from infrastructure.mcp_transport_tls import proxy_server_credentials
from infrastructure.script_runners import NODE_RUNNER, PYTHON_RUNNER
from mcp_proxy.auth import ProxyAuthError, verify_call_credential, verify_sender
from middleware.envelope import RequestContextMiddleware
from models.mcp_execution import (
    ExecutorCallFrame,
    ExecutorCallToolRequest,
    ExecutorCallToolResponse,
    ExecutorElicitationAnswer,
    ExecutorListToolsRequest,
    ExecutorListToolsResponse,
    ExecutorTestCallToolRequest,
    StdioConnectionSpec,
    spec_to_connection,
)
from models.response import ApiError, ApiMeta, ApiResponse
from repositories.exceptions import McpConnectionError

logger = logging.getLogger(__name__)

#: Where the loaded root is kept for the lifetime of the process. A module-level
#: holder rather than app state so the route functions stay plain.
_root: dict[str, x509.Certificate] = {}

#: Seconds this side waits for an answer beyond the backend's own limit, so the
#: backend -- which records the question as expired -- is the one that gives up.
_ANSWER_GRACE_SECONDS = 30

#: Bytes of randomness in an ``elicit`` frame's key.
_ANSWER_KEY_BYTES = 16


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


@app.websocket("/call-tool")
async def call_tool(websocket: WebSocket) -> None:
    """Invoke one tool on one registered MCP server, over a WebSocket.

    The backend sends the call (:class:`ExecutorCallToolRequest`) as the first
    message. Both signatures are checked before anything is reached: the
    sender's, which covers the connection spec, and the tool certificate's,
    which covers this call and must grant this exact tool. From then on the
    proxy sends :class:`ExecutorCallFrame` messages -- an ``elicit`` frame per
    question the server asks, answered by an :class:`ExecutorElicitationAnswer`
    on the same socket, then one ``result`` or ``error`` -- and closes. A
    refusal is an ``error`` frame too.

    Args:
        websocket: The connection, already mutually authenticated by TLS.
    """
    await websocket.accept()
    try:
        body = ExecutorCallToolRequest.model_validate_json(
            await websocket.receive_text()
        )
    except ValidationError:
        await _finish(
            websocket,
            ExecutorCallFrame(
                type="error", code="VALIDATION_ERROR", message="not a tool call"
            ),
        )
        return
    except WebSocketDisconnect:
        return
    now = datetime.now(UTC)
    window = _signature_window()
    try:
        verify_sender(
            body.sender,
            ca_certificate=load_root_certificate(),
            operation=CALL_OPERATION,
            connection=body.connection.model_dump(mode="json"),
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
        await _finish(
            websocket,
            ExecutorCallFrame(
                type="error", code="MCP_PROXY_FORBIDDEN", message=exc.message
            ),
        )
        return
    await _relay_call(websocket, body)


async def _relay_call(websocket: WebSocket, body: ExecutorCallToolRequest) -> None:
    """Run one verified call, relaying the server's questions over ``websocket``.

    The call runs in its own task -- the transport's task group must enter and
    exit in one task -- while this one reads the backend's answers. If the
    backend goes away, or sends something that is not an answer, the call is
    cancelled.

    Args:
        websocket: The accepted connection.
        body: The verified call.
    """
    answers: dict[str, asyncio.Future[types.ElicitResult]] = {}

    async def ask(params: types.ElicitRequestParams) -> types.ElicitResult:
        key = secrets.token_urlsafe(_ANSWER_KEY_BYTES)
        answer: asyncio.Future[types.ElicitResult] = (
            asyncio.get_running_loop().create_future()
        )
        answers[key] = answer
        await websocket.send_text(
            ExecutorCallFrame(
                type="elicit",
                key=key,
                params=params.model_dump(mode="json", by_alias=True, exclude_none=True),
            ).model_dump_json(by_alias=True, exclude_none=True)
        )
        limit = get_settings().mcp_elicitation_timeout_seconds + _ANSWER_GRACE_SECONDS
        try:
            return await asyncio.wait_for(answer, limit)
        except TimeoutError:
            return types.ElicitResult(action="cancel")
        finally:
            answers.pop(key, None)

    async def read_answers() -> None:
        while True:
            message = ExecutorElicitationAnswer.model_validate_json(
                await websocket.receive_text()
            )
            answer = answers.get(message.key)
            if answer is not None and not answer.done():
                answer.set_result(types.ElicitResult.model_validate(message.result))

    call = asyncio.create_task(_call(body, ask if body.elicit else None))
    reader = asyncio.create_task(read_answers())
    try:
        await asyncio.wait({call, reader}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        reader.cancel()
        abandoned = not call.done()
        if abandoned:
            call.cancel()
    if abandoned:
        # The reader ended first: the backend went away, or broke the protocol.
        await asyncio.wait({call})
        failure = None if reader.cancelled() else reader.exception()
        if failure is not None and not isinstance(failure, WebSocketDisconnect):
            logger.warning("Abandoned a call to %s: %s", body.tool_name, failure)
            await _finish(
                websocket,
                ExecutorCallFrame(
                    type="error", code="VALIDATION_ERROR", message="not an answer"
                ),
            )
        return
    await _finish(websocket, call.result())


async def _call(
    body: ExecutorCallToolRequest, ask: mcp_client.ElicitHandler | None
) -> ExecutorCallFrame:
    """Make the call and return the frame that ends it.

    Args:
        body: The verified call.
        ask: Relays the server's questions, or ``None`` to let it ask none.

    Returns:
        A ``result`` frame, or an ``error`` frame for any failure.
    """
    try:
        result = await mcp_client.call_server_tool(
            spec_to_connection(body.connection),
            body.tool_name,
            body.arguments,
            on_elicit=ask,
        )
    except McpConnectionError as exc:
        return ExecutorCallFrame(
            type="error", code="MCP_UNREACHABLE", message=exc.reason
        )
    except Exception:
        # Without a frame the backend would wait forever for one.
        logger.exception("A call to %s failed unexpectedly", body.tool_name)
        return ExecutorCallFrame(
            type="error", code="INTERNAL_ERROR", message="the call failed"
        )
    return ExecutorCallFrame(
        type="result", result=result.model_dump(mode="json", by_alias=True)
    )


async def _finish(websocket: WebSocket, frame: ExecutorCallFrame) -> None:
    """Send the frame that ends a call and close, if the backend is still there.

    Args:
        websocket: The accepted connection.
        frame: The ``result`` or ``error`` frame.
    """
    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
        await websocket.send_text(
            frame.model_dump_json(by_alias=True, exclude_none=True)
        )
        await websocket.close()


#: The ``args`` tail a script runner is launched with -- the only thing
#: ``/test-call-tool`` will start.
_SCRIPT_RUNNERS = frozenset({str(PYTHON_RUNNER), str(NODE_RUNNER)})


@app.post("/test-call-tool")
async def test_call_tool(
    body: ExecutorTestCallToolRequest, request: Request
) -> JSONResponse:
    """Invoke one tool of a script being tested from the MCP server form.

    No tool certificate: a test run has no task behind it. The sender check
    alone is what ``/list-tools`` relies on too, and a listing of a script
    already executes all of it, so confining this to script runners adds
    nothing a listing could not already do.

    Args:
        body: The runner to launch, the call to make, and the sender block.
        request: The incoming request.

    Returns:
        The tool result, or an error envelope.
    """
    connection_json = body.connection.model_dump(mode="json")
    try:
        verify_sender(
            body.sender,
            ca_certificate=load_root_certificate(),
            operation=TEST_CALL_OPERATION,
            connection=connection_json,
            tool_name=body.tool_name,
            arguments=body.arguments,
            now=datetime.now(UTC),
            window=_signature_window(),
        )
    except ProxyAuthError as exc:
        logger.warning("Refused a test call to %s: %s", body.tool_name, exc.message)
        return _error(request, 403, "MCP_PROXY_FORBIDDEN", exc.message)
    if not (
        isinstance(body.connection, StdioConnectionSpec)
        and body.connection.args[-1:]
        and body.connection.args[-1] in _SCRIPT_RUNNERS
    ):
        logger.warning("Refused a test call to %s: not a script", body.tool_name)
        return _error(
            request, 403, "MCP_PROXY_FORBIDDEN", "only a script runner can be tested"
        )

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
