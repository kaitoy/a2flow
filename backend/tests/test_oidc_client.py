"""Tests for the OIDC relying-party client against a fake IdP."""

import base64
import hashlib
import time
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from infrastructure import oidc_client
from infrastructure.oidc_client import (
    OidcClient,
    OidcError,
    OidcProviderMetadata,
    make_pkce_pair,
)
from tests._oidc_fake import CLIENT_ID, FakeIdp

NONCE = "nonce-1"
DISCOVERY = "/.well-known/openid-configuration"


@pytest.fixture()
def fake() -> FakeIdp:
    """Return a fresh fake IdP."""
    return FakeIdp()


@pytest.fixture()
def client(fake: FakeIdp) -> OidcClient:
    """Return an OIDC client wired to ``fake`` with no private-host allowlist."""
    return OidcClient(httpx.AsyncClient(transport=fake.transport), allowed_hosts=())


def _client_for(handler: Any) -> OidcClient:
    """Return a client whose HTTP answers come from ``handler``."""
    return OidcClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)), allowed_hosts=()
    )


def _doc(iss: str, **overrides: Any) -> dict[str, Any]:
    """Return a discovery document for ``iss`` with overrides."""
    return {
        "issuer": iss,
        "authorization_endpoint": f"{iss}/authorize",
        "token_endpoint": f"{iss}/token",
        "jwks_uri": f"{iss}/jwks",
        **overrides,
    }


async def _validate(client: OidcClient, fake: FakeIdp, token: str) -> dict[str, Any]:
    """Validate ``token`` against ``fake``'s metadata."""
    meta = await client.metadata(fake.issuer)
    claims: dict[str, Any] = await client.validate_id_token(
        meta, token, client_id=CLIENT_ID, nonce=NONCE
    )
    return claims


def _freeze_clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace the client's clock with a settable one; return its single cell."""
    now = [1000.0]
    monkeypatch.setattr(oidc_client, "time", SimpleNamespace(monotonic=lambda: now[0]))
    return now


async def test_metadata_rejects_issuer_mismatch(fake: FakeIdp) -> None:
    c = _client_for(lambda r: httpx.Response(200, json=_doc("https://evil.test")))
    with pytest.raises(OidcError):
        await c.metadata(fake.issuer)


async def test_metadata_is_cached(client: OidcClient, fake: FakeIdp) -> None:
    first = await client.metadata(fake.issuer)
    second = await client.metadata(fake.issuer)
    assert first.issuer == fake.issuer
    assert first.userinfo_endpoint == fake.issuer + "/userinfo"
    assert second == first
    assert fake.count(DISCOVERY) == 1


