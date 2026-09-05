"""Tests for the TLS material the backend issues for the MCP proxy channel.

The root CA lives in the database, so these run against a throwaway engine with
the seeded system user — the same fixture shape as ``test_mcp_ca.py``.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

import models  # noqa: F401 — registers every table on SQLModel.metadata
from config import get_settings
from infrastructure.mcp_ca import (
    RootCertificateAuthority,
    build_root_certificate,
    certificate_from_pem,
    certificate_to_pem,
    generate_key,
    load_or_create_root_ca,
    private_key_to_pem,
    sign_leaf_certificate,
)
from infrastructure.mcp_certificate import (
    BACKEND_SERVICE_NAME,
    CertificateVerificationError,
    extract_claims,
    service_name,
    verify_certificate,
)
from infrastructure.mcp_transport_tls import (
    CA_FILE,
    CLIENT_CERT_FILE,
    CLIENT_KEY_FILE,
    SERVER_CERT_FILE,
    SERVER_KEY_FILE,
    backend_client_credentials,
    provision_transport_credentials,
    proxy_server_credentials,
)
from repositories.mcp_ca import SqlMcpCertificateAuthorityRepository
from tests._engine import make_test_engine
from tests._seed import seed_users


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """A throwaway engine with the full schema and the seeded users."""
    mem_engine = await make_test_engine()
    await seed_users(mem_engine)
    try:
        yield mem_engine
    finally:
        await mem_engine.dispose()


@pytest.fixture
def tls_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Point both TLS directories at a temporary location.

    Returns:
        The ``(published, backend_private)`` pair.
    """
    published = tmp_path / "published"
    private = tmp_path / "private"
    monkeypatch.setenv("MCP_PROXY_TLS_DIR", str(published))
    monkeypatch.setenv("MCP_BACKEND_TLS_DIR", str(private))
    return published, private


async def _provision(engine: AsyncEngine) -> None:
    """Run one provisioning pass against the test engine."""
    async with AsyncSession(engine) as session:
        await provision_transport_credentials(session)


def _read(path: Path) -> x509.Certificate:
    """Load a written certificate."""
    return certificate_from_pem(path.read_text(encoding="ascii"))


# --------------------------------------------------------------------------
# When it runs at all
# --------------------------------------------------------------------------


async def test_nothing_is_written_without_a_proxy_url(
    engine: AsyncEngine, tls_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A backend that reaches MCP servers itself has no second end to equip."""
    monkeypatch.delenv("MCP_PROXY_URL", raising=False)
    published, private = tls_dirs

    await _provision(engine)

    assert not published.exists()
    assert not private.exists()


@pytest.fixture
def proxy_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn on the remote-execution path for the tests below."""
    monkeypatch.setenv("MCP_PROXY_URL", "https://mcp-proxy:8443")


# --------------------------------------------------------------------------
# What gets written
# --------------------------------------------------------------------------


async def test_provisioning_writes_both_ends_and_the_root(
    engine: AsyncEngine, tls_dirs: tuple[Path, Path], proxy_url: None
) -> None:
    published, private = tls_dirs

    await _provision(engine)

    assert (published / CA_FILE).is_file()
    assert (published / SERVER_CERT_FILE).is_file()
    assert (published / SERVER_KEY_FILE).is_file()
    assert (private / CLIENT_CERT_FILE).is_file()
    assert (private / CLIENT_KEY_FILE).is_file()


async def test_the_backend_key_is_never_published_to_the_proxy(
    engine: AsyncEngine, tls_dirs: tuple[Path, Path], proxy_url: None
) -> None:
    """A user-registered MCP server runs in that container; it must not read this."""
    published, _ = tls_dirs

    await _provision(engine)

    assert sorted(p.name for p in published.iterdir()) == [
        CA_FILE,
        SERVER_CERT_FILE,
        SERVER_KEY_FILE,
    ]


async def test_the_published_root_is_the_one_that_signs_tool_certificates(
    engine: AsyncEngine, tls_dirs: tuple[Path, Path], proxy_url: None
) -> None:
    """One root, so the proxy trusts tool certificates without a second anchor."""
    published, _ = tls_dirs

    await _provision(engine)

    async with AsyncSession(engine) as session:
        ca = await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(session))
    assert (published / CA_FILE).read_text(encoding="ascii") == certificate_to_pem(
        ca.certificate
    )


async def test_the_proxy_leaf_is_a_server_certificate(
    engine: AsyncEngine, tls_dirs: tuple[Path, Path], proxy_url: None
) -> None:
    published, _ = tls_dirs

    await _provision(engine)
    leaf = _read(published / SERVER_CERT_FILE)

    eku = leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
    assert list(eku.value) == [ExtendedKeyUsageOID.SERVER_AUTH]
    san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    assert san.value.get_values_for_type(x509.DNSName) == ["mcp-proxy"]


async def test_the_backend_leaf_is_a_client_certificate_naming_the_backend(
    engine: AsyncEngine, tls_dirs: tuple[Path, Path], proxy_url: None
) -> None:
    _, private = tls_dirs

    await _provision(engine)
    leaf = _read(private / CLIENT_CERT_FILE)

    assert service_name(leaf) == BACKEND_SERVICE_NAME
    eku = leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
    assert list(eku.value) == [ExtendedKeyUsageOID.CLIENT_AUTH]


