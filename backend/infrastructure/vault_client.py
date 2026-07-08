"""HashiCorp Vault KV v2 client used to resolve ``vault``-type secrets.

A single global Vault connection is configured through environment variables
(see :func:`dependencies.singletons.get_vault_client`): ``VAULT_ADDR`` plus
either a static ``VAULT_TOKEN`` or AppRole credentials (``VAULT_ROLE_ID`` /
``VAULT_SECRET_ID``, login mount from ``VAULT_APPROLE_MOUNT``). Only the KV v2
engine is supported.

``VAULT_ADDR`` is deliberately exempt from
:func:`infrastructure.url_safety.assert_public_http_url`: it is operator-set
deployment configuration (not user input), and a Vault server typically lives
on a private address that the SSRF check would reject.
"""

import asyncio
import logging
import os
import time
from functools import lru_cache
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

#: Request timeout, in seconds, for every Vault HTTP call.
_TIMEOUT_SECONDS = 10.0

#: Seconds subtracted from a token lease before it is considered expired, so a
#: token is never used in the final moments of its lease.
_LEASE_SKEW_SECONDS = 30.0


class VaultError(Exception):
    """Raised when a Vault login or read fails.

    Attributes:
        reason: Human-readable description of the failure. Logged server-side
            only; never returned to API clients.
    """

    def __init__(self, reason: str) -> None:
        """Store the failure reason.

        Args:
            reason: Human-readable description of the failure.
        """
        super().__init__(reason)
        self.reason = reason


class VaultAuth(Protocol):
    """Strategy producing the token sent as ``X-Vault-Token``."""

    async def get_token(self, client: httpx.AsyncClient, addr: str) -> str:
        """Return a valid Vault token, performing a login if necessary."""
        ...

    def invalidate(self) -> None:
        """Discard any cached token so the next call logs in again."""
        ...


class TokenAuth:
    """Static-token authentication (``VAULT_TOKEN``)."""

    def __init__(self, token: str) -> None:
        """Store the static token.

        Args:
            token: The Vault token to send with every request.
        """
        self._token = token

    async def get_token(self, client: httpx.AsyncClient, addr: str) -> str:
        """Return the static token; no login round-trip is needed."""
        return self._token

    def invalidate(self) -> None:
        """No-op: a static token cannot be refreshed."""


