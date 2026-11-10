"""OpenID Connect relying-party client: discovery, code flow, ID-token checks.

:class:`OidcClient` is the only code that decides whether an ID token from a
tenant's identity provider is trusted, so it is deliberately small and strict:

* every URL it contacts (the discovery document and each endpoint inside it)
  passes :func:`infrastructure.url_safety.assert_public_http_url`, except hosts
  an operator allow-listed (``OIDC_ALLOWED_PRIVATE_HOSTS``); the singleton's
  HTTP client also checks the connected peer address through
  :func:`infrastructure.url_safety.guard_peer_address` (same exemption), and
  never follows redirects;
* a token's signature algorithm comes from a fixed allow-list, never from the
  token's own header, so ``none`` and the HMAC family are refused;
* the issuer, audience, expiry and nonce are all verified, and ``exp``,
  ``iat`` and ``sub`` are mandatory.

Every failure surfaces as :class:`OidcError`, whose message is for the server
log only.
"""

import asyncio
import base64
import hashlib
import json
import secrets
import time
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

import httpx
import jwt
from jwt.api_jwk import PyJWK

from config import get_settings
from infrastructure.url_safety import assert_public_http_url, guard_peer_address

#: How long discovery documents and JWKS are cached, in seconds.
CACHE_TTL_SECONDS = 300
#: Minimum gap, in seconds, between two JWKS refetches forced by unknown key ids,
#: so a stream of forged ``kid`` values cannot turn into a stream of IdP requests.
JWKS_REFETCH_COOLDOWN_SECONDS = 30
#: Signature algorithms an ID token may use. Fixed on purpose: ``none`` and the
#: HMAC family must never be accepted, whatever the token's header claims.
ID_TOKEN_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "PS256"]
_SCOPE = "openid email profile"
_LEEWAY_SECONDS = 60


class OidcError(Exception):
    """An OIDC exchange failed or a token was not trustworthy.

    The message is meant for the server log; never show it to the end user.
    """


@dataclass(frozen=True)
class OidcProviderMetadata:
    """The parts of an IdP's discovery document this app uses.

    Attributes:
        issuer: The issuer identifier, equal to the configured issuer URL.
        authorization_endpoint: Where the browser is sent to sign in.
        token_endpoint: Where the authorization code is exchanged.
        jwks_uri: Where the ID-token signing keys are published.
        userinfo_endpoint: The userinfo endpoint, if the IdP offers one.
    """

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    userinfo_endpoint: str | None


