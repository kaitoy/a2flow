"""A fake OpenID Connect identity provider for tests.

:class:`FakeIdp` serves discovery, JWKS, token and userinfo documents through an
:class:`httpx.MockTransport`, so an ``httpx.AsyncClient(transport=fake.transport)``
talks to it without a socket. Reused by the OIDC client, sign-in service and
router tests.
"""

import time
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

ISSUER = "https://idp.example.com"
CLIENT_ID = "client-id"


def new_rsa_key() -> rsa.RSAPrivateKey:
    """Return a fresh RSA private key."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeIdp:
    """An in-memory IdP with one RSA signing key at a time.

    Attributes:
        issuer: The issuer URL the discovery document reports.
        kid: Key id of the current signing key (``key-1``, ``key-2`` ...).
        next_claims: Claims the token endpoint puts in the ID token it issues.
            Defaults to :meth:`claims` with no overrides.
        userinfo_claims: JSON object the userinfo endpoint returns.
        userinfo_endpoint: Whether discovery advertises a userinfo endpoint.
        token_status: HTTP status the token endpoint answers with.
        token_includes_id_token: Whether a successful token response carries an
            ``id_token``.
        requests: ``"METHOD /path"`` of every request served, in order.
        token_forms: The decoded form body of every token request.
        userinfo_authorizations: The ``Authorization`` header of every
            userinfo request.
        transport: The mock transport serving all of the above.
    """

    def __init__(self, issuer: str = ISSUER) -> None:
        """Create the IdP with a fresh signing key.

        Args:
            issuer: The issuer URL to serve and sign under.
        """
        self.issuer = issuer
        self._key = new_rsa_key()
        self._serial = 1
        self.kid = "key-1"
        self.next_claims: dict[str, Any] = self.claims()
        self.userinfo_claims: dict[str, Any] = {"sub": "user-1"}
        self.userinfo_endpoint = True
        self.token_status = 200
        self.token_includes_id_token = True
        self.requests: list[str] = []
        self.token_forms: list[dict[str, str]] = []
        self.userinfo_authorizations: list[str | None] = []
        self.transport = httpx.MockTransport(self._handle)

    def claims(self, **overrides: Any) -> dict[str, Any]:
        """Return valid ID-token claims for :data:`CLIENT_ID`, with overrides.

        Args:
            **overrides: Claims to add or replace.
        """
        now = int(time.time())
        base: dict[str, Any] = {
            "iss": self.issuer,
            "aud": CLIENT_ID,
            "sub": "user-1",
            "iat": now,
            "exp": now + 300,
            "nonce": "nonce-1",
            "email": "user@example.com",
        }
        return {**base, **overrides}

    def rotate_key(self) -> None:
        """Replace the signing key (new ``kid``); the old key leaves the JWKS."""
        self._key = new_rsa_key()
        self._serial += 1
        self.kid = f"key-{self._serial}"

    def count(self, path: str) -> int:
        """Return how many requests hit ``path`` so far."""
        return sum(1 for r in self.requests if r.split(" ", 1)[1] == path)

    def sign(
        self, claims: dict[str, Any], *, key: rsa.RSAPrivateKey | None = None
    ) -> str:
        """Sign ``claims`` as an RS256 JWT with the current key and ``kid``.

        Args:
            claims: The JWT payload.
            key: Sign with this key instead of the IdP's (the ``kid`` header
                stays the current one), to forge a bad signature.
        """
        return jwt.encode(
            claims,
            key or self._key,
            algorithm="RS256",
            headers={"kid": self.kid},
        )

    def _jwks(self) -> dict[str, Any]:
        """Return the JWKS document for the current key."""
        jwk = RSAAlgorithm.to_jwk(self._key.public_key(), as_dict=True)
        return {"keys": [{**jwk, "kid": self.kid, "use": "sig", "alg": "RS256"}]}

    def _handle(self, request: httpx.Request) -> httpx.Response:
        """Serve one request."""
        path = urlsplit(str(request.url)).path
        self.requests.append(f"{request.method} {path}")
        base = self.issuer.rstrip("/")
        if path == "/.well-known/openid-configuration":
            doc: dict[str, Any] = {
                "issuer": self.issuer,
                "authorization_endpoint": f"{base}/authorize",
                "token_endpoint": f"{base}/token",
                "jwks_uri": f"{base}/jwks",
            }
            if self.userinfo_endpoint:
                doc["userinfo_endpoint"] = f"{base}/userinfo"
            return httpx.Response(200, json=doc)
        if path == "/jwks":
            return httpx.Response(200, json=self._jwks())
        if path == "/token":
            self.token_forms.append(dict(parse_qsl(request.content.decode())))
            if self.token_status != 200:
                return httpx.Response(
                    self.token_status, json={"error": "invalid_grant"}
                )
            body: dict[str, Any] = {"access_token": "access-1", "token_type": "Bearer"}
            if self.token_includes_id_token:
                body["id_token"] = self.sign(self.next_claims)
            return httpx.Response(200, json=body)
        if path == "/userinfo":
            self.userinfo_authorizations.append(request.headers.get("authorization"))
            return httpx.Response(200, json=self.userinfo_claims)
        return httpx.Response(404)
