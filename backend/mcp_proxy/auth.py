"""What the MCP proxy checks before it will reach anything.

Two layers, and neither is redundant.

**TLS.** The listener is configured with ``CERT_REQUIRED`` against the root CA,
so nothing without a certificate this deployment issued can open a connection
at all. That is a real gate, and it is the only thing standing between the
proxy and anything else that can route to it on the internal network.

**This module.** TLS authenticates a *connection*; it says nothing about the
operations that flow down it, and uvicorn does not implement the ASGI TLS
extension, so the peer certificate is not readable from a handler in any case.
So every request carries its own evidence, verified here:

=============  ==========================================================
Every request  A **service certificate** and a signature over
               :func:`infrastructure.mcp_certificate.request_digest`, which
               covers the connection spec. Proves the backend sent this
               request and that the spec is the one it signed.
A call         Additionally a **tool certificate** with a proof-of-possession
               signature over this call, whose signed grant must cover the
               target ``(server, tool)``.
=============  ==========================================================

The two answer different questions and are made by different keys. The sender
signature says "the backend asked for exactly this"; the tool certificate says
"a live task grant covers exactly this tool". Neither implies the other, which
is why a request pointing a valid grant at a different command or URL fails
here rather than being executed.

Everything in this module is pure: a parsed certificate, a root, a clock. It
holds no state and reaches nothing.
"""

import base64
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography import x509

from infrastructure.mcp_ca import McpCaError, certificate_from_pem
from infrastructure.mcp_certificate import (
    CertificateClaims,
    CertificateVerificationError,
    arguments_digest,
    extract_claims,
    pop_digest,
    request_digest,
    service_name,
    verify_certificate,
    verify_pop_signature,
)
from models.mcp_execution import ExecutorCredential, ExecutorSender

logger = logging.getLogger(__name__)


class ProxyAuthError(Exception):
    """Raised when a request is refused before anything is reached.

    ``message`` is returned to the caller, which is the backend rather than an
    end user, so it names the rule that failed. It never quotes key material or
    signature bytes.
    """

    def __init__(self, message: str) -> None:
        """Initialize the error.

        Args:
            message: Why the request was refused.
        """
        self.message = message
        super().__init__(message)


def _parse(pem: str) -> x509.Certificate:
    """Parse a presented certificate, refusing anything unreadable.

    Args:
        pem: The PEM text from the request body.

    Returns:
        The parsed certificate.

    Raises:
        ProxyAuthError: If it is not a readable certificate.
    """
    try:
        return certificate_from_pem(pem)
    except McpCaError as exc:
        raise ProxyAuthError("the presented certificate is not readable") from exc


def _decode_signature(signature: str) -> bytes:
    """Decode a base64 signature from the wire.

    Args:
        signature: The base64 text.

    Returns:
        The raw DER-encoded signature.

    Raises:
        ProxyAuthError: If it is not valid base64.
    """
    try:
        return base64.b64decode(signature, validate=True)
    except ValueError as exc:
        raise ProxyAuthError("the presented signature is not valid base64") from exc


def verify_sender(
    sender: ExecutorSender,
    *,
    ca_certificate: x509.Certificate,
    operation: str,
    connection: dict[str, Any],
    tool_name: str,
    arguments: dict[str, Any],
    now: datetime,
    window: timedelta,
) -> str:
    """Check that a request came from a component of this deployment, unaltered.

    Args:
        sender: The sender block the request carries.
        ca_certificate: This deployment's root.
        operation: Which endpoint is being asked; part of the signed digest, so
            a signature made for a listing cannot stand in for a call.
        connection: The connection spec exactly as it arrived, re-serialized
            into the digest so any change to it invalidates the signature.
        tool_name: The tool being invoked, empty for a listing.
        arguments: The call's arguments, empty for a listing.
        now: The instant to judge validity and freshness against.
        window: How stale the signature's timestamp may be.

    Returns:
        The name of the component that sent the request.

    Raises:
        ProxyAuthError: If the certificate is not a service certificate issued
            by this deployment, or the signature does not cover this request.
    """
    certificate = _parse(sender.certificate_pem)
    try:
        verify_certificate(certificate, ca_certificate=ca_certificate, now=now)
        name = service_name(certificate)
    except CertificateVerificationError as exc:
        raise ProxyAuthError(
            f"the sender is not a component of this deployment: {exc}"
        ) from exc

    digest = request_digest(
        operation=operation,
        connection_hash=arguments_digest(connection),
        tool_name=tool_name,
        arguments_hash=arguments_digest(arguments),
        nonce=sender.nonce,
        timestamp=sender.timestamp,
    )
    try:
        verify_pop_signature(
            certificate,
            signature=_decode_signature(sender.signature),
            digest=digest,
            timestamp=sender.timestamp,
            now=now,
            window=window,
        )
    except CertificateVerificationError as exc:
        raise ProxyAuthError(f"the request signature does not verify: {exc}") from exc
    return name


def verify_call_credential(
    credential: ExecutorCredential | None,
    *,
    ca_certificate: x509.Certificate,
    session_id: str,
    mcp_server_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    now: datetime,
    window: timedelta,
) -> CertificateClaims:
    """Check that a live task grant covers the call being asked for.

    The backend's gateway already ran this check against the database, which is
    where the interesting half of the question lives -- is the task still in
    progress, is the approval still granted, has the certificate been revoked.
    None of that is answerable here. What *is* answerable without any state is
    that the certificate was issued by this deployment, is inside its validity
    window, was proven to belong to the caller, and grants this exact tool --
    and those are checked at the boundary rather than assumed.

    Args:
        credential: The tool certificate the call presents.
        ca_certificate: This deployment's root.
        session_id: The ADK session, part of the signed digest.
        mcp_server_id: The registered server the grant must name.
        tool_name: The tool the grant must cover.
        arguments: The call's arguments, part of the signed digest.
        now: The instant to judge validity and freshness against.
        window: How stale the signature's timestamp may be.

    Returns:
        The claims the certificate carries.

    Raises:
        ProxyAuthError: If no certificate was presented, it was not issued by
            this deployment, it does not verify, or its grant does not cover
            the target tool.
    """
    if credential is None:
        raise ProxyAuthError("a tool certificate is required to call a tool")

    certificate = _parse(credential.certificate_pem)
    try:
        verify_certificate(certificate, ca_certificate=ca_certificate, now=now)
        claims = extract_claims(certificate)
    except CertificateVerificationError as exc:
        raise ProxyAuthError(f"the tool certificate is not valid: {exc}") from exc

    digest = pop_digest(
        session_id=session_id,
        mcp_server_id=mcp_server_id,
        tool_name=tool_name,
        arguments=arguments,
        nonce=credential.nonce,
        timestamp=credential.timestamp,
    )
    try:
        verify_pop_signature(
            certificate,
            signature=_decode_signature(credential.signature),
            digest=digest,
            timestamp=credential.timestamp,
            now=now,
            window=window,
        )
    except CertificateVerificationError as exc:
        raise ProxyAuthError(
            f"the tool certificate was not proven to belong to this caller: {exc}"
        ) from exc

    if not claims.grants(mcp_server_id, tool_name):
        raise ProxyAuthError(
            f"the tool certificate does not grant {tool_name!r} on server "
            f"{mcp_server_id!r}"
        )
    return claims


def utc_now() -> datetime:
    """Return the current instant, as a seam tests can replace.

    Returns:
        The current UTC time.
    """
    return datetime.now(UTC)
