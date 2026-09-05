"""The TLS material for the hop between the backend and the MCP proxy.

Registered MCP servers are third-party code A2Flow launches on a tenant's
behalf, so they run in a container of their own rather than beside the database
credentials and the LLM API keys. That container has to be reachable, and the
channel to it has to prove both ends belong to this deployment -- which is what
this module provisions.

**One root, three kinds of leaf.** The root is the same
``mcp_certificate_authorities`` row that signs tool certificates
(:mod:`infrastructure.mcp_ca`), reused deliberately: the proxy's whole job is
to check that a call carries a tool certificate this deployment issued, so it
must trust that root anyway. Giving the transport a second root would mean a
second thing to distribute without adding a boundary. The three leaves are told
apart by their extended key usage and their SAN, never by their issuer:

=========================  ===============  ==================================
Leaf                       Usage            SAN
=========================  ===============  ==================================
Tool certificate           ``clientAuth``   binding URN + one URN per grant
Backend client identity    ``clientAuth``   ``urn:a2flow:service:backend``
Proxy listener             ``serverAuth``   ``dNSName`` of the proxy
=========================  ===============  ==================================

A server leaf presented as a client certificate is refused by
:func:`infrastructure.mcp_certificate.verify_certificate` (no ``clientAuth``),
and a service leaf presented as a grant is refused by
:func:`infrastructure.mcp_certificate.extract_claims` (unrecognized SAN). Both
refusals already existed; sharing the root is safe precisely because they do.

**Why the backend writes files.** The root's private key lives in the database,
encrypted with the same Fernet key as local secrets, so the backend is the only
process that can sign anything -- and giving the sandbox a database connection
would defeat the point of having one. So the backend issues both ends at
startup and drops them in a directory the proxy mounts read-only. No bootstrap
protocol, no shared token, no new endpoint: ``depends_on: service_healthy`` is
the whole handshake, because the backend writes these before it reports healthy.

The backend's *own* client key goes somewhere else
(:attr:`config.Settings.mcp_backend_tls_dir`), not into the published
directory. Everything in the published directory is readable by whatever a
user-registered MCP server does inside the proxy container, and the proxy's own
server key is already spent on that container's identity -- the key that speaks
for the backend must not be.

**Reissuing.** Startup rewrites a leaf that is missing, unreadable, issued by a
different root, no longer paired with its key file, or within
:data:`RENEW_BEFORE` of expiry. Otherwise the files are left exactly as they
are, so an ordinary restart does not hand the proxy a certificate it is still
holding the predecessor of.
"""

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure.mcp_ca import (
    McpCaError,
    RootCertificateAuthority,
    certificate_from_pem,
    certificate_to_pem,
    generate_key,
    load_or_create_root_ca,
    private_key_from_pem,
    private_key_to_pem,
    sign_leaf_certificate,
)
from infrastructure.mcp_certificate import BACKEND_SERVICE_NAME, build_service_urn
from repositories.mcp_ca import SqlMcpCertificateAuthorityRepository

logger = logging.getLogger(__name__)

#: Name of the root CA's public certificate, in the published directory. Both
#: sides read it: the proxy to verify client certificates, the backend to verify
#: the proxy's listener.
CA_FILE = "ca.crt"

#: The proxy listener's certificate and key, in the published directory.
SERVER_CERT_FILE = "server.crt"
SERVER_KEY_FILE = "server.key"

#: The backend's own client identity, in its private directory.
CLIENT_CERT_FILE = "client.crt"
CLIENT_KEY_FILE = "client.key"

#: How much validity has to be left for a leaf to be kept rather than reissued.
RENEW_BEFORE = timedelta(days=30)


@dataclass(frozen=True)
class TransportCredentials:
    """Where one end's TLS material sits on disk.

    Paths rather than parsed material because that is what ``ssl`` takes:
    :meth:`ssl.SSLContext.load_cert_chain` and
    :meth:`ssl.SSLContext.load_verify_locations` both read from the filesystem,
    with no in-memory equivalent for the certificate chain.

    Attributes:
        ca_certificate: The root whose signature the peer must carry.
        certificate: This end's own leaf.
        private_key: The leaf's key.
    """

    ca_certificate: Path
    certificate: Path
    private_key: Path