class AppRoleAuth:
    """AppRole authentication: logs in with role/secret IDs and caches the token.

    The client token returned by the login endpoint is reused until its lease
    (minus a small skew) expires, then a fresh login is performed. A lease
    duration of ``0`` means the token never expires. Concurrent resolutions
    share one login via an :class:`asyncio.Lock`.
    """

    def __init__(self, role_id: str, secret_id: str, mount: str = "approle") -> None:
        """Store the AppRole credentials.

        Args:
            role_id: The AppRole RoleID.
            secret_id: The AppRole SecretID.
            mount: Mount path of the AppRole auth method (default ``approle``).
        """
        self._role_id = role_id
        self._secret_id = secret_id
        self._mount = mount
        self._token: str | None = None
        self._expires_at: float | None = None
        self._lock = asyncio.Lock()

    def _cached_token(self) -> str | None:
        """Return the cached token if it is still within its lease, else ``None``."""
        if self._token is None:
            return None
        if self._expires_at is not None and time.monotonic() >= self._expires_at:
            return None
        return self._token

    async def get_token(self, client: httpx.AsyncClient, addr: str) -> str:
        """Return a cached client token, logging in when absent or expired.

        Args:
            client: The HTTP client to perform the login with.
            addr: The Vault base address.

        Returns:
            A valid Vault client token.

        Raises:
            VaultError: If the login request fails.
        """
        cached = self._cached_token()
        if cached is not None:
            return cached
        async with self._lock:
            cached = self._cached_token()
            if cached is not None:
                return cached
            return await self._login(client, addr)

    async def _login(self, client: httpx.AsyncClient, addr: str) -> str:
        """Perform the AppRole login and cache the resulting client token.

        Args:
            client: The HTTP client to perform the login with.
            addr: The Vault base address.

        Returns:
            The fresh Vault client token.

        Raises:
            VaultError: If the request errors, returns a non-200 status, or
                the response lacks a client token.
        """
        url = f"{addr}/v1/auth/{self._mount}/login"
        try:
            response = await client.post(
                url,
                json={"role_id": self._role_id, "secret_id": self._secret_id},
                timeout=_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise VaultError(f"AppRole login request failed: {exc}") from exc
        if response.status_code != 200:
            raise VaultError(f"AppRole login failed with HTTP {response.status_code}")
        auth = response.json().get("auth") or {}
        token = auth.get("client_token")
        if not token:
            raise VaultError("AppRole login response contained no client token")
        lease = auth.get("lease_duration") or 0
        self._token = token
        self._expires_at = (
            time.monotonic() + max(lease - _LEASE_SKEW_SECONDS, 0.0)
            if lease > 0
            else None
        )
        return str(token)

    def invalidate(self) -> None:
        """Discard the cached token (e.g. after a 403) to force a re-login."""
        self._token = None
        self._expires_at = None


class VaultClient:
    """Reads secret values from HashiCorp Vault's KV v2 engine."""

    def __init__(
        self,
        addr: str,
        auth: VaultAuth,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Configure the Vault connection.

        Args:
            addr: Vault base address (e.g. ``https://vault.example.com``).
            auth: Token-producing auth strategy.
            client: Optional preconfigured HTTP client, injectable for tests.
                When omitted, a client with redirects disabled is created.
        """
        self._addr = addr.rstrip("/")
        self._auth = auth
        self._client = client or httpx.AsyncClient(follow_redirects=False)

    async def read_kv2(self, mount: str, path: str, key: str) -> str:
        """Read one key of a KV v2 secret.

        Performs ``GET {addr}/v1/{mount}/data/{path}``. On a 403 the cached
        token is invalidated and the read retried once, covering tokens revoked
        before their lease expired.

        Args:
            mount: The KV v2 mount point (e.g. ``secret``).
            path: The secret path below the mount.
            key: The key within the secret's data object.

        Returns:
            The secret value.

        Raises:
            VaultError: If the request errors, the response status is not 200,
                or the key is missing from the secret data.
        """
        response = await self._get(mount, path)
        if response.status_code == 403:
            self._auth.invalidate()
            response = await self._get(mount, path)
        if response.status_code != 200:
            raise VaultError(
                f"Vault read of {mount}/{path} failed with HTTP {response.status_code}"
            )
        data = (response.json().get("data") or {}).get("data") or {}
        if key not in data:
            raise VaultError(f"Key {key!r} not found in Vault secret {mount}/{path}")
        return str(data[key])

    async def _get(self, mount: str, path: str) -> httpx.Response:
        """Issue the KV v2 read request with a fresh or cached token.

        Args:
            mount: The KV v2 mount point.
            path: The secret path below the mount.

        Returns:
            The raw HTTP response.

        Raises:
            VaultError: If the login or the request itself fails at the
                transport level.
        """
        token = await self._auth.get_token(self._client, self._addr)
        url = f"{self._addr}/v1/{mount}/data/{path}"
        try:
            return await self._client.get(
                url, headers={"X-Vault-Token": token}, timeout=_TIMEOUT_SECONDS
            )
        except httpx.HTTPError as exc:
            raise VaultError(f"Vault request failed: {exc}") from exc


@lru_cache(maxsize=1)
def get_vault_client() -> VaultClient | None:
    """Return the process-wide Vault client, or ``None`` when Vault is not configured.

    ``VAULT_ADDR`` selects the server; AppRole credentials (``VAULT_ROLE_ID`` +
    ``VAULT_SECRET_ID``, login mount from ``VAULT_APPROLE_MOUNT``) take
    precedence over a static ``VAULT_TOKEN`` when both are set. A ``VAULT_ADDR``
    with no usable credentials logs a warning and disables Vault resolution.

    Lives here (not in :mod:`dependencies.singletons`, which re-exports it) so
    the agent proxy tools in :mod:`infrastructure.mcp_tools` can use it without
    importing the dependencies package, which would create an import cycle
    through :mod:`infrastructure.agent`.
    """
    addr = os.getenv("VAULT_ADDR")
    if not addr:
        return None
    role_id = os.getenv("VAULT_ROLE_ID")
    secret_id = os.getenv("VAULT_SECRET_ID")
    if role_id and secret_id:
        mount = os.getenv("VAULT_APPROLE_MOUNT", "approle")
        return VaultClient(addr, AppRoleAuth(role_id, secret_id, mount))
    token = os.getenv("VAULT_TOKEN")
    if token:
        return VaultClient(addr, TokenAuth(token))
    logger.warning(
        "VAULT_ADDR is set but neither VAULT_TOKEN nor VAULT_ROLE_ID/VAULT_SECRET_ID "
        "is configured; vault-type secrets will fail to resolve"
    )
    return None