def make_pkce_pair() -> tuple[str, str]:
    """Return a PKCE ``(code_verifier, S256 code_challenge)`` pair (RFC 7636)."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def peer_guard_hook(
    allowed_hosts: Collection[str],
) -> Callable[[httpx.Request], Awaitable[None]]:
    """Build the ``httpx`` request hook that guards the connected peer address.

    Args:
        allowed_hosts: Lower-case hostnames exempt from the peer check.

    Returns:
        A hook that awaits :func:`guard_peer_address` for every request whose
        host is not in ``allowed_hosts``.
    """

    async def hook(request: httpx.Request) -> None:
        if request.url.host.lower() not in allowed_hosts:
            await guard_peer_address(request)

    return hook


class OidcClient:
    """Talks to a tenant's OpenID Connect provider over ``httpx``.

    Discovery documents and JWKS are cached in memory per instance, with a
    monotonic-clock expiry.
    """

    def __init__(
        self, http: httpx.AsyncClient, *, allowed_hosts: Collection[str]
    ) -> None:
        """Create the client.

        Args:
            http: The HTTP client used for every IdP call. It must not follow
                redirects, and should carry :func:`peer_guard_hook`.
            allowed_hosts: Lower-case hostnames exempt from the SSRF checks.
        """
        self._http = http
        self._allowed_hosts = {h.lower() for h in allowed_hosts}
        self._metadata: dict[str, tuple[float, OidcProviderMetadata]] = {}
        self._jwks: dict[str, tuple[float, dict[str, PyJWK]]] = {}
        self._last_forced_refetch: dict[str, float] = {}

    async def _check_url(self, url: str) -> None:
        """Raise :class:`OidcError` unless ``url`` may be contacted."""
        try:
            await asyncio.to_thread(
                assert_public_http_url, url, allowed_hosts=self._allowed_hosts
            )
        except ValueError as exc:
            raise OidcError(f"refusing to contact {url!r}: {exc}") from exc

    async def _request_json(
        self, method: str, url: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Send a request to ``url`` and return its JSON object body.

        Raises:
            OidcError: If the URL is refused, the transport fails, the status
                is not 2xx, or the body is not a JSON object.
        """
        await self._check_url(url)
        try:
            response = await self._http.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise OidcError(f"{method} {url} failed: {exc!r}") from exc
        if not response.is_success:
            raise OidcError(f"{method} {url} returned HTTP {response.status_code}")
        try:
            body = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise OidcError(f"{method} {url} did not return JSON") from exc
        if not isinstance(body, dict):
            raise OidcError(f"{method} {url} did not return a JSON object")
        return body

    async def metadata(self, issuer: str) -> OidcProviderMetadata:
        """Return the provider metadata for ``issuer``, cached for five minutes.

        Args:
            issuer: The configured issuer URL.

        Raises:
            OidcError: If discovery fails, the document's ``issuer`` differs
                from ``issuer`` (exact string match), a required endpoint is
                missing, or any endpoint fails the SSRF check.
        """
        cached = self._metadata.get(issuer)
        if cached is not None and cached[0] > time.monotonic():
            return cached[1]
        doc = await self._request_json(
            "GET", f"{issuer.rstrip('/')}/.well-known/openid-configuration"
        )
        if doc.get("issuer") != issuer:
            raise OidcError(
                f"discovery issuer {doc.get('issuer')!r} does not match {issuer!r}"
            )
        endpoints: dict[str, str | None] = {}
        for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            value = doc.get(key)
            if not isinstance(value, str) or not value:
                raise OidcError(f"discovery document has no {key}")
            endpoints[key] = value
        userinfo = doc.get("userinfo_endpoint")
        if userinfo is not None and not isinstance(userinfo, str):
            raise OidcError("discovery userinfo_endpoint is not a string")
        endpoints["userinfo_endpoint"] = userinfo or None
        for url in endpoints.values():
            if url is not None:
                await self._check_url(url)
        meta = OidcProviderMetadata(
            issuer=issuer,
            authorization_endpoint=endpoints["authorization_endpoint"] or "",
            token_endpoint=endpoints["token_endpoint"] or "",
            jwks_uri=endpoints["jwks_uri"] or "",
            userinfo_endpoint=endpoints["userinfo_endpoint"],
        )
        self._metadata[issuer] = (time.monotonic() + CACHE_TTL_SECONDS, meta)
        return meta

    def authorization_url(
        self,
        meta: OidcProviderMetadata,
        *,
        client_id: str,
        redirect_uri: str,
        state: str,
        nonce: str,
        code_challenge: str,
    ) -> str:
        """Return the URL to send the browser to, to start the code flow.

        Args:
            meta: The provider's metadata.
            client_id: This app's client id at the IdP.
            redirect_uri: The callback URL registered at the IdP.
            state: Opaque anti-CSRF value echoed back on the callback.
            nonce: Value the ID token must carry back.
            code_challenge: The PKCE S256 challenge (see :func:`make_pkce_pair`).
        """
        query = urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": _SCOPE,
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            },
            quote_via=quote,
        )
        sep = "&" if urlsplit(meta.authorization_endpoint).query else "?"
        return f"{meta.authorization_endpoint}{sep}{query}"

    async def exchange_code(
        self,
        meta: OidcProviderMetadata,
        *,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict[str, Any]:
        """Exchange an authorization code for tokens (``client_secret_post``).

        Args:
            meta: The provider's metadata.
            client_id: This app's client id at the IdP.
            client_secret: This app's client secret at the IdP.
            code: The authorization code from the callback.
            redirect_uri: The same redirect URI the flow started with.
            code_verifier: The PKCE verifier matching the challenge sent.

        Returns:
            The token response; it always contains an ``id_token``.

        Raises:
            OidcError: On a transport error, a non-2xx status, a non-object
                body, or a response without an ``id_token``.
        """
        tokens = await self._request_json(
            "POST",
            meta.token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
                "code_verifier": code_verifier,
            },
            headers={"Accept": "application/json"},
        )
        if not isinstance(tokens.get("id_token"), str) or not tokens["id_token"]:
            raise OidcError("token response has no id_token")
        return tokens

    async def _signing_keys(
        self, meta: OidcProviderMetadata, *, force: bool = False
    ) -> dict[str, PyJWK]:
        """Return the IdP's signing keys by ``kid``, from cache unless ``force``."""
        cached = self._jwks.get(meta.jwks_uri)
        if not force and cached is not None and cached[0] > time.monotonic():
            return cached[1]
        document = await self._request_json("GET", meta.jwks_uri)
        try:
            key_set = jwt.PyJWKSet.from_dict(document)
        except (jwt.PyJWTError, TypeError, ValueError) as exc:
            raise OidcError(f"unusable JWKS: {exc!r}") from exc
        keys = {
            k.key_id: k
            for k in key_set.keys
            if k.key_id and k.public_key_use in (None, "sig")
        }
        self._jwks[meta.jwks_uri] = (time.monotonic() + CACHE_TTL_SECONDS, keys)
        return keys

    async def _key_for(self, meta: OidcProviderMetadata, kid: str) -> PyJWK:
        """Return the signing key ``kid``, refetching the JWKS once if unknown.

        The forced refetch is rate-limited per ``jwks_uri``
        (:data:`JWKS_REFETCH_COOLDOWN_SECONDS`).
        """
        key = (await self._signing_keys(meta)).get(kid)
        if key is not None:
            return key
        now = time.monotonic()
        last = self._last_forced_refetch.get(meta.jwks_uri)
        if last is not None and now - last < JWKS_REFETCH_COOLDOWN_SECONDS:
            raise OidcError(f"unknown signing key {kid!r}")
        self._last_forced_refetch[meta.jwks_uri] = now
        key = (await self._signing_keys(meta, force=True)).get(kid)
        if key is None:
            raise OidcError(f"unknown signing key {kid!r}")
        return key

    async def validate_id_token(
        self,
        meta: OidcProviderMetadata,
        id_token: str,
        *,
        client_id: str,
        nonce: str,
    ) -> dict[str, Any]:
        """Verify an ID token and return its claims.

        Checks the signature against the IdP's JWKS (algorithms from
        :data:`ID_TOKEN_ALGORITHMS` only), ``iss`` against ``meta.issuer``,
        ``aud`` against ``client_id``, ``exp`` (60 s leeway), the presence of
        ``exp``/``iat``/``sub``, and ``nonce``.

        Args:
            meta: The provider's metadata.
            id_token: The compact-serialized JWT from the token endpoint.
            client_id: This app's client id, which ``aud`` must contain.
            nonce: The nonce sent in the authorization request.

        Raises:
            OidcError: If any check fails.
        """
        try:
            kid = jwt.get_unverified_header(id_token).get("kid")
            if not isinstance(kid, str) or not kid:
                raise OidcError("ID token header has no kid")
            key = await self._key_for(meta, kid)
            claims: dict[str, Any] = jwt.decode(
                id_token,
                key.key,
                algorithms=ID_TOKEN_ALGORITHMS,
                audience=client_id,
                issuer=meta.issuer,
                leeway=_LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "sub"]},
            )
        except (jwt.PyJWTError, TypeError, ValueError) as exc:
            # TypeError/ValueError: PyJWT lets a key/alg mismatch (e.g. an EC key
            # for an RS256 header) escape as these instead of InvalidKeyError.
            raise OidcError(f"invalid ID token: {exc!r}") from exc
        token_nonce = claims.get("nonce")
        if not isinstance(token_nonce, str) or not secrets.compare_digest(
            token_nonce.encode(), nonce.encode()
        ):
            raise OidcError("ID token nonce mismatch")
        return claims

    async def userinfo(
        self, meta: OidcProviderMetadata, access_token: str
    ) -> dict[str, Any]:
        """Fetch the userinfo claims, or ``{}`` if the IdP has no such endpoint.

        The caller must check that the returned ``sub`` equals the ID token's
        before trusting any claim in it.

        Args:
            meta: The provider's metadata.
            access_token: The access token from the token response.

        Raises:
            OidcError: On a transport error, non-2xx status or non-object body.
        """
        if meta.userinfo_endpoint is None:
            return {}
        return await self._request_json(
            "GET",
            meta.userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
        )


@lru_cache(maxsize=1)
def get_oidc_client() -> OidcClient:
    """Return the process-wide :class:`OidcClient` singleton.

    Its HTTP client has a 10 s timeout, follows no redirects, and checks the
    connected peer address of every request unless the host is listed in
    ``OIDC_ALLOWED_PRIVATE_HOSTS``.
    """
    allowed = get_settings().oidc_allowed_private_hosts
    http = httpx.AsyncClient(
        timeout=10, event_hooks={"request": [peer_guard_hook(allowed)]}
    )
    return OidcClient(http, allowed_hosts=allowed)
