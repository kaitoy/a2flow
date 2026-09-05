"""Generation, loading, and signing operations of the internal MCP root CA.

The root signs one short-lived leaf certificate per approved workflow task.
:mod:`services.mcp_tool_certificate` decides *when* to issue; this module owns
the X.509 mechanics and the key material.

**Key custody.** The root's private key is stored as Fernet ciphertext in
``mcp_certificate_authorities.private_key_encrypted``, encrypted with the same
process-wide key as local secrets
(:func:`infrastructure.secret_cipher.get_secret_cipher`). Losing that key makes
the root unloadable, which stops new certificates from being issued and every
existing one from verifying -- the same failure mode as losing the key for
stored secrets, and covered by the same warning the cipher logs when it
generates one.

**No process-wide cache.** The active root is read from the database on every
use rather than memoized. Multi-replica deployments on PostgreSQL are
explicitly supported (see ``backend/README.md``), so a cached root would go
stale the moment rotation is implemented, and loading a P-256 key is cheap
enough that the query dominates either way.

**Living where it does.** This module sits in ``infrastructure`` next to
:mod:`infrastructure.secret_cipher`, not under ``dependencies``, so the agent
tool path in :mod:`infrastructure.mcp_tools` can reach it without importing the
dependencies package -- that import would cycle back through
:mod:`infrastructure.agent`.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID, ObjectIdentifier

from config import get_settings
from infrastructure.secret_cipher import get_secret_cipher
from models.mcp_ca import MCPCertificateAuthority, McpCertificateAuthorityCreate
from models.user import SYSTEM_USER_ID
from repositories.exceptions import UniqueViolationError
from repositories.mcp_ca import McpCertificateAuthorityRepository

logger = logging.getLogger(__name__)

#: Curve used for both the root and every leaf. P-256 is the curve every current
#: TLS stack accepts, which matters because leaves carry the ``clientAuth``
#: extended key usage so they can be presented over mTLS unchanged once the
#: gateway is lifted to an HTTP endpoint.
CURVE = ec.SECP256R1()

#: Hash used for every signature this module produces or verifies.
HASH_ALGORITHM = hashes.SHA256()


class McpCaError(Exception):
    """Raised when the root CA cannot be generated, loaded, or used to sign.

    Distinct from :class:`repositories.exceptions.RepositoryError` because it
    signals a deployment-level fault (unreadable key material, an unparseable
    stored certificate) rather than a rejected request.
    """


@dataclass(frozen=True)
class RootCertificateAuthority:
    """A loaded root CA: its database identity plus usable key material.

    Attributes:
        ca_id: Primary key of the ``mcp_certificate_authorities`` row, recorded
            on every certificate this root signs so a leaf stays traceable to
            its issuer after rotation.
        certificate: The parsed self-signed root certificate.
        private_key: The decrypted signing key. Never leaves this process.
    """

    ca_id: str
    certificate: x509.Certificate
    private_key: ec.EllipticCurvePrivateKey


def generate_key() -> ec.EllipticCurvePrivateKey:
    """Generate a fresh P-256 private key.

    Returns:
        A new elliptic-curve private key on :data:`CURVE`.
    """
    return ec.generate_private_key(CURVE)


def private_key_to_pem(key: ec.EllipticCurvePrivateKey) -> str:
    """Serialize a private key as unencrypted PKCS#8 PEM.

    The PEM is never written to disk or returned to a client in this form: both
    call sites hand it straight to the Fernet cipher, so ``NoEncryption`` here
    means "not encrypted twice", not "stored in the clear".

    Args:
        key: The private key to serialize.

    Returns:
        The PKCS#8 PEM text.
    """
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")


def private_key_from_pem(pem: str) -> ec.EllipticCurvePrivateKey:
    """Parse a PKCS#8 PEM private key produced by :func:`private_key_to_pem`.

    Args:
        pem: The PEM text.

    Returns:
        The parsed elliptic-curve private key.

    Raises:
        McpCaError: If the PEM is unparseable or holds a non-EC key.
    """
    try:
        key = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    except (ValueError, TypeError) as exc:
        raise McpCaError("Stored private key is not a readable PEM") from exc
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise McpCaError("Stored private key is not an elliptic-curve key")
    return key


def certificate_to_pem(certificate: x509.Certificate) -> str:
    """Serialize a certificate as PEM.

    Args:
        certificate: The certificate to serialize.

    Returns:
        The PEM text.
    """
    return certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")


def certificate_from_pem(pem: str) -> x509.Certificate:
    """Parse a PEM certificate.

    Args:
        pem: The PEM text.

    Returns:
        The parsed certificate.

    Raises:
        McpCaError: If the PEM is not a readable certificate.
    """
    try:
        return x509.load_pem_x509_certificate(pem.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise McpCaError("Certificate is not a readable PEM") from exc


def build_root_certificate(
    key: ec.EllipticCurvePrivateKey,
    *,
    common_name: str,
    not_before: datetime,
    not_after: datetime,
) -> x509.Certificate:
    """Build and self-sign the root certificate.

    ``pathlen:0`` keeps the root from minting intermediates: every leaf this
    deployment issues chains directly to it, so a one-step chain is the only
    shape verification ever has to accept.

    Args:
        key: The root's private key; its public half becomes the subject key.
        common_name: Subject and issuer common name.
        not_before: Start of the validity window.
        not_after: End of the validity window.

    Returns:
        The self-signed root certificate.
    """
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    public_key = key.public_key()
    return (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False
        )
        .sign(key, HASH_ALGORITHM)
    )


def sign_leaf_certificate(
    ca: RootCertificateAuthority,
    *,
    public_key: ec.EllipticCurvePublicKey,
    subject: x509.Name,
    sans: list[x509.GeneralName],
    not_before: datetime,
    not_after: datetime,
    extended_key_usage: Sequence[ObjectIdentifier] = (ExtendedKeyUsageOID.CLIENT_AUTH,),
) -> x509.Certificate:
    """Sign a leaf certificate with the root.

    Every leaf carries ``digitalSignature``: a tool certificate signs
    proof-of-possession challenges with it, and a TLS leaf needs it for the
    ECDHE handshake either way. Everything that identifies *what* the
    certificate authorizes lives in ``sans`` -- see
    :mod:`infrastructure.mcp_certificate` for the URN grammar.

    ``extended_key_usage`` is what separates the kinds of leaf this root signs.
    It defaults to ``clientAuth``, which covers every tool certificate, so the
    same material a run presents to the gateway also works unchanged as a TLS
    client certificate. Passing ``serverAuth`` instead is how the MCP proxy's
    own listener gets a certificate the backend trusts, from the one root both
    sides already share.

    Args:
        ca: The loaded root that signs.
        public_key: Public half of the leaf's freshly generated key pair.
        subject: The leaf's subject name.
        sans: Subject alternative names carrying the binding and tool grants.
        not_before: Start of the validity window.
        not_after: End of the validity window.
        extended_key_usage: What the leaf may be used for. Defaults to client
            authentication.

    Returns:
        The signed leaf certificate.

    Raises:
        McpCaError: If ``sans`` is empty, or ``extended_key_usage`` is. A leaf
            with no SAN carries no binding and no tool grant, and one with no
            extended key usage is refused by
            :func:`infrastructure.mcp_certificate.verify_certificate`; either
            way verification could never accept it, so failing here turns a
            silently always-denied certificate into a loud error.
    """
    if not sans:
        raise McpCaError("A leaf certificate must carry at least one SAN entry")
    if not extended_key_usage:
        raise McpCaError("A leaf certificate must declare an extended key usage")
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca.certificate.subject)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage(list(extended_key_usage)), critical=False)
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                ca.private_key.public_key()
            ),
            critical=False,
        )
        .sign(ca.private_key, HASH_ALGORITHM)
    )


def _load(row: MCPCertificateAuthority) -> RootCertificateAuthority:
    """Decrypt and parse a stored CA row into usable key material.

    Args:
        row: The persisted certificate authority.

    Returns:
        The loaded root.

    Raises:
        McpCaError: If the stored key cannot be decrypted (the Fernet key
            changed) or either PEM is unparseable.
    """
    try:
        key_pem = get_secret_cipher().decrypt(row.private_key_encrypted)
    except ValueError as exc:
        raise McpCaError(
            f"Cannot decrypt the private key of certificate authority {row.id!r}; "
            "the secret encryption key has changed"
        ) from exc
    return RootCertificateAuthority(
        ca_id=row.id,
        certificate=certificate_from_pem(row.certificate_pem),
        private_key=private_key_from_pem(key_pem),
    )


async def load_or_create_root_ca(
    repo: McpCertificateAuthorityRepository,
) -> RootCertificateAuthority:
    """Return the active root CA, generating it on first use.

    Takes a repository rather than a session so callers in the service layer
    stay free of direct database handles, matching how every other service
    reaches persistence.

    Concurrent callers on different replicas may both find no active row and
    both generate a candidate. The partial unique index on ``active`` lets
    exactly one insert win; the loser swallows the
    :class:`~repositories.exceptions.UniqueViolationError` and re-reads, so both
    callers end up on the same root.

    Args:
        repo: Repository providing certificate-authority persistence.

    Returns:
        The loaded active root.

    Raises:
        McpCaError: If the stored root cannot be decrypted or parsed, or if the
            insert lost the race but no active row is readable afterwards.
    """
    existing = await repo.get_active()
    if existing is not None:
        return _load(existing)

    settings = get_settings()
    key = generate_key()
    not_before = datetime.now(UTC)
    not_after = not_before + timedelta(days=settings.mcp_ca_validity_days)
    certificate = build_root_certificate(
        key,
        common_name=settings.mcp_ca_common_name,
        not_before=not_before,
        not_after=not_after,
    )
    payload = McpCertificateAuthorityCreate(
        common_name=settings.mcp_ca_common_name,
        certificate_pem=certificate_to_pem(certificate),
        private_key_encrypted=get_secret_cipher().encrypt(private_key_to_pem(key)),
        not_before=not_before,
        not_after=not_after,
    )
    try:
        row = await repo.create(payload, user_id=SYSTEM_USER_ID)
    except UniqueViolationError:
        # Another writer created the root first. The candidate key was never
        # persisted, so discard it and use theirs.
        raced = await repo.get_active()
        if raced is None:
            raise McpCaError(
                "Lost the race to create the root certificate authority but no "
                "active authority is readable"
            ) from None
        return _load(raced)

    logger.info(
        "Generated the MCP approval root certificate authority %r (id=%s), valid until %s",
        settings.mcp_ca_common_name,
        row.id,
        not_after.isoformat(),
    )
    return _load(row)