async def test_metadata_cache_expires(
    client: OidcClient, fake: FakeIdp, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = _freeze_clock(monkeypatch)
    await client.metadata(fake.issuer)
    now[0] += 299
    await client.metadata(fake.issuer)
    assert fake.count(DISCOVERY) == 1
    now[0] += 2
    await client.metadata(fake.issuer)
    assert fake.count(DISCOVERY) == 2


async def test_metadata_rejects_private_endpoint(fake: FakeIdp) -> None:
    doc = _doc(fake.issuer, token_endpoint="http://169.254.169.254/token")
    c = _client_for(lambda r: httpx.Response(200, json=doc))
    with pytest.raises(OidcError):
        await c.metadata(fake.issuer)


async def test_metadata_requires_endpoints(fake: FakeIdp) -> None:
    doc = _doc(fake.issuer)
    del doc["jwks_uri"]
    c = _client_for(lambda r: httpx.Response(200, json=doc))
    with pytest.raises(OidcError):
        await c.metadata(fake.issuer)


async def test_private_issuer_needs_the_allowlist() -> None:
    fake = FakeIdp("http://127.0.0.1:8080")
    strict = OidcClient(httpx.AsyncClient(transport=fake.transport), allowed_hosts=())
    with pytest.raises(OidcError):
        await strict.metadata(fake.issuer)
    assert fake.requests == []
    allowed = OidcClient(
        httpx.AsyncClient(transport=fake.transport), allowed_hosts=("127.0.0.1",)
    )
    assert (await allowed.metadata(fake.issuer)).issuer == fake.issuer


@pytest.mark.parametrize("body", ["not json", "[1]"])
async def test_metadata_rejects_non_object_json(fake: FakeIdp, body: str) -> None:
    c = _client_for(lambda r: httpx.Response(200, text=body))
    with pytest.raises(OidcError):
        await c.metadata(fake.issuer)


async def test_transport_error_is_oidc_error(fake: FakeIdp) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(OidcError):
        await _client_for(boom).metadata(fake.issuer)


def test_make_pkce_pair() -> None:
    verifier, challenge = make_pkce_pair()
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    assert challenge == base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    assert len(verifier) >= 43
    assert make_pkce_pair()[0] != verifier


async def test_authorization_url_carries_pkce_and_scope(
    client: OidcClient, fake: FakeIdp
) -> None:
    meta = await client.metadata(fake.issuer)
    url = client.authorization_url(
        meta,
        client_id=CLIENT_ID,
        redirect_uri="https://app.example.com/api/v1/auth/oidc/callback",
        state="st",
        nonce="no",
        code_challenge="ch",
    )
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == meta.authorization_endpoint
    q = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert q == {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": "https://app.example.com/api/v1/auth/oidc/callback",
        "scope": "openid email profile",
        "state": "st",
        "nonce": "no",
        "code_challenge": "ch",
        "code_challenge_method": "S256",
    }


async def test_authorization_url_keeps_existing_query(client: OidcClient) -> None:
    meta = OidcProviderMetadata(
        issuer="https://i",
        authorization_endpoint="https://i/auth?tenant=x",
        token_endpoint="https://i/t",
        jwks_uri="https://i/j",
        userinfo_endpoint=None,
    )
    url = client.authorization_url(
        meta, client_id="c", redirect_uri="r", state="s", nonce="n", code_challenge="h"
    )
    assert "?tenant=x&" in url


async def test_validate_id_token_happy_path(client: OidcClient, fake: FakeIdp) -> None:
    claims = await _validate(client, fake, fake.sign(fake.claims()))
    assert claims["sub"] == "user-1"
    assert claims["email"] == "user@example.com"


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "someone-else"},
        {"iss": "https://evil.example.com"},
        {"nonce": "wrong"},
        {"exp": int(time.time()) - 120},
    ],
    ids=["aud", "iss", "nonce", "expired"],
)
async def test_validate_id_token_rejects(
    client: OidcClient, fake: FakeIdp, overrides: dict[str, Any]
) -> None:
    with pytest.raises(OidcError):
        await _validate(client, fake, fake.sign(fake.claims(**overrides)))


@pytest.mark.parametrize("missing", ["exp", "iat", "sub", "nonce"])
async def test_validate_id_token_requires_claims(
    client: OidcClient, fake: FakeIdp, missing: str
) -> None:
    claims = fake.claims()
    del claims[missing]
    with pytest.raises(OidcError):
        await _validate(client, fake, fake.sign(claims))


async def test_validate_id_token_bad_signature(
    client: OidcClient, fake: FakeIdp
) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(OidcError):
        await _validate(client, fake, fake.sign(fake.claims(), key=other))


async def test_validate_id_token_rejects_unsigned_and_symmetric(
    client: OidcClient, fake: FakeIdp
) -> None:
    headers = {"kid": fake.kid}
    tokens = [
        jwt.encode(fake.claims(), "", algorithm="none", headers=headers),
        jwt.encode(fake.claims(), "x" * 64, algorithm="HS256", headers=headers),
        "garbage",
    ]
    for token in tokens:
        with pytest.raises(OidcError):
            await _validate(client, fake, token)


