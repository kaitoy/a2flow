"""Tests for the internal MCP root certificate authority.

Covers generation on first use, the concurrent-generation race the partial
unique index resolves, that the private key is only ever persisted as
ciphertext, and the X.509 shape of both the root and the leaves it signs.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

import models  # noqa: F401 — registers every table on SQLModel.metadata
from infrastructure.mcp_ca import (
    HASH_ALGORITHM,
    McpCaError,
    build_root_certificate,
    certificate_from_pem,
    certificate_to_pem,
    generate_key,
    load_or_create_root_ca,
    private_key_from_pem,
    private_key_to_pem,
    sign_leaf_certificate,
)
from infrastructure.mcp_certificate import (
    CertificateVerificationError,
    verify_certificate,
)
from infrastructure.secret_cipher import get_secret_cipher
from models.mcp_ca import MCPCertificateAuthority
from repositories._integrity import is_unique_error
from repositories.mcp_ca import SqlMcpCertificateAuthorityRepository
from tests._engine import make_test_engine
from tests._seed import seed_users


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """A throwaway engine with the full schema and the seeded users.

    The CA rows carry ``created_by`` / ``updated_by`` foreign keys to
    ``users.id``, so the system user has to exist before anything is written.
    """
    mem_engine = await make_test_engine()
    await seed_users(mem_engine)
    try:
        yield mem_engine
    finally:
        await mem_engine.dispose()


async def _count_authorities(engine: AsyncEngine) -> int:
    """Return how many certificate-authority rows exist."""
    async with AsyncSession(engine) as session:
        result = await session.exec(select(MCPCertificateAuthority))
        return len(result.all())


# --------------------------------------------------------------------------
# Generation and loading
# --------------------------------------------------------------------------


async def test_load_or_create_generates_the_root_on_first_use(
    engine: AsyncEngine,
) -> None:
    async with AsyncSession(engine) as session:
        ca = await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(session))

    assert await _count_authorities(engine) == 1
    assert isinstance(ca.private_key, ec.EllipticCurvePrivateKey)
    assert ca.certificate.subject == ca.certificate.issuer


async def test_load_or_create_reuses_the_existing_root(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        first = await load_or_create_root_ca(
            SqlMcpCertificateAuthorityRepository(session)
        )
    async with AsyncSession(engine) as session:
        second = await load_or_create_root_ca(
            SqlMcpCertificateAuthorityRepository(session)
        )

    assert await _count_authorities(engine) == 1
    assert first.ca_id == second.ca_id
    assert first.certificate.serial_number == second.certificate.serial_number


async def test_private_key_is_stored_only_as_ciphertext(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        ca = await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(session))

    async with AsyncSession(engine) as session:
        row = await session.get(MCPCertificateAuthority, ca.ca_id)
    assert row is not None
    assert "PRIVATE KEY" not in row.private_key_encrypted
    # The ciphertext is the real key, not a placeholder.
    decrypted = get_secret_cipher().decrypt(row.private_key_encrypted)
    assert private_key_from_pem(decrypted).private_numbers() == (
        ca.private_key.private_numbers()
    )


async def test_load_fails_loudly_when_the_fernet_key_changed(
    engine: AsyncEngine,
) -> None:
    async with AsyncSession(engine) as session:
        ca = await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(session))

    async with AsyncSession(engine) as session:
        row = await session.get(MCPCertificateAuthority, ca.ca_id)
        assert row is not None
        # Ciphertext from a different Fernet key is indistinguishable from a
        # rotated deployment key.
        row.private_key_encrypted = "gAAAAABmtampered-with-ciphertext"
        session.add(row)
        await session.commit()

    async with AsyncSession(engine) as session:
        with pytest.raises(McpCaError, match="secret encryption key has changed"):
            await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(session))


async def test_only_one_authority_may_be_active(engine: AsyncEngine) -> None:
    """The partial unique index is what makes the generation race safe."""
    async with AsyncSession(engine) as session:
        await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(session))

    key = generate_key()
    now = datetime.now(UTC)
    duplicate = MCPCertificateAuthority(
        common_name="Second root",
        certificate_pem=certificate_to_pem(
            build_root_certificate(
                key,
                common_name="Second root",
                not_before=now,
                not_after=now + timedelta(days=1),
            )
        ),
        private_key_encrypted=get_secret_cipher().encrypt(private_key_to_pem(key)),
        not_before=now,
        not_after=now + timedelta(days=1),
        active=True,
        created_by="alice",
        updated_by="alice",
    )
    async with AsyncSession(engine) as session:
        session.add(duplicate)
        with pytest.raises(IntegrityError) as exc_info:
            await session.commit()
    # SQLite and PostgreSQL word the failure differently, so assert through the
    # same classifier the repositories use rather than matching one dialect's text.
    assert is_unique_error(exc_info.value)


# --------------------------------------------------------------------------
# Root certificate shape
# --------------------------------------------------------------------------


async def test_root_certificate_is_a_pathlen_zero_ca(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        ca = await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(session))

    basic = ca.certificate.extensions.get_extension_for_class(x509.BasicConstraints)
    assert basic.critical is True
    assert basic.value.ca is True
    assert basic.value.path_length == 0

    usage = ca.certificate.extensions.get_extension_for_class(x509.KeyUsage)
    assert usage.value.key_cert_sign is True
    assert usage.value.crl_sign is True
    assert usage.value.digital_signature is False


async def test_root_certificate_is_self_signed(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        ca = await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(session))

    public_key = ca.certificate.public_key()
    assert isinstance(public_key, ec.EllipticCurvePublicKey)
    # Raises InvalidSignature if the root was not signed by its own key.
    public_key.verify(
        ca.certificate.signature,
        ca.certificate.tbs_certificate_bytes,
        ec.ECDSA(HASH_ALGORITHM),
    )


# --------------------------------------------------------------------------
# Leaf signing
# --------------------------------------------------------------------------


def _leaf_subject() -> x509.Name:
    """A minimal subject standing in for a workflow task's leaf subject."""
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "task-1")])


