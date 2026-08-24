"""The certificate grammar and the verification steps that read it.

Everything here is pure: no database session, no ORM row, no settings lookup
beyond what a caller passes in. That keeps the rules an approval certificate
encodes testable on their own, and it is what lets the same code run unchanged
when the proxy is lifted to an HTTP endpoint and the certificate arrives from a
TLS handshake rather than from a local lookup.

**What a certificate claims.** Two things, both carried as ``subjectAltName``
URI entries rather than a custom extension -- A2Flow holds no private enterprise
OID arc, and a made-up one would be indistinguishable from someone else's:

``urn:a2flow:binding:tenant/T/execution/E/task/K/approval/A``
    Exactly one per certificate. Says which approval, on which task, of which
    run, in which tenant this certificate speaks for. Verification compares
    every segment against the context the proxy derived independently from the
    ADK session id, so a certificate minted for one run is useless in another.

``urn:a2flow:tool:SERVER/TOOL``
    One per tool the approval granted, snapshotted from the task's
    ``tool_bindings`` at the moment the approver decided. This is the frozen
    grant: the execution agent can still rewrite a task's bindings mid-run
    through ``update_workflow_task``, but the certificate it must present does
    not change, so rewriting them cannot widen what it may call.

Both segments are percent-encoded. ``mcp_server_id`` is a UUID, but
:data:`models.constraints.ToolName` places no character restriction on a tool
name at all -- a name containing ``/`` would otherwise make the URN ambiguous.

**Proof of possession.** A certificate alone proves nothing about who is
presenting it, so every proxied call carries a signature over
:func:`pop_digest` -- a hash binding the certificate to *this* call's session,
server, tool, arguments, a nonce, and a timestamp. Rejecting a stale timestamp
(:func:`verify_pop_signature` takes the window) is the whole replay defense:
recording nonces would cost a write per tool call to defend against an attacker
who, in the current single-process deployment, could simply sign a fresh one.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote, unquote

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ec

from infrastructure.mcp_ca import HASH_ALGORITHM

#: Prefix of the single binding URN every approval certificate carries.
BINDING_URN_PREFIX = "urn:a2flow:binding:"

#: Prefix of the tool-grant URNs. One entry per granted tool.
TOOL_URN_PREFIX = "urn:a2flow:tool:"

#: Domain-separation tag hashed into every proof-of-possession digest. Bumping
#: it invalidates every signature made under the old scheme, which is the point:
#: a change to the digest layout must never leave old signatures verifiable
#: against the new one.
POP_CONTEXT = "a2flow-mcp-pop-v1"

#: Ordered segment labels of the binding URN, e.g. ``tenant/T/execution/E/...``.
_BINDING_LABELS = ("tenant", "execution", "task", "approval")


class CertificateVerificationError(Exception):
    """Raised when a certificate or its proof-of-possession signature is rejected.

    The message is caller-safe: it names the rule that failed, never the key
    material or the signature bytes.
    """


@dataclass(frozen=True)
class CertificateBinding:
    """Which approval, task, run, and tenant a certificate speaks for."""

    tenant_id: str
    execution_id: str
    task_id: str
    approval_id: str


@dataclass(frozen=True)
class CertificateClaims:
    """Everything verification reads out of a leaf certificate.

    Attributes:
        binding: The single binding URN, parsed.
        allowed_tools: ``(mcp_server_id, tool_name)`` pairs the approval
            granted, frozen at decision time.
        serial_number: Decimal serial, matching
            ``approval_certificates.serial_number``.
        not_before: Start of the validity window.
        not_after: End of the validity window.
    """

    binding: CertificateBinding
    allowed_tools: frozenset[tuple[str, str]]
    serial_number: str
    not_before: datetime
    not_after: datetime

    def grants(self, mcp_server_id: str, tool_name: str) -> bool:
        """Return whether the approval granted this exact tool.

        Args:
            mcp_server_id: Id of the registered MCP server.
            tool_name: Name of the tool on that server.

        Returns:
            ``True`` when the pair is in :attr:`allowed_tools`.
        """
        return (mcp_server_id, tool_name) in self.allowed_tools


# ---------------------------------------------------------------------------
# URN grammar
# ---------------------------------------------------------------------------


def build_binding_urn(binding: CertificateBinding) -> str:
    """Render a binding as its URN.

    Args:
        binding: The tenant/execution/task/approval tuple.

    Returns:
        The ``urn:a2flow:binding:...`` string.
    """
    values = (
        binding.tenant_id,
        binding.execution_id,
        binding.task_id,
        binding.approval_id,
    )
    segments = [
        f"{label}/{quote(value, safe='')}"
        for label, value in zip(_BINDING_LABELS, values, strict=True)
    ]
    return BINDING_URN_PREFIX + "/".join(segments)


def parse_binding_urn(urn: str) -> CertificateBinding:
    """Parse a binding URN produced by :func:`build_binding_urn`.

    Args:
        urn: The URN text.

    Returns:
        The parsed binding.

    Raises:
        CertificateVerificationError: If the URN is not a well-formed binding.
    """
    if not urn.startswith(BINDING_URN_PREFIX):
        raise CertificateVerificationError("Certificate binding URN is malformed")
    parts = urn[len(BINDING_URN_PREFIX) :].split("/")
    if len(parts) != 2 * len(_BINDING_LABELS):
        raise CertificateVerificationError("Certificate binding URN is malformed")
    labels = tuple(parts[0::2])
    values = [unquote(value) for value in parts[1::2]]
    if labels != _BINDING_LABELS or not all(values):
        raise CertificateVerificationError("Certificate binding URN is malformed")
    return CertificateBinding(
        tenant_id=values[0],
        execution_id=values[1],
        task_id=values[2],
        approval_id=values[3],
    )


def build_tool_urn(mcp_server_id: str, tool_name: str) -> str:
    """Render one granted tool as its URN.

    Args:
        mcp_server_id: Id of the registered MCP server.
        tool_name: Name of the tool on that server.

    Returns:
        The ``urn:a2flow:tool:...`` string.
    """
    return (
        f"{TOOL_URN_PREFIX}{quote(mcp_server_id, safe='')}/{quote(tool_name, safe='')}"
    )


def parse_tool_urn(urn: str) -> tuple[str, str]:
    """Parse a tool-grant URN produced by :func:`build_tool_urn`.

    Args:
        urn: The URN text.

    Returns:
        The ``(mcp_server_id, tool_name)`` pair.

    Raises:
        CertificateVerificationError: If the URN is not a well-formed grant.
    """
    if not urn.startswith(TOOL_URN_PREFIX):
        raise CertificateVerificationError("Certificate tool grant URN is malformed")
    server, separator, tool = urn[len(TOOL_URN_PREFIX) :].partition("/")
    if not separator or not server or not tool:
        raise CertificateVerificationError("Certificate tool grant URN is malformed")
    return unquote(server), unquote(tool)


def extract_claims(certificate: x509.Certificate) -> CertificateClaims:
    """Read the binding and tool grants out of a leaf certificate.

    Args:
        certificate: The parsed leaf certificate.

    Returns:
        The claims it carries.

    Raises:
        CertificateVerificationError: If the certificate has no SAN extension,
            carries anything other than exactly one binding URN, or holds a URI
            entry that is neither a binding nor a tool grant. An unrecognized
            entry is a hard failure rather than something to skip: silently
            ignoring it would let a future URN kind be stripped by an old
            verifier without anyone noticing.
    """
    try:
        san = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
    except x509.ExtensionNotFound as exc:
        raise CertificateVerificationError(
            "Certificate carries no subject alternative names"
        ) from exc

    uris = san.get_values_for_type(x509.UniformResourceIdentifier)
    bindings: list[CertificateBinding] = []
    tools: set[tuple[str, str]] = set()
    for uri in uris:
        if uri.startswith(BINDING_URN_PREFIX):
            bindings.append(parse_binding_urn(uri))
        elif uri.startswith(TOOL_URN_PREFIX):
            tools.add(parse_tool_urn(uri))
        else:
            raise CertificateVerificationError(
                "Certificate carries an unrecognized subject alternative name"
            )

    if len(bindings) != 1:
        raise CertificateVerificationError(
            "Certificate must carry exactly one binding URN"
        )

    return CertificateClaims(
        binding=bindings[0],
        allowed_tools=frozenset(tools),
        serial_number=str(certificate.serial_number),
        not_before=certificate.not_valid_before_utc,
        not_after=certificate.not_valid_after_utc,
    )


# ---------------------------------------------------------------------------
# Proof of possession
# ---------------------------------------------------------------------------


def canonical_json(value: Any) -> str:
    """Serialize a value to the one JSON form both signer and verifier produce.

    Sorted keys and separators without whitespace make the encoding stable
    across dict insertion order and Python versions; ``default=str`` keeps a
    stray non-JSON value (a ``datetime`` an upstream schema allowed through)
    from raising instead of signing.

    Args:
        value: The value to encode, typically the tool-call arguments dict.

    Returns:
        The canonical JSON text.
    """
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def arguments_digest(arguments: Any) -> str:
    """Hash the call's arguments into the form the signed digest embeds.

    Split out so the audit trail can store this hex string instead of the
    arguments themselves -- tool arguments routinely carry the very data an
    approval was needed for, and an audit table is the wrong place to
    accumulate it. Storing the hash keeps the record verifiable by anyone who
    already has the arguments, without handing them to anyone who does not.

    Args:
        arguments: The tool-call arguments.

    Returns:
        The SHA-256 hex digest of their canonical JSON encoding.
    """
    return hashlib.sha256(canonical_json(arguments).encode("utf-8")).hexdigest()


def pop_digest_from_parts(
    *,
    session_id: str,
    mcp_server_id: str,
    tool_name: str,
    arguments_hash: str,
    nonce: str,
    timestamp: datetime,
) -> bytes:
    """Compute the signed digest from already-hashed arguments.

    This is the form an audit row can reconstruct: every input is a column of
    ``mcp_tool_invocations``, so a recorded signature stays checkable against
    the certificate long after the call itself is gone.

    Args:
        session_id: The ADK session the call belonged to.
        mcp_server_id: Id of the registered MCP server called.
        tool_name: Name of the tool called.
        arguments_hash: Output of :func:`arguments_digest`.
        nonce: The per-call random value that went into the digest.
        timestamp: When the signature was made; normalized to UTC.

    Returns:
        The SHA-256 digest to sign or verify.
    """
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    payload = "\n".join(
        (
            POP_CONTEXT,
            session_id,
            mcp_server_id,
            tool_name,
            arguments_hash,
            nonce,
            timestamp.astimezone(UTC).isoformat(),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).digest()


def pop_digest(
    *,
    session_id: str,
    mcp_server_id: str,
    tool_name: str,
    arguments: Any,
    nonce: str,
    timestamp: datetime,
) -> bytes:
    """Compute the digest a proof-of-possession signature covers.

    Every field that identifies the call is in here, so a signature captured
    from one call cannot be replayed onto a different server, tool, or argument
    set -- only onto a byte-identical repeat of the same call inside the
    timestamp window.

    Args:
        session_id: The ADK session the call belongs to.
        mcp_server_id: Id of the registered MCP server being called.
        tool_name: Name of the tool being called.
        arguments: The tool-call arguments, encoded with :func:`canonical_json`.
        nonce: A per-call random value, making two identical calls sign
            different digests.
        timestamp: When the signature was made; normalized to UTC.

    Returns:
        The SHA-256 digest to sign or verify.
    """
    return pop_digest_from_parts(
        session_id=session_id,
        mcp_server_id=mcp_server_id,
        tool_name=tool_name,
        arguments_hash=arguments_digest(arguments),
        nonce=nonce,
        timestamp=timestamp,
    )


def sign_pop_digest(key: ec.EllipticCurvePrivateKey, digest: bytes) -> bytes:
    """Sign a proof-of-possession digest.

    Args:
        key: The leaf certificate's private key.
        digest: The digest from :func:`pop_digest`.

    Returns:
        The DER-encoded ECDSA signature.
    """
    return key.sign(digest, ec.ECDSA(HASH_ALGORITHM))


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify_certificate(
    certificate: x509.Certificate,
    *,
    ca_certificate: x509.Certificate,
    now: datetime,
) -> None:
    """Check that a leaf was issued by the given root and is valid right now.

    Every rule is checked even though the signature check alone would catch a
    forged certificate: the rest guard against a certificate this deployment
    itself issued for a different purpose being replayed as an approval
    certificate.

    Args:
        certificate: The leaf to verify.
        ca_certificate: The root that must have issued it.
        now: The instant to evaluate the validity window against.

    Raises:
        CertificateVerificationError: If the issuer, signature, validity window,
            basic constraints, key usage, or extended key usage is wrong.
    """
    if certificate.issuer != ca_certificate.subject:
        raise CertificateVerificationError(
            "Certificate was not issued by this deployment's authority"
        )

    public_key = ca_certificate.public_key()
    if not isinstance(public_key, ec.EllipticCurvePublicKey):
        raise CertificateVerificationError(
            "The certificate authority does not hold an elliptic-curve key"
        )
    try:
        public_key.verify(
            certificate.signature,
            certificate.tbs_certificate_bytes,
            ec.ECDSA(HASH_ALGORITHM),
        )
    except InvalidSignature as exc:
        raise CertificateVerificationError(
            "Certificate signature does not verify against the authority"
        ) from exc

    if now < certificate.not_valid_before_utc:
        raise CertificateVerificationError("Certificate is not valid yet")
    if now > certificate.not_valid_after_utc:
        raise CertificateVerificationError("Certificate has expired")

    # Basic constraints first, and its own check before the rest are even read:
    # a CA certificate has no extended key usage, so checking that first would
    # report "missing a required extension" for the one case where the real
    # answer is "this is the root".
    try:
        basic = certificate.extensions.get_extension_for_class(x509.BasicConstraints)
    except x509.ExtensionNotFound as exc:
        raise CertificateVerificationError(
            "Certificate is missing a required extension"
        ) from exc
    if basic.value.ca:
        raise CertificateVerificationError(
            "A certificate authority cannot be used as a client certificate"
        )

    try:
        usage = certificate.extensions.get_extension_for_class(x509.KeyUsage)
        eku = certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
    except x509.ExtensionNotFound as exc:
        raise CertificateVerificationError(
            "Certificate is missing a required extension"
        ) from exc

    if not usage.value.digital_signature:
        raise CertificateVerificationError(
            "Certificate is not allowed to make digital signatures"
        )
    if x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH not in eku.value:
        raise CertificateVerificationError(
            "Certificate is not marked for client authentication"
        )


def verify_pop_signature(
    certificate: x509.Certificate,
    *,
    signature: bytes,
    digest: bytes,
    timestamp: datetime,
    now: datetime,
    window: timedelta,
) -> None:
    """Check the proof-of-possession signature and its freshness.

    The window is two-sided: a timestamp far in the future is rejected as
    firmly as a stale one, so a signer cannot mint a signature now and hold it
    until the certificate is about to expire.

    Args:
        certificate: The leaf whose public key must verify the signature.
        signature: The DER-encoded ECDSA signature presented by the caller.
        digest: The expected digest, recomputed by the verifier from the call.
        timestamp: The timestamp the caller signed.
        now: The instant to judge freshness against.
        window: How far from ``now`` the timestamp may be in either direction.

    Raises:
        CertificateVerificationError: If the timestamp is outside the window,
            the certificate holds a non-EC key, or the signature does not
            verify.
    """
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    if abs(now - timestamp) > window:
        raise CertificateVerificationError(
            "Proof-of-possession signature is outside the accepted time window"
        )

    public_key = certificate.public_key()
    if not isinstance(public_key, ec.EllipticCurvePublicKey):
        raise CertificateVerificationError(
            "Certificate does not hold an elliptic-curve key"
        )
    try:
        public_key.verify(signature, digest, ec.ECDSA(HASH_ALGORITHM))
    except InvalidSignature as exc:
        raise CertificateVerificationError(
            "Proof-of-possession signature does not verify"
        ) from exc
