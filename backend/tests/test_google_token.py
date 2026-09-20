"""Tests for minting Google access tokens from a ``${gcp-token:NAME/KEY}`` placeholder."""

import json
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth.exceptions import GoogleAuthError
from google.oauth2 import credentials as user_credentials
from google.oauth2 import service_account

from infrastructure import google_token
from infrastructure.google_token import (
    _access_token,
    _load_credentials,
    resolve_gcp_tokens,
)
from infrastructure.secret_resolver import SecretResolver
from repositories.exceptions import SecretResolutionError

_AUTHORIZED_USER_JSON = json.dumps(
    {
        "type": "authorized_user",
        "client_id": "id.apps.googleusercontent.com",
        "client_secret": "GOCSPX-secret",
        "refresh_token": "1//refresh",
    }
)


def _service_account_json() -> str:
    """A syntactically complete service account key with a throwaway RSA key."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return json.dumps(
        {
            "type": "service_account",
            "project_id": "demo-project",
            "private_key_id": "kid",
            "private_key": pem,
            "client_email": "demo@demo-project.iam.gserviceaccount.com",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )


class _StubResolver:
    """Stand-in for ``SecretResolver`` serving one entry and recording lookups."""

    def __init__(self, value: str) -> None:
        self.value = value
        self.lookups: list[tuple[str, str]] = []

    async def resolve_value(self, name: str, key: str) -> str:
        self.lookups.append((name, key))
        return self.value


class _FakeCredentials:
    """Minimal ``google.auth.credentials.Credentials`` double for the refresh branch."""

    def __init__(self, *, valid: bool, token: str | None) -> None:
        self.valid = valid
        self.token = token
        self.refreshed = 0

    def refresh(self, request: Any) -> None:
        self.refreshed += 1
        self.valid = True
        self.token = "fresh-token"


# --- resolve_gcp_tokens ------------------------------------------------------


async def test_resolve_gcp_tokens_replaces_the_placeholder_with_a_minted_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    minted_from: list[str] = []

    def fake_access_token(info_json: str) -> str:
        minted_from.append(info_json)
        return "ya29.token"

    monkeypatch.setattr(google_token, "_access_token", fake_access_token)
    stub = _StubResolver(_AUTHORIZED_USER_JSON)
    resolver: SecretResolver = stub  # type: ignore[assignment]

    resolved = await resolve_gcp_tokens(
        {
            "Authorization": "Bearer ${gcp-token:gcp-creds/GOOGLE_CREDENTIALS_JSON}",
            "x-goog-user-project": "demo-project",
        },
        resolver,
    )

    assert resolved == {
        "Authorization": "Bearer ya29.token",
        "x-goog-user-project": "demo-project",
    }
    assert stub.lookups == [("gcp-creds", "GOOGLE_CREDENTIALS_JSON")]
    assert minted_from == [_AUTHORIZED_USER_JSON]


async def test_resolve_gcp_tokens_leaves_values_without_placeholders_alone() -> None:
    stub = _StubResolver("unused")
    resolver: SecretResolver = stub  # type: ignore[assignment]

    resolved = await resolve_gcp_tokens(
        {"Authorization": "Bearer ${secret:other/token}", "Accept": "*/*"}, resolver
    )

    assert resolved == {
        "Authorization": "Bearer ${secret:other/token}",
        "Accept": "*/*",
    }
    assert stub.lookups == []


async def test_resolve_gcp_tokens_rejects_a_key_less_reference() -> None:
    stub = _StubResolver("unused")
    resolver: SecretResolver = stub  # type: ignore[assignment]

    with pytest.raises(SecretResolutionError):
        await resolve_gcp_tokens({"Authorization": "${gcp-token:gcp-creds}"}, resolver)
    assert stub.lookups == []


@pytest.mark.parametrize(
    "failure",
    [
        GoogleAuthError("token endpoint said no"),  # type: ignore[no-untyped-call]
        ValueError("not credentials"),
    ],
    ids=["google-auth", "malformed"],
)
async def test_resolve_gcp_tokens_reports_a_minting_failure_as_secret_resolution(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    def fake_access_token(info_json: str) -> str:
        raise failure

    monkeypatch.setattr(google_token, "_access_token", fake_access_token)
    resolver: SecretResolver = _StubResolver("{}")  # type: ignore[assignment]

    with pytest.raises(SecretResolutionError) as excinfo:
        await resolve_gcp_tokens(
            {"Authorization": "Bearer ${gcp-token:gcp-creds/JSON}"}, resolver
        )
    assert excinfo.value.details() == {"secret": "gcp-creds"}


# --- _access_token -----------------------------------------------------------


def test_access_token_refreshes_a_stale_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeCredentials(valid=False, token=None)
    monkeypatch.setattr(google_token, "_load_credentials", lambda info_json: fake)

    assert _access_token("{}") == "fresh-token"
    assert fake.refreshed == 1


def test_access_token_reuses_a_valid_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeCredentials(valid=True, token="still-good")
    monkeypatch.setattr(google_token, "_load_credentials", lambda info_json: fake)

    assert _access_token("{}") == "still-good"
    assert fake.refreshed == 0


# --- _load_credentials -------------------------------------------------------


def test_load_credentials_builds_scoped_service_account_credentials() -> None:
    creds = _load_credentials(_service_account_json())

    assert isinstance(creds, service_account.Credentials)
    assert creds.service_account_email == "demo@demo-project.iam.gserviceaccount.com"
    assert list(creds.scopes) == ["https://www.googleapis.com/auth/cloud-platform"]


def test_load_credentials_builds_authorized_user_credentials_with_granted_scopes() -> (
    None
):
    creds = _load_credentials(_AUTHORIZED_USER_JSON)

    assert isinstance(creds, user_credentials.Credentials)
    assert creds.client_id == "id.apps.googleusercontent.com"
    assert creds.refresh_token == "1//refresh"
    # No scopes are requested on refresh: the token carries whatever consent granted.
    assert creds.scopes is None


@pytest.mark.parametrize(
    "info_json",
    [
        json.dumps({"type": "external_account"}),
        json.dumps({"client_id": "no-type"}),
        json.dumps(["not", "an", "object"]),
        "not json at all",
    ],
    ids=["unsupported-type", "no-type", "not-an-object", "not-json"],
)
def test_load_credentials_rejects_anything_else(info_json: str) -> None:
    with pytest.raises(ValueError):
        _load_credentials(info_json)
