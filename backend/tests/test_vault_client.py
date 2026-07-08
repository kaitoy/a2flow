"""Unit tests for the Vault KV v2 client and its auth strategies.

All HTTP traffic is faked with ``httpx.MockTransport``; no Vault server is
needed.
"""

from typing import Any

import httpx
import pytest

from infrastructure.vault_client import (
    AppRoleAuth,
    TokenAuth,
    VaultClient,
    VaultError,
)

_ADDR = "https://vault.example.com"


def _mock_client(
    handler: Any,
) -> httpx.AsyncClient:
    """Build an AsyncClient routed through a MockTransport handler."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ---------- token auth ----------


async def test_token_auth_reads_value() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Vault-Token"] == "tok"
        assert request.url.path == "/v1/secret/data/myapp/github"
        return httpx.Response(200, json={"data": {"data": {"token": "s3cr3t"}}})

    client = VaultClient(_ADDR, TokenAuth("tok"), client=_mock_client(handler))
    assert await client.read_kv2("secret", "myapp/github", "token") == "s3cr3t"


async def test_non_200_raises_vault_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"errors": []})

    client = VaultClient(_ADDR, TokenAuth("tok"), client=_mock_client(handler))
    with pytest.raises(VaultError, match="404"):
        await client.read_kv2("secret", "missing", "token")


async def test_missing_key_raises_vault_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"data": {"other": "v"}}})

    client = VaultClient(_ADDR, TokenAuth("tok"), client=_mock_client(handler))
    with pytest.raises(VaultError, match="not found"):
        await client.read_kv2("secret", "myapp/github", "token")


async def test_network_error_raises_vault_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = VaultClient(_ADDR, TokenAuth("tok"), client=_mock_client(handler))
    with pytest.raises(VaultError, match="request failed"):
        await client.read_kv2("secret", "myapp/github", "token")


# ---------- AppRole auth ----------


class _AppRoleHandler:
    """Stateful fake Vault: AppRole login endpoint plus one KV v2 secret."""

    def __init__(self, lease_duration: int = 3600) -> None:
        self.logins = 0
        self.reads = 0
        self.lease_duration = lease_duration
        self.reject_tokens: set[str] = set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/auth/approle/login":
            self.logins += 1
            return httpx.Response(
                200,
                json={
                    "auth": {
                        "client_token": f"tok-{self.logins}",
                        "lease_duration": self.lease_duration,
                    }
                },
            )
        self.reads += 1
        token = request.headers.get("X-Vault-Token", "")
        if not token.startswith("tok-") or token in self.reject_tokens:
            return httpx.Response(403, json={"errors": ["permission denied"]})
        return httpx.Response(200, json={"data": {"data": {"token": "s3cr3t"}}})


async def test_approle_logs_in_then_reads() -> None:
    handler = _AppRoleHandler()
    client = VaultClient(_ADDR, AppRoleAuth("rid", "sid"), client=_mock_client(handler))
    assert await client.read_kv2("secret", "p", "token") == "s3cr3t"
    assert handler.logins == 1


async def test_approle_caches_token_across_reads() -> None:
    handler = _AppRoleHandler()
    client = VaultClient(_ADDR, AppRoleAuth("rid", "sid"), client=_mock_client(handler))
    await client.read_kv2("secret", "p", "token")
    await client.read_kv2("secret", "p", "token")
    assert handler.logins == 1


async def test_approle_relogs_in_after_lease_expiry() -> None:
    # A 1-second lease minus the 30-second skew expires immediately, so every
    # read must trigger a fresh login.
    handler = _AppRoleHandler(lease_duration=1)
    client = VaultClient(_ADDR, AppRoleAuth("rid", "sid"), client=_mock_client(handler))
    await client.read_kv2("secret", "p", "token")
    await client.read_kv2("secret", "p", "token")
    assert handler.logins == 2


async def test_approle_retries_once_after_403() -> None:
    handler = _AppRoleHandler()
    handler.reject_tokens.add("tok-1")
    client = VaultClient(_ADDR, AppRoleAuth("rid", "sid"), client=_mock_client(handler))
    assert await client.read_kv2("secret", "p", "token") == "s3cr3t"
    assert handler.logins == 2
    assert handler.reads == 2


async def test_approle_login_failure_raises_vault_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"errors": ["invalid role"]})

    client = VaultClient(_ADDR, AppRoleAuth("rid", "sid"), client=_mock_client(handler))
    with pytest.raises(VaultError, match="login failed"):
        await client.read_kv2("secret", "p", "token")


async def test_approle_login_without_token_raises_vault_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"auth": {}})

    client = VaultClient(_ADDR, AppRoleAuth("rid", "sid"), client=_mock_client(handler))
    with pytest.raises(VaultError, match="no client token"):
        await client.read_kv2("secret", "p", "token")


async def test_approle_uses_custom_login_mount() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "login" in request.url.path:
            seen.append(request.url.path)
            return httpx.Response(
                200, json={"auth": {"client_token": "tok-1", "lease_duration": 0}}
            )
        return httpx.Response(200, json={"data": {"data": {"token": "v"}}})

    client = VaultClient(
        _ADDR,
        AppRoleAuth("rid", "sid", mount="my-approle"),
        client=_mock_client(handler),
    )
    await client.read_kv2("secret", "p", "token")
    assert seen == ["/v1/auth/my-approle/login"]