async def test_unknown_kid_refetches_jwks_once(
    client: OidcClient, fake: FakeIdp
) -> None:
    await _validate(client, fake, fake.sign(fake.claims()))
    assert fake.count("/jwks") == 1
    fake.rotate_key()
    await _validate(client, fake, fake.sign(fake.claims()))
    assert fake.count("/jwks") == 2
    # A second unknown kid: refused, and no further fetch while rate-limited.
    fake.rotate_key()
    stale = fake.sign(fake.claims())
    fake.rotate_key()  # the IdP no longer publishes the key that signed `stale`
    with pytest.raises(OidcError):
        await _validate(client, fake, stale)
    assert fake.count("/jwks") == 2


async def test_unknown_kid_refetch_is_rate_limited(
    client: OidcClient, fake: FakeIdp, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = _freeze_clock(monkeypatch)
    await _validate(client, fake, fake.sign(fake.claims()))
    fake.rotate_key()
    stale = fake.sign(fake.claims())
    fake.rotate_key()  # the IdP no longer publishes the key that signed `stale`
    for expected in (2, 2):
        with pytest.raises(OidcError):
            await _validate(client, fake, stale)
        assert fake.count("/jwks") == expected
    now[0] += 31
    with pytest.raises(OidcError):
        await _validate(client, fake, stale)
    assert fake.count("/jwks") == 3


async def test_jwks_is_cached(client: OidcClient, fake: FakeIdp) -> None:
    for _ in range(2):
        await _validate(client, fake, fake.sign(fake.claims()))
    assert fake.count("/jwks") == 1


async def test_exchange_code_returns_token_response(
    client: OidcClient, fake: FakeIdp
) -> None:
    meta = await client.metadata(fake.issuer)
    tokens = await client.exchange_code(
        meta,
        client_id=CLIENT_ID,
        client_secret="s3cret",
        code="abc",
        redirect_uri="https://app/cb",
        code_verifier="ver",
    )
    assert tokens["access_token"] == "access-1"
    assert "id_token" in tokens
    assert fake.token_forms == [
        {
            "grant_type": "authorization_code",
            "code": "abc",
            "redirect_uri": "https://app/cb",
            "client_id": CLIENT_ID,
            "client_secret": "s3cret",
            "code_verifier": "ver",
        }
    ]


async def test_exchange_code_error_status_is_oidc_error(
    client: OidcClient, fake: FakeIdp
) -> None:
    meta = await client.metadata(fake.issuer)
    fake.token_status = 400
    with pytest.raises(OidcError):
        await client.exchange_code(
            meta,
            client_id=CLIENT_ID,
            client_secret="s",
            code="c",
            redirect_uri="r",
            code_verifier="v",
        )


async def test_exchange_code_without_id_token_is_oidc_error(
    client: OidcClient, fake: FakeIdp
) -> None:
    meta = await client.metadata(fake.issuer)
    fake.token_includes_id_token = False
    with pytest.raises(OidcError):
        await client.exchange_code(
            meta,
            client_id=CLIENT_ID,
            client_secret="s",
            code="c",
            redirect_uri="r",
            code_verifier="v",
        )


async def test_userinfo(client: OidcClient, fake: FakeIdp) -> None:
    meta = await client.metadata(fake.issuer)
    assert await client.userinfo(meta, "tok") == {"sub": "user-1"}
    assert fake.userinfo_authorizations == ["Bearer tok"]


async def test_userinfo_without_endpoint_is_empty(
    client: OidcClient, fake: FakeIdp
) -> None:
    fake.userinfo_endpoint = False
    meta = await client.metadata(fake.issuer)
    assert meta.userinfo_endpoint is None
    assert await client.userinfo(meta, "tok") == {}
    assert fake.count("/userinfo") == 0


async def test_peer_guard_hook_skips_allowed_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_guard(request: httpx.Request) -> None:
        calls.append(request.url.host)

    monkeypatch.setattr(oidc_client, "guard_peer_address", fake_guard)
    hook = oidc_client.peer_guard_hook(("keycloak.internal",))
    await hook(httpx.Request("GET", "https://Keycloak.internal/x"))
    await hook(httpx.Request("GET", "https://idp.example.com/x"))
    assert calls == ["idp.example.com"]
