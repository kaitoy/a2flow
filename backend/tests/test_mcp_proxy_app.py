"""Tests for what the MCP proxy refuses, and one real mutually authenticated hop.

The authorization tests drive the ASGI app directly: TLS is a separate layer
with its own guarantee, and every check this module covers is deliberately one
that does *not* depend on it — uvicorn does not expose the peer certificate to a
handler, so the app's rules have to stand on the request body alone.

The last test closes that gap the only way it can be closed: it starts the real
listener with the real material and drives it through ``RemoteMcpExecutor``.
"""

import asyncio
import base64
import contextlib
import ipaddress
import socket
import ssl
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from fastapi.testclient import TestClient
from mcp import types

from infrastructure import mcp_client
from infrastructure.mcp_ca import (
    HASH_ALGORITHM,
    RootCertificateAuthority,
    build_root_certificate,
    certificate_to_pem,
    generate_key,
    private_key_to_pem,
    sign_leaf_certificate,
)
from infrastructure.mcp_certificate import (
    BACKEND_SERVICE_NAME,
    CertificateBinding,
    McpClientCredential,
    arguments_digest,
    build_binding_urn,
    build_service_urn,
    build_tool_urn,
    pop_digest,
    request_digest,
    sign_pop_digest,
)
from infrastructure.mcp_client import HttpConnection, McpConnection, StdioConnection
from infrastructure.mcp_executor import (
    CALL_OPERATION,
    LIST_OPERATION,
    RemoteMcpExecutor,
)
from infrastructure.mcp_transport_tls import (
    CA_FILE,
    CLIENT_CERT_FILE,
    CLIENT_KEY_FILE,
    SERVER_CERT_FILE,
    SERVER_KEY_FILE,
    TransportCredentials,
    backend_client_credentials,
)
from models.mcp_execution import connection_to_spec
from repositories.exceptions import McpConnectionError

SESSION_ID = "sess-proxy"
SERVER_ID = "srv-1"
TOOL_NAME = "read_file"
ARGUMENTS: dict[str, Any] = {"path": "/etc/hosts"}
CONNECTION = HttpConnection(url="https://mcp.example.com/mcp")


@pytest.fixture
def ca() -> RootCertificateAuthority:
    """A throwaway root standing in for the deployment's own."""
    now = datetime.now(UTC)
    key = generate_key()
    return RootCertificateAuthority(
        ca_id="ca-1",
        certificate=build_root_certificate(
            key,
            common_name="Test root",
            not_before=now - timedelta(days=1),
            not_after=now + timedelta(days=365),
        ),
        private_key=key,
    )