def backend_client_credentials() -> TransportCredentials:
    """Return where the backend's client identity is kept.

    Returns:
        The paths, whether or not they have been written yet.
    """
    settings = get_settings()
    return TransportCredentials(
        ca_certificate=settings.mcp_proxy_tls_dir / CA_FILE,
        certificate=settings.mcp_backend_tls_dir / CLIENT_CERT_FILE,
        private_key=settings.mcp_backend_tls_dir / CLIENT_KEY_FILE,
    )


def proxy_server_credentials() -> TransportCredentials:
    """Return where the proxy's listener material is published.

    Read by the proxy process, which never signs anything and therefore never
    calls the rest of this module.

    Returns:
        The paths, whether or not they have been written yet.
    """
    settings = get_settings()
    return TransportCredentials(
        ca_certificate=settings.mcp_proxy_tls_dir / CA_FILE,
        certificate=settings.mcp_proxy_tls_dir / SERVER_CERT_FILE,
        private_key=settings.mcp_proxy_tls_dir / SERVER_KEY_FILE,
    )


def _write_atomic(path: Path, text: str, *, mode: int) -> None:
    """Replace a file's contents in one step, at the given permissions.

    The proxy reads these files at its own startup, which can overlap a backend
    restart, so a reader must never see a half-written PEM. ``os.replace`` is
    atomic on both POSIX and Windows; the mode is applied to the temporary file
    first, so the final name is never briefly world-readable.

    Args:
        path: Final path to write.
        text: PEM contents.
        mode: POSIX permission bits. A no-op on Windows, where the enclosing
            directory's ACL is what protects the file.
    """
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="ascii")
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def _read_certificate(path: Path) -> x509.Certificate | None:
    """Load a certificate from disk, treating anything unreadable as absent.

    Args:
        path: The certificate file.

    Returns:
        The parsed certificate, or ``None`` when the file is missing or is not
        a readable PEM -- both of which mean the same thing here: reissue.
    """
    try:
        return certificate_from_pem(path.read_text(encoding="ascii"))
    except (OSError, McpCaError, UnicodeDecodeError):
        return None


def _read_private_key(path: Path) -> ec.EllipticCurvePrivateKey | None:
    """Load a private key from disk, treating anything unreadable as absent.

    Args:
        path: The key file.

    Returns:
        The parsed key, or ``None`` when the file is missing or unreadable.
    """
    try:
        return private_key_from_pem(path.read_text(encoding="ascii"))
    except (OSError, McpCaError, UnicodeDecodeError):
        return None


def _is_still_usable(
    certificate_path: Path,
    key_path: Path,
    *,
    ca: RootCertificateAuthority,
    now: datetime,
) -> bool:
    """Report whether an already-written leaf can be left alone.

    Args:
        certificate_path: The leaf's certificate file.
        key_path: The leaf's key file.
        ca: The root that must have issued it.
        now: The instant to judge the validity window against.

    Returns:
        ``True`` when the pair is present, matched, issued by this root, and
        not close to expiring.
    """
    certificate = _read_certificate(certificate_path)
    key = _read_private_key(key_path)
    if certificate is None or key is None:
        return False
    if certificate.issuer != ca.certificate.subject:
        # The root rotated, or these files came from another deployment. Either
        # way the peer would refuse this leaf.
        return False
    public_key = certificate.public_key()
    if not isinstance(public_key, ec.EllipticCurvePublicKey):
        return False
    if key.public_key().public_numbers() != public_key.public_numbers():
        # A previous run was interrupted between the two writes.
        return False
    return now + RENEW_BEFORE < certificate.not_valid_after_utc


def _issue(
    ca: RootCertificateAuthority,
    *,
    common_name: str,
    sans: list[x509.GeneralName],
    extended_key_usage: list[x509.ObjectIdentifier],
    now: datetime,
) -> tuple[str, str]:
    """Sign one transport leaf and return it with its key, both as PEM.

    Args:
        ca: The loaded root that signs.
        common_name: Subject common name of the leaf.
        sans: The leaf's subject alternative names.
        extended_key_usage: What the leaf may be used for.
        now: Start of the validity window.

    Returns:
        The ``(certificate_pem, private_key_pem)`` pair.
    """
    key = generate_key()
    certificate = sign_leaf_certificate(
        ca,
        public_key=key.public_key(),
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]),
        sans=sans,
        not_before=now,
        not_after=now + timedelta(days=get_settings().mcp_transport_cert_validity_days),
        extended_key_usage=extended_key_usage,
    )
    return certificate_to_pem(certificate), private_key_to_pem(key)


