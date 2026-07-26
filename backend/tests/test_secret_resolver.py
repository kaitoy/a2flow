"""Unit tests for ${secret:NAME/KEY} placeholder resolution."""

from typing import cast

import pytest
from cryptography.fernet import Fernet

from infrastructure.secret_cipher import SecretCipher
from infrastructure.secret_resolver import SecretResolver, split_secret_ref
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
    """Stand-in VaultClient returning a data map derived from the reference."""

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    async def read_kv2(self, mount: str, path: str) -> dict[str, str]:
        if self._fail:
            raise VaultError("sealed")
        return {
            "token": f"vault:{mount}/{path}/token",
            "username": f"vault:{mount}/{path}/username",
        }


def _local_secret(name: str, **entries: str) -> Secret:
    return Secret(
        name=name,
        type=SecretType.local,
        entries={key: _CIPHER.encrypt(value) for key, value in entries.items()},
        created_by=SYSTEM_USER_ID,
        updated_by=SYSTEM_USER_ID,
    )


def _vault_secret(name: str) -> Secret:
    return Secret(
        name=name,
        type=SecretType.vault,
        vault_mount="secret",
        vault_path="myapp/github",
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


def test_split_secret_ref_separates_name_and_key() -> None:
    assert split_secret_ref("api-key/token") == ("api-key", "token")


def test_split_secret_ref_without_key_yields_none() -> None:
    assert split_secret_ref("api-key") == ("api-key", None)


async def test_resolve_value_decrypts_local_entry() -> None:
    resolver, _ = _resolver([_local_secret("api-key", token="plain-1")])
    assert await resolver.resolve_value("api-key", "token") == "plain-1"


async def test_resolve_value_picks_the_requested_entry() -> None:
    resolver, _ = _resolver([_local_secret("aws", ID="the-id", KEY="the-key")])
    assert await resolver.resolve_value("aws", "ID") == "the-id"
    assert await resolver.resolve_value("aws", "KEY") == "the-key"


async def test_resolve_value_unknown_name_raises() -> None:
    resolver, _ = _resolver([])
    with pytest.raises(SecretResolutionError, match="api-key"):
        await resolver.resolve_value("api-key", "token")


async def test_resolve_value_unknown_key_raises() -> None:
    resolver, _ = _resolver([_local_secret("api-key", token="plain-1")])
    with pytest.raises(SecretResolutionError, match="api-key"):
        await resolver.resolve_value("api-key", "nope")


async def test_resolve_value_undecryptable_ciphertext_raises() -> None:
    broken = _local_secret("api-key", token="x")
    broken.entries["token"] = SecretCipher(Fernet.generate_key()).encrypt("x")
    resolver, _ = _resolver([broken])
    with pytest.raises(SecretResolutionError, match="api-key"):
        await resolver.resolve_value("api-key", "token")


async def test_resolve_value_reads_vault_secret() -> None:
    resolver, _ = _resolver([_vault_secret("gh")], vault=_FakeVault())
    assert (
        await resolver.resolve_value("gh", "token") == "vault:secret/myapp/github/token"
    )


async def test_resolve_value_vault_unknown_key_raises() -> None:
    resolver, _ = _resolver([_vault_secret("gh")], vault=_FakeVault())
    with pytest.raises(SecretResolutionError, match="gh"):
        await resolver.resolve_value("gh", "nope")


async def test_resolve_value_vault_unconfigured_raises() -> None:
    resolver, _ = _resolver([_vault_secret("gh")], vault=None)
    with pytest.raises(SecretResolutionError, match="Vault"):
        await resolver.resolve_value("gh", "token")


async def test_resolve_value_vault_failure_raises() -> None:
    resolver, _ = _resolver([_vault_secret("gh")], vault=_FakeVault(fail=True))
    with pytest.raises(SecretResolutionError, match="gh"):
        await resolver.resolve_value("gh", "token")


async def test_resolve_ref_resolves_name_and_key() -> None:
    resolver, _ = _resolver([_local_secret("api-key", token="plain-1")])
    assert await resolver.resolve_ref("api-key/token") == "plain-1"


async def test_resolve_ref_without_key_raises() -> None:
    resolver, _ = _resolver([_local_secret("api-key", token="plain-1")])
    with pytest.raises(SecretResolutionError, match="api-key"):
        await resolver.resolve_ref("api-key")


async def test_resolve_text_replaces_multiple_placeholders() -> None:
    resolver, _ = _resolver([_local_secret("aws", ID="AAA", KEY="BBB")])
    result = await resolver.resolve_text("x ${secret:aws/ID} y ${secret:aws/KEY} z")
    assert result == "x AAA y BBB z"


async def test_resolve_text_rejects_placeholder_without_key() -> None:
    """A key-less placeholder fails loudly rather than passing through as text.

    Leaving it unsubstituted would hand the literal ``${secret:a}`` to the MCP
    server as if it were the credential.
    """
    resolver, _ = _resolver([_local_secret("a", token="AAA")])
    with pytest.raises(SecretResolutionError, match="a"):
        await resolver.resolve_text("x ${secret:a} y")


async def test_resolve_text_rejects_key_less_placeholder_on_single_entry() -> None:
    """Even an unambiguous single-entry secret requires an explicit key."""
    resolver, _ = _resolver([_local_secret("solo", only="AAA")])
    with pytest.raises(SecretResolutionError, match="solo"):
        await resolver.resolve_text("${secret:solo}")


async def test_resolve_text_without_placeholder_is_untouched_and_free() -> None:
    resolver, repo = _resolver([_local_secret("a", token="AAA")])
    assert await resolver.resolve_text("Bearer literal-token") == "Bearer literal-token"
    assert repo.lookups == 0


async def test_resolve_headers_resolves_values_only() -> None:
    resolver, _ = _resolver([_local_secret("tok", token="T")])
    headers = await resolver.resolve_headers(
        {"Authorization": "Bearer ${secret:tok/token}", "X-Plain": "as-is"}
    )
    assert headers == {"Authorization": "Bearer T", "X-Plain": "as-is"}


async def test_resolve_headers_missing_secret_raises() -> None:
    resolver, _ = _resolver([])
    with pytest.raises(SecretResolutionError, match="nope"):
        await resolver.resolve_headers({"Authorization": "Bearer ${secret:nope/k}"})