@pytest.fixture
def tls_dir(
    ca: RootCertificateAuthority, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Publish the root the proxy verifies against, as the backend would."""
    published = tmp_path / "published"
    published.mkdir()
    (published / CA_FILE).write_text(
        certificate_to_pem(ca.certificate), encoding="ascii"
    )
    monkeypatch.setenv("MCP_PROXY_TLS_DIR", str(published))
    monkeypatch.setenv("MCP_BACKEND_TLS_DIR", str(tmp_path / "private"))
    return published


@pytest.fixture
def client(tls_dir: Path) -> Iterator[TestClient]:
    """The proxy app, with its cached root cleared between tests."""
    from mcp_proxy import app as proxy_app

    proxy_app._root.clear()
    with TestClient(proxy_app.app) as test_client:
        yield test_client
    proxy_app._root.clear()


def _service_leaf(
    ca: RootCertificateAuthority, name: str = BACKEND_SERVICE_NAME
) -> tuple[str, Any]:
    """Issue a service certificate and return its PEM with its key."""
    now = datetime.now(UTC)
    key = generate_key()
    leaf = sign_leaf_certificate(
        ca,
        public_key=key.public_key(),
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]),
        sans=[x509.UniformResourceIdentifier(build_service_urn(name))],
        not_before=now - timedelta(minutes=1),
        not_after=now + timedelta(hours=1),
        extended_key_usage=[ExtendedKeyUsageOID.CLIENT_AUTH],
    )
    return certificate_to_pem(leaf), key


def _tool_leaf(
    ca: RootCertificateAuthority,
    *,
    tools: tuple[tuple[str, str], ...] = ((SERVER_ID, TOOL_NAME),),
    not_after: datetime | None = None,
) -> tuple[str, Any]:
    """Issue a tool certificate granting the given tools."""
    now = datetime.now(UTC)
    key = generate_key()
    binding = CertificateBinding(
        tenant_id="t-1", execution_id="exec-1", task_id="task-1", approval_id="appr-1"
    )
    leaf = sign_leaf_certificate(
        ca,
        public_key=key.public_key(),
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "task-1")]),
        sans=[
            x509.UniformResourceIdentifier(build_binding_urn(binding)),
            *(
                x509.UniformResourceIdentifier(build_tool_urn(server, tool))
                for server, tool in tools
            ),
        ],
        not_before=now - timedelta(minutes=1),
        not_after=not_after or now + timedelta(hours=1),
    )
    return certificate_to_pem(leaf), key


def _sender(
    ca: RootCertificateAuthority,
    *,
    operation: str,
    connection: McpConnection = CONNECTION,
    tool_name: str = "",
    arguments: dict[str, Any] | None = None,
    name: str = BACKEND_SERVICE_NAME,
    certificate: tuple[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a signed sender block."""
    pem, key = certificate or _service_leaf(ca, name)
    nonce = "sender-nonce"
    timestamp = datetime.now(UTC)
    digest = request_digest(
        operation=operation,
        connection_hash=arguments_digest(
            connection_to_spec(connection).model_dump(mode="json")
        ),
        tool_name=tool_name,
        arguments_hash=arguments_digest(arguments or {}),
        nonce=nonce,
        timestamp=timestamp,
    )
    return {
        "certificatePem": pem,
        "signature": base64.b64encode(sign_pop_digest(key, digest)).decode("ascii"),
        "nonce": nonce,
        "timestamp": timestamp.isoformat(),
    }


def _credential(
    certificate: tuple[str, Any],
    *,
    server_id: str = SERVER_ID,
    tool_name: str = TOOL_NAME,
    arguments: dict[str, Any] | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Build a proof-of-possession block for a tool certificate."""
    pem, key = certificate
    nonce = "call-nonce"
    stamp = timestamp or datetime.now(UTC)
    digest = pop_digest(
        session_id=SESSION_ID,
        mcp_server_id=server_id,
        tool_name=tool_name,
        arguments=arguments if arguments is not None else ARGUMENTS,
        nonce=nonce,
        timestamp=stamp,
    )
    return {
        "certificatePem": pem,
        "signature": base64.b64encode(sign_pop_digest(key, digest)).decode("ascii"),
        "nonce": nonce,
        "timestamp": stamp.isoformat(),
    }


def _call_body(
    ca: RootCertificateAuthority,
    *,
    connection: McpConnection = CONNECTION,
    credential: dict[str, Any] | None,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a whole /call-tool body."""
    args = ARGUMENTS if arguments is None else arguments
    return {
        "connection": connection_to_spec(connection).model_dump(
            mode="json", by_alias=True
        ),
        "mcpServerId": SERVER_ID,
        "toolName": TOOL_NAME,
        "arguments": args,
        "sessionId": SESSION_ID,
        "sender": _sender(
            ca,
            operation=CALL_OPERATION,
            connection=connection,
            tool_name=TOOL_NAME,
            arguments=args,
        ),
        "credential": credential,
    }


@pytest.fixture
def reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the transport succeed, so only authorization decides the outcome."""

    async def _list(connection: McpConnection) -> list[types.Tool]:
        return [types.Tool(name=TOOL_NAME, inputSchema={})]

    async def _call(
        connection: McpConnection, tool_name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        return types.CallToolResult(content=[types.TextContent(type="text", text="ok")])

    monkeypatch.setattr(mcp_client, "list_server_tools", _list)
    monkeypatch.setattr(mcp_client, "call_server_tool", _call)


def _forbidden(response: Any) -> str:
    """Assert a refusal and return its message."""
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "MCP_PROXY_FORBIDDEN"
    assert body["data"] is None
    return str(body["error"]["message"])


# --------------------------------------------------------------------------
# Listing
# --------------------------------------------------------------------------


def test_a_listing_signed_by_the_backend_is_served(
    client: TestClient, ca: RootCertificateAuthority, reachable: None
) -> None:
    response = client.post(
        "/list-tools",
        json={
            "connection": connection_to_spec(CONNECTION).model_dump(
                mode="json", by_alias=True
            ),
            "sender": _sender(ca, operation=LIST_OPERATION),
        },
    )

    assert response.status_code == 200
    assert [t["name"] for t in response.json()["data"]["tools"]] == [TOOL_NAME]


def test_a_listing_from_another_deployment_is_refused(
    client: TestClient, ca: RootCertificateAuthority, reachable: None
) -> None:
    """Material signed by a root this proxy does not hold."""
    now = datetime.now(UTC)
    foreign_key = generate_key()
    foreign = RootCertificateAuthority(
        ca_id="ca-2",
        certificate=build_root_certificate(
            foreign_key,
            common_name="Someone else",
            not_before=now - timedelta(days=1),
            not_after=now + timedelta(days=365),
        ),
        private_key=foreign_key,
    )

    response = client.post(
        "/list-tools",
        json={
            "connection": connection_to_spec(CONNECTION).model_dump(
                mode="json", by_alias=True
            ),
            "sender": _sender(foreign, operation=LIST_OPERATION),
        },
    )

    assert "not a component of this deployment" in _forbidden(response)


def test_a_listing_whose_connection_was_altered_in_flight_is_refused(
    client: TestClient, ca: RootCertificateAuthority, reachable: None
) -> None:
    """The whole reason the sender signature covers the spec."""
    sender = _sender(ca, operation=LIST_OPERATION, connection=CONNECTION)
    tampered = StdioConnection(command="npx", args=["-y", "attacker-package"])

    response = client.post(
        "/list-tools",
        json={
            "connection": connection_to_spec(tampered).model_dump(
                mode="json", by_alias=True
            ),
            "sender": sender,
        },
    )

    assert "signature does not verify" in _forbidden(response)


def test_a_tool_certificate_cannot_ask_for_a_listing(
    client: TestClient, ca: RootCertificateAuthority, reachable: None
) -> None:
    """Only a component of this deployment may drive the proxy."""
    response = client.post(
        "/list-tools",
        json={
            "connection": connection_to_spec(CONNECTION).model_dump(
                mode="json", by_alias=True
            ),
            "sender": _sender(ca, operation=LIST_OPERATION, certificate=_tool_leaf(ca)),
        },
    )

    assert "not a component of this deployment" in _forbidden(response)


def test_a_listing_signature_cannot_be_replayed_as_a_call(
    client: TestClient, ca: RootCertificateAuthority, reachable: None
) -> None:
    """Which is what the operation name in the digest is for."""
    body = _call_body(ca, credential=_credential(_tool_leaf(ca)))
    body["sender"] = _sender(
        ca, operation=LIST_OPERATION, tool_name=TOOL_NAME, arguments=ARGUMENTS
    )

    response = client.post("/call-tool", json=body)

    assert "signature does not verify" in _forbidden(response)


# --------------------------------------------------------------------------
# Calling
# --------------------------------------------------------------------------


def test_a_granted_call_reaches_the_server(
    client: TestClient, ca: RootCertificateAuthority, reachable: None
) -> None:
    response = client.post(
        "/call-tool", json=_call_body(ca, credential=_credential(_tool_leaf(ca)))
    )

    assert response.status_code == 200
    assert response.json()["data"]["result"]["content"][0]["text"] == "ok"


def test_a_call_without_a_tool_certificate_is_refused(
    client: TestClient, ca: RootCertificateAuthority, reachable: None
) -> None:
    """Being the backend is not the same as holding a task's grant."""
    response = client.post("/call-tool", json=_call_body(ca, credential=None))

    assert "tool certificate is required" in _forbidden(response)


def test_a_call_the_certificate_does_not_grant_is_refused(
    client: TestClient, ca: RootCertificateAuthority, reachable: None
) -> None:
    certificate = _tool_leaf(ca, tools=((SERVER_ID, "write_file"),))

    response = client.post(
        "/call-tool", json=_call_body(ca, credential=_credential(certificate))
    )

    assert "does not grant" in _forbidden(response)


def test_an_expired_tool_certificate_is_refused(
    client: TestClient, ca: RootCertificateAuthority, reachable: None
) -> None:
    certificate = _tool_leaf(ca, not_after=datetime.now(UTC) - timedelta(seconds=30))

    response = client.post(
        "/call-tool", json=_call_body(ca, credential=_credential(certificate))
    )

    assert "has expired" in _forbidden(response)


def test_a_stale_proof_of_possession_is_refused(
    client: TestClient, ca: RootCertificateAuthority, reachable: None
) -> None:
    """The whole replay defence: a captured signature stops working."""
    credential = _credential(
        _tool_leaf(ca), timestamp=datetime.now(UTC) - timedelta(hours=1)
    )

    response = client.post("/call-tool", json=_call_body(ca, credential=credential))

    assert "outside the accepted time window" in _forbidden(response)


def test_a_credential_signed_for_different_arguments_is_refused(
    client: TestClient, ca: RootCertificateAuthority, reachable: None
) -> None:
    """The proof covers the arguments, so swapping them invalidates it."""
    credential = _credential(_tool_leaf(ca), arguments={"path": "/etc/shadow"})

    response = client.post("/call-tool", json=_call_body(ca, credential=credential))

    assert "not proven to belong to this caller" in _forbidden(response)


def test_a_service_certificate_cannot_stand_in_for_a_grant(
    client: TestClient, ca: RootCertificateAuthority, reachable: None
) -> None:
    """It authenticates a component; it authorizes no tool at all."""
    response = client.post(
        "/call-tool", json=_call_body(ca, credential=_credential(_service_leaf(ca)))
    )

    assert "tool certificate is not valid" in _forbidden(response)


def test_a_valid_grant_pointed_at_another_command_is_refused(
    client: TestClient, ca: RootCertificateAuthority, reachable: None
) -> None:
    """The gap the sender signature exists to close.

    The grant names a server id, which says nothing about the command the proxy
    would run. Swapping the connection spec keeps the credential valid and is
    caught by the sender signature instead.
    """
    body = _call_body(ca, credential=_credential(_tool_leaf(ca)))
    body["connection"] = connection_to_spec(
        StdioConnection(command="npx", args=["-y", "attacker-package"])
    ).model_dump(mode="json", by_alias=True)

    response = client.post("/call-tool", json=body)

    assert "signature does not verify" in _forbidden(response)


def test_an_unreachable_server_is_reported_as_a_bad_gateway(
    client: TestClient, ca: RootCertificateAuthority, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transport failure is not an authorization failure and must not read as one."""

    async def _call(
        connection: McpConnection, tool_name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        raise McpConnectionError("srv", "connection refused")

    monkeypatch.setattr(mcp_client, "call_server_tool", _call)

    response = client.post(
        "/call-tool", json=_call_body(ca, credential=_credential(_tool_leaf(ca)))
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MCP_UNREACHABLE"


# --------------------------------------------------------------------------
# One real mutually authenticated hop
# --------------------------------------------------------------------------


#: How many ports to try before giving up on getting one to ourselves.
_LISTENER_ATTEMPTS = 5


async def _stop(server: uvicorn.Server, task: asyncio.Task[None]) -> None:
    """Ask a listener to shut down and wait for it to unwind.

    Args:
        server: The running server.
        task: The task its ``serve()`` is running under.
    """
    server.should_exit = True
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(task, timeout=10)


def _free_port() -> int:
    """Return a port the OS says is free, on the IPv4 loopback.

    Deliberately without ``SO_REUSEADDR``: on Windows that option means what
    ``SO_REUSEPORT`` means elsewhere, letting a second socket bind an address
    already in use, so it would hide a collision rather than prevent one.
    ``SO_EXCLUSIVEADDRUSE``, where it exists, asks for the opposite.

    Even so this is only a hint. Windows lets a socket bound to ``127.0.0.1``
    coexist with one bound to ``0.0.0.0`` on the same port, and hands an
    incoming connection to either -- so the listener has to confirm it is the
    one being reached, which is what :func:`_preflight` is for.
    """
    with socket.socket() as probe:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:
            probe.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class _NotOurListener(Exception):
    """Raised when the port answers with a certificate from another issuer.

    Attributes:
        issuer: Who signed the certificate that came back.
    """

    def __init__(self, issuer: str) -> None:
        """Initialize the error.

        Args:
            issuer: Distinguished name of the unexpected issuer.
        """
        self.issuer = issuer
        super().__init__(issuer)


def _peer_issuer(port: int, credentials: TransportCredentials) -> str:
    """Return who signed the certificate the port presents, verifying nothing.

    Args:
        port: The port to ask.
        credentials: The client material to present, since the listener demands
            a client certificate.

    Returns:
        The issuer's distinguished name.
    """
    blind = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    blind.check_hostname = False
    blind.verify_mode = ssl.CERT_NONE
    blind.load_cert_chain(str(credentials.certificate), str(credentials.private_key))
    with (
        socket.create_connection(("127.0.0.1", port), timeout=10) as raw,
        blind.wrap_socket(raw) as tls,
    ):
        der = tls.getpeercert(True) or b""
    return x509.load_der_x509_certificate(der).issuer.rfc4514_string()


def _preflight(port: int, credentials: TransportCredentials) -> None:
    """Complete one real handshake, to prove the listener reached is ours.

    Presents a client certificate, because the listener demands one -- a probe
    without it is refused by design and would prove nothing.

    Args:
        port: The port the listener was given.
        credentials: The client material to present and the root to trust.

    Raises:
        _NotOurListener: If something answered with a certificate this
            deployment's root did not sign.
        ssl.SSLError: If the handshake failed for any other reason.
        OSError: If nothing answers.
    """
    context = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH, cafile=str(credentials.ca_certificate)
    )
    context.load_cert_chain(str(credentials.certificate), str(credentials.private_key))
    try:
        with (
            socket.create_connection(("127.0.0.1", port), timeout=10) as raw,
            context.wrap_socket(raw, server_hostname="127.0.0.1") as tls,
        ):
            assert tls.getpeercert() is not None
    except ssl.SSLError as exc:
        issuer = _peer_issuer(port, credentials)
        root = x509.load_pem_x509_certificate(credentials.ca_certificate.read_bytes())
        if issuer != root.subject.rfc4514_string():
            raise _NotOurListener(issuer) from exc
        raise


def _assert_material_agrees(ca_file: Path, server_file: Path) -> None:
    """Fail in setup if the published root does not vouch for the server leaf.

    A mismatch surfaces from a handshake as "unable to get local issuer
    certificate", which reads as a bug in the code under test rather than as a
    fixture that wrote two unrelated certificates.

    Args:
        ca_file: The root the client half will trust.
        server_file: The certificate the listener will present.
    """
    root = x509.load_pem_x509_certificate(ca_file.read_bytes())
    leaf = x509.load_pem_x509_certificate(server_file.read_bytes())
    assert leaf.issuer == root.subject, (
        f"{server_file} was issued by {leaf.issuer.rfc4514_string()!r}, but "
        f"{ca_file} is {root.subject.rfc4514_string()!r}"
    )
    public_key = root.public_key()
    assert isinstance(public_key, ec.EllipticCurvePublicKey)
    public_key.verify(
        leaf.signature, leaf.tbs_certificate_bytes, ec.ECDSA(HASH_ALGORITHM)
    )


@pytest.fixture
async def listener(
    ca: RootCertificateAuthority,
    tls_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reachable: None,
) -> AsyncIterator[str]:
    """Run the real listener with real material, and yield its base URL.

    The certificate names the loopback address rather than ``mcp-proxy`` so the
    handshake can verify what it is actually connected to. The address, not the
    name: ``localhost`` resolves to ``::1`` first on Windows, the listener binds
    IPv4 only, and a dual-stack server elsewhere on the machine holding that
    port on ``::1`` would answer instead — with its own certificate, which then
    fails to verify for reasons that have nothing to do with this code.
    """
    from mcp_proxy import app as proxy_app

    monkeypatch.setenv("MCP_PROXY_SERVER_NAME", "localhost")
    proxy_app._root.clear()

    now = datetime.now(UTC)
    server_key = generate_key()
    server_leaf = sign_leaf_certificate(
        ca,
        public_key=server_key.public_key(),
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]),
        sans=[
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        ],
        not_before=now - timedelta(minutes=1),
        not_after=now + timedelta(hours=1),
        extended_key_usage=[ExtendedKeyUsageOID.SERVER_AUTH],
    )
    (tls_dir / SERVER_CERT_FILE).write_text(
        certificate_to_pem(server_leaf), encoding="ascii"
    )
    (tls_dir / SERVER_KEY_FILE).write_text(
        private_key_to_pem(server_key), encoding="ascii"
    )

    private = tmp_path / "private"
    private.mkdir(exist_ok=True)
    client_pem, client_key = _service_leaf(ca)
    (private / CLIENT_CERT_FILE).write_text(client_pem, encoding="ascii")
    (private / CLIENT_KEY_FILE).write_text(
        private_key_to_pem(client_key), encoding="ascii"
    )

    # The client half reads its material through the settings rather than from
    # this fixture, so a drift between the two would surface as an opaque TLS
    # error rather than as the fixture's own problem.
    paths = backend_client_credentials()
    assert paths.ca_certificate == tls_dir / CA_FILE
    _assert_material_agrees(paths.ca_certificate, tls_dir / SERVER_CERT_FILE)

    # Retried because a port the OS calls free can still be reached by somebody
    # else's listener: Windows lets a 0.0.0.0 binder and a 127.0.0.1 binder hold
    # the same port and hands a connection to either. The preflight is what
    # tells the two apart; without it the mix-up surfaces inside the test as a
    # certificate that will not verify.
    #
    # And when every port answers with the same foreign issuer, nothing is
    # colliding -- a TLS-inspecting security product on the machine is
    # re-signing loopback connections, and a handshake is simply not observable
    # here. That is a property of the machine, not of the code, so the test says
    # so and skips.
    for attempt in range(_LISTENER_ATTEMPTS):
        port = _free_port()
        server = uvicorn.Server(
            uvicorn.Config(
                proxy_app.app,
                host="127.0.0.1",
                port=port,
                ssl_certfile=str(tls_dir / SERVER_CERT_FILE),
                ssl_keyfile=str(tls_dir / SERVER_KEY_FILE),
                ssl_ca_certs=str(tls_dir / CA_FILE),
                ssl_cert_reqs=ssl.CERT_REQUIRED,
                log_config=None,
                lifespan="on",
            )
        )
        task = asyncio.create_task(server.serve())
        while not server.started:
            if task.done():
                # Surfaces a bind failure instead of spinning forever.
                await task
                raise AssertionError("the listener stopped before it was ready")
            await asyncio.sleep(0.02)
        try:
            # In a thread: the listener shares this event loop, so a blocking
            # handshake here would wait on a server that cannot run until it
            # returns.
            await asyncio.to_thread(_preflight, port, paths)
        except _NotOurListener as exc:
            await _stop(server, task)
            if attempt == _LISTENER_ATTEMPTS - 1:
                pytest.skip(
                    f"loopback TLS on this machine is re-signed by {exc.issuer!r}, "
                    "so a real handshake cannot be observed here; the "
                    "authorization rules are covered by the tests above"
                )
            continue
        except (ssl.SSLError, OSError) as exc:
            await _stop(server, task)
            if attempt == _LISTENER_ATTEMPTS - 1:
                raise AssertionError(
                    f"the listener on port {port} never became reachable: {exc}"
                ) from exc
            continue
        break

    try:
        yield f"https://127.0.0.1:{port}"
    finally:
        await _stop(server, task)
        proxy_app._root.clear()


async def test_a_real_mutually_authenticated_call_round_trips(
    listener: str, ca: RootCertificateAuthority
) -> None:
    """Everything at once: mTLS, the sender signature, and a live grant."""
    pem, key = _tool_leaf(ca)
    timestamp = datetime.now(UTC)
    credential = McpClientCredential(
        certificate_pem=pem,
        signature=sign_pop_digest(
            key,
            pop_digest(
                session_id=SESSION_ID,
                mcp_server_id=SERVER_ID,
                tool_name=TOOL_NAME,
                arguments=ARGUMENTS,
                nonce="live-nonce",
                timestamp=timestamp,
            ),
        ),
        nonce="live-nonce",
        timestamp=timestamp,
        private_key_pem=private_key_to_pem(key),
    )

    result = await RemoteMcpExecutor(listener).call_tool(
        CONNECTION,
        TOOL_NAME,
        ARGUMENTS,
        mcp_server_id=SERVER_ID,
        session_id=SESSION_ID,
        credential=credential,
    )

    assert isinstance(result.content[0], types.TextContent)
    assert result.content[0].text == "ok"


async def test_a_client_without_a_certificate_cannot_even_connect(
    listener: str,
) -> None:
    """The TLS layer's own guarantee, which nothing in the app can see."""
    import httpx

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    async with httpx.AsyncClient(verify=context, timeout=10) as client:
        with pytest.raises(httpx.HTTPError):
            await client.get(f"{listener}/health")