def _ensure_leaf(
    ca: RootCertificateAuthority,
    *,
    certificate_path: Path,
    key_path: Path,
    common_name: str,
    sans: list[x509.GeneralName],
    extended_key_usage: list[x509.ObjectIdentifier],
    now: datetime,
) -> None:
    """Write a transport leaf, unless the one already on disk still stands.

    The key is written before the certificate. A reader that catches the
    in-between state then sees a certificate that is either absent or already
    paired, never one whose key has not landed.

    Args:
        ca: The loaded root that signs.
        certificate_path: Where the leaf goes.
        key_path: Where its key goes.
        common_name: Subject common name of the leaf.
        sans: The leaf's subject alternative names.
        extended_key_usage: What the leaf may be used for.
        now: Start of the validity window of a newly issued leaf.
    """
    if _is_still_usable(certificate_path, key_path, ca=ca, now=now):
        return
    certificate_pem, key_pem = _issue(
        ca,
        common_name=common_name,
        sans=sans,
        extended_key_usage=extended_key_usage,
        now=now,
    )
    _write_atomic(key_path, key_pem, mode=0o600)
    _write_atomic(certificate_path, certificate_pem, mode=0o644)
    logger.info("Issued the MCP transport certificate %s", certificate_path)


def _publish_ca(ca: RootCertificateAuthority, path: Path) -> None:
    """Publish the root's public certificate, if it is not already there.

    Compared before writing so an unchanged root leaves the file, and its
    modification time, alone.

    Args:
        ca: The loaded root.
        path: Where the public certificate goes.
    """
    pem = certificate_to_pem(ca.certificate)
    existing = _read_certificate(path)
    if existing is not None and certificate_to_pem(existing) == pem:
        return
    _write_atomic(path, pem, mode=0o644)
    logger.info("Published the MCP root certificate to %s", path)


async def provision_transport_credentials(db: AsyncSession) -> None:
    """Issue and publish everything the backend/proxy channel needs.

    A no-op unless ``MCP_PROXY_URL`` is set: a deployment that reaches MCP
    servers from the backend process has no second end to authenticate, and
    writing key material it will never use would be pure liability.

    Called from the application's lifespan, after the system user is seeded --
    creating the root on first use records that user as its owner.

    Args:
        db: An open database session, used to load or create the root CA.

    Raises:
        McpCaError: If the root cannot be generated, loaded, or used to sign.
        OSError: If the directories cannot be created or written. Both are
            deliberately fatal: a deployment that asked for the proxy and
            cannot equip it would otherwise come up unable to run a single
            tool, and say so only at the first call.
    """
    settings = get_settings()
    if not settings.mcp_proxy_url:
        return

    settings.mcp_proxy_tls_dir.mkdir(parents=True, exist_ok=True)
    settings.mcp_backend_tls_dir.mkdir(parents=True, exist_ok=True)

    ca = await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(db))
    now = datetime.now(UTC)

    _publish_ca(ca, settings.mcp_proxy_tls_dir / CA_FILE)
    _ensure_leaf(
        ca,
        certificate_path=settings.mcp_proxy_tls_dir / SERVER_CERT_FILE,
        key_path=settings.mcp_proxy_tls_dir / SERVER_KEY_FILE,
        common_name=settings.mcp_proxy_server_name,
        sans=[x509.DNSName(settings.mcp_proxy_server_name)],
        extended_key_usage=[ExtendedKeyUsageOID.SERVER_AUTH],
        now=now,
    )
    _ensure_leaf(
        ca,
        certificate_path=settings.mcp_backend_tls_dir / CLIENT_CERT_FILE,
        key_path=settings.mcp_backend_tls_dir / CLIENT_KEY_FILE,
        common_name=BACKEND_SERVICE_NAME,
        sans=[x509.UniformResourceIdentifier(build_service_urn(BACKEND_SERVICE_NAME))],
        extended_key_usage=[ExtendedKeyUsageOID.CLIENT_AUTH],
        now=now,
    )