async def test_the_backend_leaf_verifies_against_the_published_root(
    engine: AsyncEngine, tls_dirs: tuple[Path, Path], proxy_url: None
) -> None:
    """What the proxy will do on every request, done here against the same files."""
    published, private = tls_dirs

    await _provision(engine)

    verify_certificate(
        _read(private / CLIENT_CERT_FILE),
        ca_certificate=_read(published / CA_FILE),
        now=datetime.now(UTC),
    )


async def test_the_backend_leaf_grants_no_tool(
    engine: AsyncEngine, tls_dirs: tuple[Path, Path], proxy_url: None
) -> None:
    """It authenticates a component, so it must not read as a grant over anything."""
    _, private = tls_dirs

    await _provision(engine)

    with pytest.raises(CertificateVerificationError, match="unrecognized subject"):
        extract_claims(_read(private / CLIENT_CERT_FILE))


async def test_the_reported_paths_are_the_ones_written(
    engine: AsyncEngine, tls_dirs: tuple[Path, Path], proxy_url: None
) -> None:
    """The two accessors are what the executor and the proxy read; keep them honest."""
    await _provision(engine)

    for credentials in (backend_client_credentials(), proxy_server_credentials()):
        assert credentials.ca_certificate.is_file()
        assert credentials.certificate.is_file()
        assert credentials.private_key.is_file()


# --------------------------------------------------------------------------
# Reissuing
# --------------------------------------------------------------------------


async def test_a_second_pass_leaves_healthy_material_alone(
    engine: AsyncEngine, tls_dirs: tuple[Path, Path], proxy_url: None
) -> None:
    """An ordinary restart must not hand the proxy a certificate it is not holding."""
    published, private = tls_dirs
    await _provision(engine)
    before = {
        path: path.read_bytes() for path in (*published.iterdir(), *private.iterdir())
    }

    await _provision(engine)

    assert {path: path.read_bytes() for path in before} == before


async def test_a_leaf_close_to_expiry_is_reissued(
    engine: AsyncEngine,
    tls_dirs: tuple[Path, Path],
    proxy_url: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A one-day certificate is always inside the renewal window."""
    monkeypatch.setenv("MCP_TRANSPORT_CERT_VALIDITY_DAYS", "1")
    get_settings.cache_clear()
    published, _ = tls_dirs
    await _provision(engine)
    first = _read(published / SERVER_CERT_FILE).serial_number

    await _provision(engine)

    assert _read(published / SERVER_CERT_FILE).serial_number != first


async def test_a_leaf_whose_key_went_missing_is_reissued(
    engine: AsyncEngine, tls_dirs: tuple[Path, Path], proxy_url: None
) -> None:
    """The half-written state a run interrupted between the two writes leaves behind."""
    published, _ = tls_dirs
    await _provision(engine)
    first = _read(published / SERVER_CERT_FILE).serial_number
    (published / SERVER_KEY_FILE).unlink()

    await _provision(engine)

    assert (published / SERVER_KEY_FILE).is_file()
    assert _read(published / SERVER_CERT_FILE).serial_number != first


async def test_a_leaf_from_another_root_is_reissued(
    engine: AsyncEngine, tls_dirs: tuple[Path, Path], proxy_url: None
) -> None:
    """Material left over from another deployment would be refused by the peer."""
    published, _ = tls_dirs
    now = datetime.now(UTC)
    foreign_key = generate_key()
    foreign = RootCertificateAuthority(
        ca_id="ca-foreign",
        certificate=build_root_certificate(
            foreign_key,
            common_name="Someone else",
            not_before=now - timedelta(days=1),
            not_after=now + timedelta(days=365),
        ),
        private_key=foreign_key,
    )
    leaf_key = generate_key()
    published.mkdir(parents=True)
    (published / SERVER_CERT_FILE).write_text(
        certificate_to_pem(
            sign_leaf_certificate(
                foreign,
                public_key=leaf_key.public_key(),
                subject=foreign.certificate.subject,
                sans=[x509.DNSName("mcp-proxy")],
                not_before=now,
                not_after=now + timedelta(days=365),
                extended_key_usage=[ExtendedKeyUsageOID.SERVER_AUTH],
            )
        ),
        encoding="ascii",
    )
    (published / SERVER_KEY_FILE).write_text(
        private_key_to_pem(leaf_key), encoding="ascii"
    )

    await _provision(engine)

    assert _read(published / SERVER_CERT_FILE).issuer != foreign.certificate.subject


async def test_unreadable_material_is_replaced_rather_than_raising(
    engine: AsyncEngine, tls_dirs: tuple[Path, Path], proxy_url: None
) -> None:
    published, _ = tls_dirs
    published.mkdir(parents=True)
    (published / SERVER_CERT_FILE).write_text("not a pem", encoding="ascii")
    (published / SERVER_KEY_FILE).write_text("not a pem either", encoding="ascii")

    await _provision(engine)

    leaf = _read(published / SERVER_CERT_FILE)
    async with AsyncSession(engine) as session:
        ca = await load_or_create_root_ca(SqlMcpCertificateAuthorityRepository(session))
    assert leaf.issuer == ca.certificate.subject
