"""Tests for the certificate grammar and the verification steps that read it.

Everything here is pure, so the root CA is built in-process rather than loaded
from the database.
"""

from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from infrastructure.mcp_ca import (
    RootCertificateAuthority,
    build_root_certificate,
    generate_key,
    sign_leaf_certificate,
)
from infrastructure.mcp_certificate import (
    CertificateBinding,
    CertificateVerificationError,
    build_binding_urn,
    build_tool_urn,
    canonical_json,
    extract_claims,
    parse_binding_urn,
    parse_tool_urn,
    pop_digest,
    sign_pop_digest,
    verify_certificate,
    verify_pop_signature,
)

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
WINDOW = timedelta(seconds=60)

BINDING = CertificateBinding(
    tenant_id="tenant-default",
    execution_id="exec-1",
    task_id="task-1",
    approval_id="approval-1",
)


def _root(common_name: str = "Test root") -> RootCertificateAuthority:
    """Build a throwaway in-memory root CA."""
    key = generate_key()
    certificate = build_root_certificate(
        key,
        common_name=common_name,
        not_before=NOW - timedelta(days=1),
        not_after=NOW + timedelta(days=365),
    )
    return RootCertificateAuthority(
        ca_id="ca-1", certificate=certificate, private_key=key
    )


def _leaf(
    ca: RootCertificateAuthority,
    *,
    key: ec.EllipticCurvePrivateKey | None = None,
    binding: CertificateBinding | None = BINDING,
    tools: tuple[tuple[str, str], ...] = (("server-1", "read_file"),),
    extra_sans: tuple[str, ...] = (),
    not_before: datetime | None = None,
    not_after: datetime | None = None,
) -> x509.Certificate:
    """Sign a leaf carrying the given binding and tool grants."""
    sans: list[x509.GeneralName] = []
    if binding is not None:
        sans.append(x509.UniformResourceIdentifier(build_binding_urn(binding)))
    sans.extend(
        x509.UniformResourceIdentifier(build_tool_urn(server, tool))
        for server, tool in tools
    )
    sans.extend(x509.UniformResourceIdentifier(uri) for uri in extra_sans)
    return sign_leaf_certificate(
        ca,
        public_key=(key or generate_key()).public_key(),
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "task-1")]),
        sans=sans,
        not_before=not_before or NOW - timedelta(minutes=1),
        not_after=not_after or NOW + timedelta(hours=1),
    )


# ---------------------------------------------------------------------------
# URN grammar
# ---------------------------------------------------------------------------


def test_binding_urn_round_trip() -> None:
    assert parse_binding_urn(build_binding_urn(BINDING)) == BINDING


def test_initiator_binding_urn_round_trip() -> None:
    """The second grantor form, which carries a user id instead of an approval."""
    binding = CertificateBinding(
        tenant_id="tenant-1",
        execution_id="exec-1",
        task_id="task-1",
        initiator_id="user-1",
    )
    urn = build_binding_urn(binding)
    assert urn.endswith("/initiator/user-1")
    assert parse_binding_urn(urn) == binding


def test_a_binding_names_exactly_one_grantor() -> None:
    """Neither and both are rejected where the object is built, not at each use.

    A binding is constructed both when signing a certificate and when parsing a
    presented one, so the invariant has to hold in both directions.
    """
    for kwargs in (
        {},
        {"approval_id": "a1", "initiator_id": "u1"},
    ):
        with pytest.raises(CertificateVerificationError, match="exactly one grantor"):
            CertificateBinding(
                tenant_id="tenant-1",
                execution_id="exec-1",
                task_id="task-1",
                **kwargs,
            )


def test_tool_urn_round_trip() -> None:
    assert parse_tool_urn(build_tool_urn("server-1", "read_file")) == (
        "server-1",
        "read_file",
    )


def test_tool_urn_survives_a_slash_in_the_tool_name() -> None:
    """``ToolName`` places no character restriction, so ``/`` must not split it."""
    urn = build_tool_urn("server-1", "files/read")
    assert parse_tool_urn(urn) == ("server-1", "files/read")


def test_tool_urn_survives_exotic_tool_names() -> None:
    for name in ("a b", "π/λ", "with%20percent", "colon:name", "trailing/"):
        assert parse_tool_urn(build_tool_urn("server-1", name)) == ("server-1", name)