async def test_signed_leaf_verifies_against_the_root(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        ca = await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(session))

    leaf_key = generate_key()
    now = datetime.now(UTC)
    leaf = sign_leaf_certificate(
        ca,
        public_key=leaf_key.public_key(),
        subject=_leaf_subject(),
        sans=[x509.UniformResourceIdentifier("urn:a2flow:binding:example")],
        not_before=now,
        not_after=now + timedelta(hours=1),
    )

    assert leaf.issuer == ca.certificate.subject
    root_public = ca.certificate.public_key()
    assert isinstance(root_public, ec.EllipticCurvePublicKey)
    root_public.verify(
        leaf.signature, leaf.tbs_certificate_bytes, ec.ECDSA(HASH_ALGORITHM)
    )


async def test_leaf_from_a_different_root_does_not_verify(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        ca = await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(session))

    leaf_key = generate_key()
    now = datetime.now(UTC)
    leaf = sign_leaf_certificate(
        ca,
        public_key=leaf_key.public_key(),
        subject=_leaf_subject(),
        sans=[x509.UniformResourceIdentifier("urn:a2flow:binding:example")],
        not_before=now,
        not_after=now + timedelta(hours=1),
    )

    foreign_key = generate_key()
    foreign_public = foreign_key.public_key()
    with pytest.raises(InvalidSignature):
        foreign_public.verify(
            leaf.signature, leaf.tbs_certificate_bytes, ec.ECDSA(HASH_ALGORITHM)
        )


async def test_leaf_carries_client_auth_and_digital_signature(
    engine: AsyncEngine,
) -> None:
    """The leaf has to work unchanged as a TLS client certificate later."""
    async with AsyncSession(engine) as session:
        ca = await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(session))

    now = datetime.now(UTC)
    leaf = sign_leaf_certificate(
        ca,
        public_key=generate_key().public_key(),
        subject=_leaf_subject(),
        sans=[x509.UniformResourceIdentifier("urn:a2flow:binding:example")],
        not_before=now,
        not_after=now + timedelta(hours=1),
    )

    eku = leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
    assert ExtendedKeyUsageOID.CLIENT_AUTH in eku.value

    usage = leaf.extensions.get_extension_for_class(x509.KeyUsage)
    assert usage.value.digital_signature is True
    assert usage.value.key_cert_sign is False

    basic = leaf.extensions.get_extension_for_class(x509.BasicConstraints)
    assert basic.value.ca is False


