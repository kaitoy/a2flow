"""Google OAuth 2.0 access tokens for MCP servers, minted from a stored credential.

Google-managed remote MCP servers (``https://container.googleapis.com/mcp``
and its siblings) do not take API keys: every request must carry
``Authorization: Bearer <OAuth 2.0 access token>`` minted for a Google Cloud
identity -- a service account, or a user who granted consent once. An access
token lives an hour, so one cannot simply be pasted into a Secret. What is
stored instead is the *credential that mints them*, and this module turns a
``${gcp-token:NAME/KEY}`` placeholder into a fresh token at connection time.

Two credential JSON shapes are accepted, told apart by their ``type``:

* ``service_account`` -- a service account key as downloaded from the Cloud
  Console. Tokens are minted with the ``cloud-platform`` scope, which every
  Google Cloud MCP server accepts.
* ``authorized_user`` -- what ``gcloud auth application-default login
  --client-id-file=<OAuth client JSON> --scopes=...`` writes to
  ``application_default_credentials.json``: the OAuth client id and secret
  plus the refresh token that consent produced. Tokens carry whatever scopes
  were granted then, so none are requested here.

Anything else -- another ``type``, malformed JSON, a refresh the token
endpoint rejects -- surfaces as
:class:`repositories.exceptions.SecretResolutionError`, the same 502 a
dangling ``${secret:...}`` reference produces, with the raw reason logged
server-side only.

Lives beside :mod:`infrastructure.mcp_connection` rather than in
:mod:`infrastructure.mcp_client` for the same reason secret resolution does:
the token is minted here, in the backend, and crosses to the MCP proxy as an
already-resolved header value, so that container needs no Google credential.
"""

import asyncio
import json
import re
from functools import lru_cache

from google.auth.credentials import Credentials
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2 import credentials as user_credentials
from google.oauth2 import service_account

from infrastructure.secret_resolver import SecretResolver
from repositories.exceptions import SecretResolutionError

#: Matches ``${gcp-token:NAME/KEY}``, the same shape as ``${secret:NAME/KEY}``
#: (see :data:`infrastructure.secret_resolver.PLACEHOLDER_PATTERN`): the key
#: group is optional so a key-less reference still matches and fails loudly.
GCP_TOKEN_PLACEHOLDER_PATTERN = re.compile(
    r"\$\{gcp-token:([A-Za-z0-9._-]+)(?:/([^}]+))?\}"
)

#: Scope a service account token is minted with. Broad on purpose: it is what
#: every Google Cloud MCP server accepts, and the identity's IAM roles -- not
#: the scope -- are what actually bound what its tools may do.
_SERVICE_ACCOUNT_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)

#: Reason reported when a reference names a secret but no entry within it.
_MISSING_KEY_REASON = "a key is required: reference the entry as ${gcp-token:NAME/KEY}"


@lru_cache(maxsize=16)
def _load_credentials(info_json: str) -> Credentials:
    """Parse a credential JSON into the google-auth object that mints tokens.

    Cached on the JSON text itself so the access token google-auth keeps on
    the object survives across connections: one refresh an hour per distinct
    credential, not one per tool call.

    Args:
        info_json: The stored credential, as JSON text.

    Returns:
        Scoped service account credentials, or authorized-user credentials
        carrying the scopes consent granted.

    Raises:
        ValueError: If the text is not a JSON object, its ``type`` is neither
            ``service_account`` nor ``authorized_user``, or it lacks a field
            that type requires.
    """
    info = json.loads(info_json)
    if not isinstance(info, dict):
        raise ValueError("credential JSON must be an object")
    kind = info.get("type")
    if kind == "service_account":
        return service_account.Credentials.from_service_account_info(  # type: ignore[no-any-return,no-untyped-call]
            info, scopes=_SERVICE_ACCOUNT_SCOPES
        )
    if kind == "authorized_user":
        return user_credentials.Credentials.from_authorized_user_info(info)  # type: ignore[no-any-return,no-untyped-call]
    raise ValueError(f"unsupported credential type: {kind!r}")


def _access_token(info_json: str) -> str:
    """Return a currently valid access token for the credential, refreshing if stale.

    Runs blocking I/O (the token endpoint round-trip) and so is called through
    :func:`asyncio.to_thread`.

    Args:
        info_json: The stored credential, as JSON text.

    Returns:
        The bearer token.

    Raises:
        ValueError: See :func:`_load_credentials`.
        google.auth.exceptions.GoogleAuthError: If the token endpoint rejects
            the refresh.
    """
    # ponytail: no lock around refresh -- two calls racing on an expired
    # token both refresh, harmlessly. Add a per-credential lock if the token
    # endpoint's quota ever shows up in the logs.
    credentials = _load_credentials(info_json)
    if not credentials.valid:
        credentials.refresh(Request())  # type: ignore[no-untyped-call]
    return str(credentials.token)


async def resolve_gcp_tokens(
    values: dict[str, str], resolver: SecretResolver
) -> dict[str, str]:
    """Replace every ``${gcp-token:NAME/KEY}`` in a mapping's values with a token.

    Values without the placeholder are returned unchanged and cost no lookup.

    Args:
        values: Header names (or env var names) to values, the values possibly
            containing placeholders.
        resolver: Resolver used to read the credential JSON the placeholder
            names.

    Returns:
        A new mapping with every placeholder replaced; keys are untouched.

    Raises:
        SecretResolutionError: If a placeholder omits its key, the referenced
            entry fails to resolve, the credential is malformed, or the token
            endpoint rejects the refresh.
    """
    resolved: dict[str, str] = {}
    for name, value in values.items():
        resolved[name] = await _resolve_text(value, resolver)
    return resolved


async def _resolve_text(text: str, resolver: SecretResolver) -> str:
    """Replace every placeholder in one value; see :func:`resolve_gcp_tokens`."""
    result: list[str] = []
    cursor = 0
    for match in GCP_TOKEN_PLACEHOLDER_PATTERN.finditer(text):
        secret_name, key = match.group(1), match.group(2)
        if key is None:
            raise SecretResolutionError(secret_name, _MISSING_KEY_REASON)
        info_json = await resolver.resolve_value(secret_name, key)
        try:
            token = await asyncio.to_thread(_access_token, info_json)
        except (ValueError, GoogleAuthError) as e:
            raise SecretResolutionError(secret_name, str(e)) from e
        result.append(text[cursor : match.start()])
        result.append(token)
        cursor = match.end()
    if not result:
        return text
    result.append(text[cursor:])
    return "".join(result)