@pytest.mark.parametrize(
    "urn",
    [
        "urn:a2flow:binding:tenant/t1/execution/e1/task/k1",  # too few segments
        "urn:a2flow:binding:tenant/t1/execution/e1/task/k1/approval/a1/extra/x",
        "urn:a2flow:binding:renant/t1/execution/e1/task/k1/approval/a1",  # bad label
        "urn:a2flow:binding:tenant//execution/e1/task/k1/approval/a1",  # empty value
        # An unrecognized grantor label, which is the failure a future third
        # grant kind would produce against a verifier that predates it.
        "urn:a2flow:binding:tenant/t1/execution/e1/task/k1/somebody/s1",
        "urn:a2flow:binding:tenant/t1/execution/e1/task/k1/initiator/",
        "urn:something:else",
    ],
)
def test_malformed_binding_urns_are_rejected(urn: str) -> None:
    with pytest.raises(CertificateVerificationError, match="binding URN is malformed"):
        parse_binding_urn(urn)


@pytest.mark.parametrize(
    "urn", ["urn:a2flow:tool:server-only", "urn:a2flow:tool:/tool", "urn:other:x/y"]
)
def test_malformed_tool_urns_are_rejected(urn: str) -> None:
    with pytest.raises(
        CertificateVerificationError, match="tool grant URN is malformed"
    ):
        parse_tool_urn(urn)


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------


def test_extract_claims_reads_the_binding_and_grants() -> None:
    ca = _root()
    leaf = _leaf(ca, tools=(("server-1", "read_file"), ("server-2", "query")))

    claims = extract_claims(leaf)

    assert claims.binding == BINDING
    assert claims.allowed_tools == frozenset(
        {("server-1", "read_file"), ("server-2", "query")}
    )
    assert claims.serial_number == str(leaf.serial_number)
    assert claims.grants("server-1", "read_file")
    assert not claims.grants("server-1", "write_file")


def test_extract_claims_rejects_a_certificate_with_no_binding() -> None:
    ca = _root()
    leaf = _leaf(ca, binding=None)

    with pytest.raises(CertificateVerificationError, match="exactly one binding URN"):
        extract_claims(leaf)


def test_extract_claims_rejects_two_bindings() -> None:
    """Two bindings would let a certificate claim authority over two runs."""
    ca = _root()
    other = CertificateBinding(
        tenant_id="tenant-default",
        execution_id="exec-2",
        task_id="task-2",
        approval_id="approval-2",
    )
    leaf = _leaf(ca, extra_sans=(build_binding_urn(other),))

    with pytest.raises(CertificateVerificationError, match="exactly one binding URN"):
        extract_claims(leaf)


def test_extract_claims_rejects_an_unrecognized_san() -> None:
    """An unknown URN kind fails loudly rather than being silently skipped."""
    ca = _root()
    leaf = _leaf(ca, extra_sans=("urn:a2flow:future:something",))

    with pytest.raises(CertificateVerificationError, match="unrecognized subject"):
        extract_claims(leaf)


# ---------------------------------------------------------------------------
# Certificate verification
# ---------------------------------------------------------------------------


def test_verify_accepts_a_well_formed_leaf() -> None:
    ca = _root()
    verify_certificate(_leaf(ca), ca_certificate=ca.certificate, now=NOW)


def test_verify_rejects_a_leaf_from_another_root() -> None:
    ca = _root("Ours")
    foreign = _root("Theirs")
    leaf = _leaf(foreign)

    with pytest.raises(CertificateVerificationError, match="not issued by"):
        verify_certificate(leaf, ca_certificate=ca.certificate, now=NOW)


def test_verify_rejects_a_leaf_whose_signature_was_swapped() -> None:
    """Same issuer name, different key: only the signature check catches this."""
    ca = _root("Same name")
    impostor = _root("Same name")
    leaf = _leaf(impostor)

    with pytest.raises(CertificateVerificationError, match="signature does not verify"):
        verify_certificate(leaf, ca_certificate=ca.certificate, now=NOW)


def test_verify_rejects_an_expired_leaf() -> None:
    ca = _root()
    leaf = _leaf(
        ca, not_before=NOW - timedelta(hours=3), not_after=NOW - timedelta(hours=1)
    )

    with pytest.raises(CertificateVerificationError, match="has expired"):
        verify_certificate(leaf, ca_certificate=ca.certificate, now=NOW)