async def test_leaf_sans_are_preserved_in_order(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        ca = await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(session))

    uris = [
        "urn:a2flow:binding:tenant/t1/execution/e1/task/k1/approval/a1",
        "urn:a2flow:tool:server-1/read_file",
        "urn:a2flow:tool:server-1/write_file",
    ]
    now = datetime.now(UTC)
    leaf = sign_leaf_certificate(
        ca,
        public_key=generate_key().public_key(),
        subject=_leaf_subject(),
        sans=[x509.UniformResourceIdentifier(uri) for uri in uris],
        not_before=now,
        not_after=now + timedelta(hours=1),
    )

    san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    assert san.value.get_values_for_type(x509.UniformResourceIdentifier) == uris


async def test_signing_without_sans_is_rejected(engine: AsyncEngine) -> None:
    """A SAN-less leaf could never be accepted, so refuse to mint one."""
    async with AsyncSession(engine) as session:
        ca = await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(session))

    now = datetime.now(UTC)
    with pytest.raises(McpCaError, match="at least one SAN entry"):
        sign_leaf_certificate(
            ca,
            public_key=generate_key().public_key(),
            subject=_leaf_subject(),
            sans=[],
            not_before=now,
            not_after=now + timedelta(hours=1),
        )


async def test_a_leaf_can_be_signed_for_server_authentication(
    engine: AsyncEngine,
) -> None:
    """The MCP proxy's listener gets its certificate from this same root."""
    async with AsyncSession(engine) as session:
        ca = await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(session))

    now = datetime.now(UTC)
    leaf = sign_leaf_certificate(
        ca,
        public_key=generate_key().public_key(),
        subject=_leaf_subject(),
        sans=[x509.DNSName("mcp-proxy")],
        not_before=now,
        not_after=now + timedelta(hours=1),
        extended_key_usage=[ExtendedKeyUsageOID.SERVER_AUTH],
    )

    eku = leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
    assert list(eku.value) == [ExtendedKeyUsageOID.SERVER_AUTH]
    # digitalSignature is still set: the ECDHE handshake needs it whichever way
    # round the certificate is used.
    usage = leaf.extensions.get_extension_for_class(x509.KeyUsage)
    assert usage.value.digital_signature is True


async def test_a_server_leaf_is_refused_as_a_client_certificate(
    engine: AsyncEngine,
) -> None:
    """Sharing one root is safe because the usage check is what separates the kinds."""
    async with AsyncSession(engine) as session:
        ca = await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(session))

    now = datetime.now(UTC)
    leaf = sign_leaf_certificate(
        ca,
        public_key=generate_key().public_key(),
        subject=_leaf_subject(),
        sans=[x509.DNSName("mcp-proxy")],
        not_before=now - timedelta(minutes=1),
        not_after=now + timedelta(hours=1),
        extended_key_usage=[ExtendedKeyUsageOID.SERVER_AUTH],
    )

    with pytest.raises(
        CertificateVerificationError, match="not marked for client authentication"
    ):
        verify_certificate(leaf, ca_certificate=ca.certificate, now=now)


async def test_signing_without_an_extended_key_usage_is_rejected(
    engine: AsyncEngine,
) -> None:
    """Verification requires the extension, so a leaf without one is always denied."""
    async with AsyncSession(engine) as session:
        ca = await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(session))

    now = datetime.now(UTC)
    with pytest.raises(McpCaError, match="extended key usage"):
        sign_leaf_certificate(
            ca,
            public_key=generate_key().public_key(),
            subject=_leaf_subject(),
            sans=[x509.DNSName("mcp-proxy")],
            not_before=now,
            not_after=now + timedelta(hours=1),
            extended_key_usage=[],
        )


# --------------------------------------------------------------------------
# PEM round-trips
# --------------------------------------------------------------------------


def test_private_key_pem_round_trip() -> None:
    key = generate_key()
    assert (
        private_key_from_pem(private_key_to_pem(key)).private_numbers()
        == key.private_numbers()
    )


def test_certificate_pem_round_trip() -> None:
    key = generate_key()
    now = datetime.now(UTC)
    certificate = build_root_certificate(
        key, common_name="Round trip", not_before=now, not_after=now + timedelta(days=1)
    )
    assert (
        certificate_from_pem(certificate_to_pem(certificate)).serial_number
        == certificate.serial_number
    )


def test_unparseable_pems_raise_mcp_ca_error() -> None:
    with pytest.raises(McpCaError, match="not a readable PEM"):
        certificate_from_pem("not a certificate")
    with pytest.raises(McpCaError, match="not a readable PEM"):
        private_key_from_pem("not a key")
