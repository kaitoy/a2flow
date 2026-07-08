"""Unit tests for ${secret:NAME} placeholder resolution."""

from typing import cast

import pytest
from cryptography.fernet import Fernet

from infrastructure.secret_cipher import SecretCipher
from infrastructure.secret_resolver import SecretResolver
from infrastructure.vault_client import VaultClient, VaultError
from models.secret import Secret, SecretType
from models.user import SYSTEM_USER_ID
from repositories import SecretRepository
from repositories.exceptions import SecretResolutionError

_CIPHER = SecretCipher(Fernet.generate_key())


class _FakeRepo:
    """In-memory stand-in implementing the one lookup the resolver uses."""

    def __init__(self, secrets: list[Secret]) -> None:
        self._by_name = {s.name: s for s in secrets}
        self.lookups = 0

    async def get_by_name(self, name: str) -> Secret | None:
        self.lookups += 1
        return self._by_name.get(name)


class _FakeVault:
    """Stand-in VaultClient returning a value derived from the reference."""

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    async def read_kv2(self, mount: str, path: str, key: str) -> str:
        if self._fail:
            raise VaultError("sealed")
        return f"vault:{mount}/{path}/{key}"


def _local_secret(name: str, value: str) -> Secret:
    return Secret(
        name=name,
        type=SecretType.local,
        value=_CIPHER.encrypt(value),
        created_by=SYSTEM_USER_ID,
        updated_by=SYSTEM_USER_ID,
    )


def _vault_secret(name: str) -> Secret:
    return Secret(
        name=name,
        type=SecretType.vault,
        vault_mount="secret",
        vault_path="myapp/github",
        vault_key="token",
        created_by=SYSTEM_USER_ID,
        updated_by=SYSTEM_USER_ID,
    )


def _resolver(
    secrets: list[Secret],
    *,
    vault: _FakeVault | None = None,
) -> tuple[SecretResolver, _FakeRepo]:
    repo = _FakeRepo(secrets)
    resolver = SecretResolver(
        cast(SecretRepository, repo),
        _CIPHER,
        cast("VaultClient | None", vault),
    )
    return resolver, repo


async def test_resolve_value_decrypts_local_secret() -> None:
    resolver, _ = _resolver([_local_secret("api-key", "plain-1")])
    assert await resolver.resolve_value("api-key") == "plain-1"


async def test_resolve_value_unknown_name_raises() -> None:
    resolver, _ = _resolver([])
    with pytest.raises(SecretResolutionError, match="api-key"):
        await resolver.resolve_value("api-key")


async def test_resolve_value_undecryptable_ciphertext_raises() -> None:
    broken = _local_secret("api-key", "x")
    broken.value = SecretCipher(Fernet.generate_key()).encrypt("x")
    resolver, _ = _resolver([broken])
    with pytest.raises(SecretResolutionError, match="api-key"):
        await resolver.resolve_value("api-key")


async def test_resolve_value_reads_vault_secret() -> None:
    resolver, _ = _resolver([_vault_secret("vault-key")], vault=_FakeVault())
    assert (
        await resolver.resolve_value("vault-key") == "vault:secret/myapp/github/token"
    )


async def test_resolve_value_vault_unconfigured_raises() -> None:
    resolver, _ = _resolver([_vault_secret("vault-key")], vault=None)
    with pytest.raises(SecretResolutionError, match="Vault"):
        await resolver.resolve_value("vault-key")


async def test_resolve_value_vault_failure_raises() -> None:
    resolver, _ = _resolver([_vault_secret("vault-key")], vault=_FakeVault(fail=True))
    with pytest.raises(SecretResolutionError, match="vault-key"):
        await resolver.resolve_value("vault-key")


async def test_resolve_text_replaces_multiple_placeholders() -> None:
    resolver, _ = _resolver([_local_secret("a", "AAA"), _local_secret("b", "BBB")])
    result = await resolver.resolve_text("x ${secret:a} y ${secret:b} z")
    assert result == "x AAA y BBB z"


async def test_resolve_text_without_placeholder_is_untouched_and_free() -> None:
    resolver, repo = _resolver([_local_secret("a", "AAA")])
    assert await resolver.resolve_text("Bearer literal-token") == "Bearer literal-token"
    assert repo.lookups == 0


async def test_resolve_headers_resolves_values_only() -> None:
    resolver, _ = _resolver([_local_secret("tok", "T")])
    headers = await resolver.resolve_headers(
        {"Authorization": "Bearer ${secret:tok}", "X-Plain": "as-is"}
    )
    assert headers == {"Authorization": "Bearer T", "X-Plain": "as-is"}


async def test_resolve_headers_missing_secret_raises() -> None:
    resolver, _ = _resolver([])
    with pytest.raises(SecretResolutionError, match="nope"):
        await resolver.resolve_headers({"Authorization": "Bearer ${secret:nope}"})