def test_verify_rejects_a_leaf_that_is_not_valid_yet() -> None:
    ca = _root()
    leaf = _leaf(
        ca, not_before=NOW + timedelta(hours=1), not_after=NOW + timedelta(hours=2)
    )

    with pytest.raises(CertificateVerificationError, match="not valid yet"):
        verify_certificate(leaf, ca_certificate=ca.certificate, now=NOW)


def test_verify_rejects_the_root_presented_as_a_client_certificate() -> None:
    """The root is self-signed, so the issuer and signature checks both pass."""
    ca = _root()

    with pytest.raises(
        CertificateVerificationError, match="cannot be used as a client certificate"
    ):
        verify_certificate(ca.certificate, ca_certificate=ca.certificate, now=NOW)


# ---------------------------------------------------------------------------
# Proof of possession
# ---------------------------------------------------------------------------


def _digest(**overrides: object) -> bytes:
    """Build a digest over a baseline call, with fields overridden."""
    fields: dict[str, object] = {
        "session_id": "sess-1",
        "mcp_server_id": "server-1",
        "tool_name": "read_file",
        "arguments": {"path": "/etc/hosts", "limit": 10},
        "nonce": "nonce-1",
        "timestamp": NOW,
    }
    fields.update(overrides)
    return pop_digest(**fields)  # type: ignore[arg-type]


def test_canonical_json_is_insertion_order_independent() -> None:
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})


def test_digest_is_stable_for_the_same_call() -> None:
    assert _digest() == _digest()
    assert _digest(arguments={"limit": 10, "path": "/etc/hosts"}) == _digest()


@pytest.mark.parametrize(
    "override",
    [
        {"session_id": "sess-2"},
        {"mcp_server_id": "server-2"},
        {"tool_name": "write_file"},
        {"arguments": {"path": "/etc/shadow", "limit": 10}},
        {"nonce": "nonce-2"},
        {"timestamp": NOW + timedelta(seconds=1)},
    ],
)
def test_digest_changes_when_any_field_changes(override: dict[str, object]) -> None:
    assert _digest(**override) != _digest()


def test_verify_pop_accepts_a_fresh_signature() -> None:
    ca = _root()
    key = generate_key()
    leaf = _leaf(ca, key=key)
    digest = _digest()

    verify_pop_signature(
        leaf,
        signature=sign_pop_digest(key, digest),
        digest=digest,
        timestamp=NOW,
        now=NOW,
        window=WINDOW,
    )


def test_verify_pop_rejects_a_signature_from_another_key() -> None:
    ca = _root()
    leaf = _leaf(ca, key=generate_key())
    digest = _digest()

    with pytest.raises(CertificateVerificationError, match="does not verify"):
        verify_pop_signature(
            leaf,
            signature=sign_pop_digest(generate_key(), digest),
            digest=digest,
            timestamp=NOW,
            now=NOW,
            window=WINDOW,
        )


def test_verify_pop_rejects_a_signature_over_a_different_call() -> None:
    """A signature captured from one call must not authorize another."""
    ca = _root()
    key = generate_key()
    leaf = _leaf(ca, key=key)
    signature = sign_pop_digest(key, _digest(tool_name="read_file"))

    with pytest.raises(CertificateVerificationError, match="does not verify"):
        verify_pop_signature(
            leaf,
            signature=signature,
            digest=_digest(tool_name="delete_everything"),
            timestamp=NOW,
            now=NOW,
            window=WINDOW,
        )


@pytest.mark.parametrize("skew", [timedelta(seconds=61), timedelta(seconds=-61)])
def test_verify_pop_rejects_a_timestamp_outside_the_window(skew: timedelta) -> None:
    """The window is two-sided: a future timestamp is as bad as a stale one."""
    ca = _root()
    key = generate_key()
    leaf = _leaf(ca, key=key)
    timestamp = NOW + skew
    digest = _digest(timestamp=timestamp)

    with pytest.raises(CertificateVerificationError, match="time window"):
        verify_pop_signature(
            leaf,
            signature=sign_pop_digest(key, digest),
            digest=digest,
            timestamp=timestamp,
            now=NOW,
            window=WINDOW,
        )
