"""HashiCorp Vault KV v2 client used to resolve ``vault``-type secrets.

A tenant reads its ``vault``-type secrets from one of two Vaults, picked by
:class:`TenantVaults`:

* **Its own**, configured by the tenant's ``admin`` on the tenant record
  (:class:`models.tenant.TenantVaultFields`): an address plus either a static
  token or AppRole credentials. Since a tenant user chose the address, it
  passed :func:`infrastructure.url_safety.assert_public_http_url` when saved,
  and the client refuses to connect to a non-public peer
  (:func:`~infrastructure.url_safety.guard_peer_address`).
* Otherwise **the global Vault**, whose address a ``super_admin`` sets in
  :class:`models.system_settings.SystemSettings`. There is no shared
  credential: each tenant logs in with its own
  (:class:`models.tenant.TenantGlobalVaultFields`, registered by a
  ``super_admin``), so what a tenant may read there is decided by the Vault
  policies attached to that credential -- not by A2Flow. A tenant with no such
  credential cannot read the global Vault at all. Its address is exempt from
  the SSRF checks: only a ``super_admin`` sets it, and a Vault typically lives
  on a private address.

Either way a secret names its own mount and path. Only the KV v2 engine is
supported.
"""

import asyncio
import logging
import time
from typing import Protocol

import httpx
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.secret_cipher import SecretCipher
from infrastructure.url_safety import guard_peer_address
from models.system_settings import SYSTEM_SETTINGS_ID, SystemSettings
from models.tenant import DEFAULT_VAULT_APPROLE_MOUNT, Tenant, VaultAuthMethod

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

    async def read_kv2(self, mount: str, path: str) -> dict[str, str]:
        """Read every key of a KV v2 secret.

        Performs ``GET {addr}/v1/{mount}/data/{path}``. On a 403 the cached
        token is invalidated and the read retried once, covering tokens revoked
        before their lease expired.

        The whole data object is returned rather than a single key because a
        Secret row references a Vault *path*, and each ``${secret:NAME/KEY}``
        placeholder picks its key out of the result — see
        :class:`infrastructure.secret_resolver.SecretResolver`.

        Args:
            mount: The KV v2 mount point (e.g. ``secret``).
            path: The secret path below the mount.

        Returns:
            The secret's data object, with every value coerced to ``str``.

        Raises:
            VaultError: If the request errors or the response status is not 200.
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
        return {str(key): str(value) for key, value in data.items()}

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


#: One client per Vault connection -- keyed by tenant id for a tenant's own
#: Vault, or ``global:<tenant id>`` for its login to the global Vault -- with the
#: configuration it was built from. Keeping the client (not just rebuilding it
#: per call) is what lets an AppRole token be reused across requests; storing
#: the configuration alongside means an edit of the Vault settings replaces the
#: client on its next use.
_clients: dict[str, tuple[tuple[object, ...], VaultClient]] = {}


class TenantVaults:
    """Hands out the Vault client a given tenant reads with, built from stored settings.

    A tenant's own Vault wins; a tenant without one logs in to the global Vault
    of :class:`models.system_settings.SystemSettings` with its own credential.
    """

    def __init__(self, session: AsyncSession, cipher: SecretCipher) -> None:
        """Store the session the settings rows are read through and the cipher.

        Args:
            session: The SQLModel async session to read the rows with.
            cipher: Cipher that decrypts the stored Vault credentials.
        """
        self._db = session
        self._cipher = cipher

    async def client_for(self, tenant_id: str) -> VaultClient | None:
        """Return the Vault client ``tenant_id`` reads with, or ``None`` if none.

        Args:
            tenant_id: The tenant whose secrets are being read.

        Returns:
            A client for the tenant's own Vault when it has an address,
            otherwise one for the global Vault logged in with the tenant's
            credential for it, or ``None`` when neither is usable (no address
            or credential, or a credential that no longer decrypts because the
            Fernet key changed).
        """
        tenant = await self._db.get(Tenant, tenant_id)
        if tenant is None:
            return None
        if tenant.vault_addr:
            return self._client(
                tenant_id,
                tenant.vault_addr,
                tenant.vault_auth_method,
                tenant.vault_role_id,
                tenant.vault_approle_mount,
                tenant.vault_credential,
                guard_peer=True,
            )
        settings = await self._db.get(SystemSettings, SYSTEM_SETTINGS_ID)
        if settings is None or not settings.vault_addr:
            return None
        return self._client(
            f"global:{tenant_id}",
            settings.vault_addr,
            tenant.global_vault_auth_method,
            tenant.global_vault_role_id,
            tenant.global_vault_approle_mount,
            tenant.global_vault_credential,
            guard_peer=False,
        )

    def _client(
        self,
        key: str,
        addr: str,
        method: VaultAuthMethod | None,
        role_id: str | None,
        approle_mount: str | None,
        credential: str | None,
        *,
        guard_peer: bool,
    ) -> VaultClient | None:
        """Return the cached client of a connection, rebuilding it on a change.

        Args:
            key: :data:`_clients` key of the connection.
            addr: The Vault address.
            method: How to log in.
            role_id: The AppRole role id, for :attr:`VaultAuthMethod.approle`.
            approle_mount: The AppRole login mount, or ``None`` for the default.
            credential: The stored (encrypted) token or AppRole secret id.
            guard_peer: Whether to refuse connecting to a non-public address.
                Set for a tenant's own Vault, whose address a tenant user
                chose; the global Vault's address is a ``super_admin``'s.

        Returns:
            The client, or ``None`` when the connection lacks a credential, or
            (for AppRole) a role id, or its credential no longer decrypts.
        """
        if not credential:
            return None
        config = (addr, method, role_id, approle_mount, credential)
        cached = _clients.get(key)
        if cached is not None and cached[0] == config:
            return cached[1]
        try:
            plaintext = self._cipher.decrypt(credential)
        except ValueError:
            logger.error(
                "Stored Vault credential (%s) could not be decrypted; its "
                "vault-type secrets fail until the credential is set again.",
                key,
            )
            return None
        auth: VaultAuth
        if method == VaultAuthMethod.approle:
            if not role_id:
                return None
            auth = AppRoleAuth(
                role_id, plaintext, approle_mount or DEFAULT_VAULT_APPROLE_MOUNT
            )
        else:
            auth = TokenAuth(plaintext)
        http = httpx.AsyncClient(
            follow_redirects=False,
            event_hooks={"request": [guard_peer_address]} if guard_peer else None,
        )
        client = VaultClient(addr, auth, http)
        _clients[key] = (config, client)
        return client
