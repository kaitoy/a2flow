"""Tests for the Admin Settings routes (``/admin-settings``)."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure import url_safety
from infrastructure.bootstrap import seed_system_settings
from infrastructure.secret_cipher import get_secret_cipher
from models.tenant import LlmMode, Tenant
from models.user import SYSTEM_USER_ID, User
from repositories.exceptions import ForeignKeyViolationError, UniqueViolationError
from repositories.tenant import SqlTenantRepository
from repositories.user import SqlUserRepository
from tests._engine import make_test_engine
from tests._envelope import assert_err, assert_ok
from tests._seed import (
    DEFAULT_TEST_TENANT_ID,
    seed_local_secret,
    seed_tenant,
    seed_users,
)
from tests.conftest import _install_auth_overrides

_PATH = "/api/v1/admin-settings"


@pytest_asyncio.fixture()
async def settings_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Throwaway database holding the default test tenant and system settings."""
    engine = await make_test_engine()
    await seed_users(engine, ids=())
    async with AsyncSession(engine) as session:
        await seed_system_settings(session)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture()
async def settings_client(
    settings_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[AsyncClient, None]:
    """Client bound to :func:`settings_engine`, with no ``APP_BASE_URL``.

    Importing ``main`` loads ``backend/.env`` into the environment, so a
    developer's own ``APP_BASE_URL`` would otherwise reach the redirect URIs.
    """
    from infrastructure.database import get_session
    from main import app

    monkeypatch.delenv("APP_BASE_URL", raising=False)
    get_settings.cache_clear()

    engine = settings_engine

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    _install_auth_overrides(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-Id": SYSTEM_USER_ID, "X-User-Roles": "admin"},
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


#: The OIDC fields of an unconfigured tenant (no ``app_base_url`` either).
_NO_OIDC = {
    "oidcEnabled": False,
    "oidcIssuer": None,
    "oidcClientId": None,
    "oidcClientSecretSet": False,
    "oidcClientSecretRef": None,
    "oidcGroupsClaim": "groups",
    "oidcTrustEmail": False,
    "oidcRedirectUri": None,
    "oidcSubdomainRedirectUri": None,
}

#: The LLM fields of a tenant that runs on the platform's LLM.
_NO_LLM = {
    "llmMode": "system_default",
    "llmModel": None,
    "llmApiKeySet": False,
    "llmApiKeyRef": None,
}

#: The Vault fields of an unconfigured tenant.
_NO_VAULT = {
    "vaultAddr": None,
    "vaultAuthMethod": None,
    "vaultRoleId": None,
    "vaultApproleMount": None,
    "vaultCredentialSet": False,
}

#: A Vault on a public IP literal, so the SSRF check needs no DNS lookup.
_VAULT = {
    "vaultAddr": "https://93.184.215.14:8200",
    "vaultAuthMethod": "token",
    "vaultCredential": "hvs.secret-token",
}


async def test_get_returns_defaults(settings_client: AsyncClient) -> None:
    assert assert_ok(await settings_client.get(_PATH)) == {
        "loginMaxFailures": 5,
        "loginLockoutMinutes": 15,
        **_NO_VAULT,
        **_NO_OIDC,
        **_NO_LLM,
    }


async def test_patch_updates_and_null_keeps(settings_client: AsyncClient) -> None:
    limits = {"loginMaxFailures": 3, "loginLockoutMinutes": 60}
    assert assert_ok(await settings_client.patch(_PATH, json=limits)) == {
        **limits,
        **_NO_VAULT,
        **_NO_OIDC,
        **_NO_LLM,
    }
    assert assert_ok(
        await settings_client.patch(_PATH, json={"loginMaxFailures": None})
    ) == {**limits, **_NO_VAULT, **_NO_OIDC, **_NO_LLM}


async def test_global_vault_credential_is_not_a_tenant_setting(
    settings_client: AsyncClient,
) -> None:
    """Only a super admin registers it (on the tenant record); here it is ignored."""
    response = await settings_client.patch(
        _PATH,
        json={"globalVaultAuthMethod": "token", "globalVaultCredential": "hvs.x"},
    )
    body = assert_ok(response)
    assert body == {
        "loginMaxFailures": 5,
        "loginLockoutMinutes": 15,
        **_NO_VAULT,
        **_NO_OIDC,
        **_NO_LLM,
    }


# ---------- vault connection ----------


async def test_vault_credential_is_stored_encrypted_and_never_returned(
    settings_client: AsyncClient,
) -> None:
    response = await settings_client.patch(_PATH, json=_VAULT)
    body = assert_ok(response)
    assert body["vaultAddr"] == _VAULT["vaultAddr"]
    assert body["vaultCredentialSet"] is True
    assert "vaultCredential" not in body
    assert "hvs.secret-token" not in response.text
    assert "hvs.secret-token" not in (await settings_client.get(_PATH)).text


async def test_blank_vault_credential_keeps_and_null_clears(
    settings_client: AsyncClient,
) -> None:
    assert_ok(await settings_client.patch(_PATH, json=_VAULT))
    body = assert_ok(
        await settings_client.patch(
            _PATH,
            json={"vaultAddr": "https://93.184.215.15", "vaultCredential": ""},
        )
    )
    assert body["vaultCredentialSet"] is True

    cleared = assert_ok(
        await settings_client.patch(
            _PATH, json={"vaultAddr": None, "vaultCredential": None}
        )
    )
    assert cleared["vaultCredentialSet"] is False
    assert cleared["vaultAddr"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"vaultAddr": _VAULT["vaultAddr"]},
        {**_VAULT, "vaultAuthMethod": "approle"},
    ],
)
async def test_unusable_vault_connection_is_rejected(
    settings_client: AsyncClient, body: dict[str, str]
) -> None:
    assert_err(
        await settings_client.patch(_PATH, json=body),
        code="INVALID_TENANT",
        status=422,
    )


@pytest.mark.parametrize(
    "addr", ["https://10.0.0.5:8200", "http://127.0.0.1:8200", "https://[::1]"]
)
async def test_private_vault_address_is_rejected(
    settings_client: AsyncClient, addr: str
) -> None:
    """A tenant user must not point A2Flow at an internal address."""
    assert_err(
        await settings_client.patch(_PATH, json={**_VAULT, "vaultAddr": addr}),
        code="VALIDATION_ERROR",
        status=422,
    )


async def test_switching_vault_auth_method_needs_a_new_credential(
    settings_client: AsyncClient,
) -> None:
    """A stored token must not be reused as an AppRole secret id."""
    assert_ok(await settings_client.patch(_PATH, json=_VAULT))
    switch = {"vaultAuthMethod": "approle", "vaultRoleId": "role-1"}
    assert_err(
        await settings_client.patch(_PATH, json=switch),
        code="INVALID_TENANT",
        status=422,
    )
    body = assert_ok(
        await settings_client.patch(
            _PATH, json={**switch, "vaultCredential": "secret-id-1"}
        )
    )
    assert body["vaultAuthMethod"] == "approle"


@pytest.mark.parametrize(
    "body",
    [
        {"loginMaxFailures": 0},
        {"loginMaxFailures": 101},
        {"loginLockoutMinutes": 0},
        {"loginLockoutMinutes": 1441},
    ],
)
async def test_patch_rejects_out_of_range(
    settings_client: AsyncClient, body: dict[str, int]
) -> None:
    assert_err(
        await settings_client.patch(_PATH, json=body),
        code="VALIDATION_ERROR",
        status=422,
    )


@pytest.mark.parametrize("role", ["developer", "requester", "approver", ""])
async def test_non_admin_is_forbidden(settings_client: AsyncClient, role: str) -> None:
    headers = {"X-User-Roles": role}
    assert_err(
        await settings_client.get(_PATH, headers=headers), code="FORBIDDEN", status=403
    )
    assert_err(
        await settings_client.patch(
            _PATH, json={"loginMaxFailures": 3}, headers=headers
        ),
        code="FORBIDDEN",
        status=403,
    )


async def test_group_granted_admin_may_edit(settings_client: AsyncClient) -> None:
    assert_ok(
        await settings_client.patch(
            _PATH,
            json={"loginMaxFailures": 7},
            headers={"X-User-Roles": "", "X-User-Group-Roles": "admin"},
        )
    )


# ---------- OIDC single sign-on ----------

#: A public IP literal, so the SSRF check needs no DNS lookup.
_OIDC = {
    "oidcIssuer": "https://93.184.215.14/realms/a",
    "oidcClientId": "a2flow",
    "oidcClientSecret": "s3cret",
}


async def _tenant(engine: AsyncEngine) -> Tenant:
    async with AsyncSession(engine) as session:
        tenant = await session.get(Tenant, DEFAULT_TEST_TENANT_ID)
        assert tenant is not None
        return tenant


async def test_oidc_secret_is_encrypted_and_never_returned(
    settings_client: AsyncClient, settings_engine: AsyncEngine
) -> None:
    response = await settings_client.patch(_PATH, json={"oidcClientSecret": "s3cret"})
    body = assert_ok(response)
    assert body["oidcClientSecretSet"] is True
    assert "oidcClientSecret" not in body
    assert "s3cret" not in response.text
    stored = (await _tenant(settings_engine)).oidc_client_secret
    assert stored is not None and stored != "s3cret"
    assert get_secret_cipher().decrypt(stored) == "s3cret"


async def test_oidc_secret_blank_clears_and_omitted_keeps(
    settings_client: AsyncClient,
) -> None:
    assert_ok(await settings_client.patch(_PATH, json={"oidcClientSecret": "s3cret"}))
    kept = assert_ok(await settings_client.patch(_PATH, json={"oidcClientId": "x"}))
    assert kept["oidcClientSecretSet"] is True
    cleared = assert_ok(
        await settings_client.patch(_PATH, json={"oidcClientSecret": ""})
    )
    assert cleared["oidcClientSecretSet"] is False


async def test_enable_oidc_requires_issuer_client_and_secret(
    settings_client: AsyncClient,
) -> None:
    assert_err(
        await settings_client.patch(_PATH, json={"oidcEnabled": True}),
        code="INVALID_TENANT",
        status=422,
    )
    body = assert_ok(
        await settings_client.patch(_PATH, json={**_OIDC, "oidcEnabled": True})
    )
    assert body["oidcEnabled"] is True


async def test_clearing_a_required_field_while_enabled_is_rejected(
    settings_client: AsyncClient,
) -> None:
    assert_ok(await settings_client.patch(_PATH, json={**_OIDC, "oidcEnabled": True}))
    for body in ({"oidcClientSecret": ""}, {"oidcClientId": ""}, {"oidcIssuer": ""}):
        assert_err(
            await settings_client.patch(_PATH, json=body),
            code="INVALID_TENANT",
            status=422,
        )


async def test_oidc_secret_ref_replaces_the_stored_secret_and_back(
    settings_client: AsyncClient, settings_engine: AsyncEngine
) -> None:
    await seed_local_secret(settings_engine, "idp", {"client-secret": "s3cret"})
    assert_ok(await settings_client.patch(_PATH, json={"oidcClientSecret": "s3cret"}))

    body = assert_ok(
        await settings_client.patch(
            _PATH, json={"oidcClientSecretRef": "idp/client-secret"}
        )
    )
    assert body["oidcClientSecretRef"] == "idp/client-secret"
    assert body["oidcClientSecretSet"] is False
    assert (await _tenant(settings_engine)).oidc_client_secret is None

    body = assert_ok(
        await settings_client.patch(_PATH, json={"oidcClientSecret": "other"})
    )
    assert body["oidcClientSecretRef"] is None
    assert body["oidcClientSecretSet"] is True


async def test_oidc_secret_ref_alone_lets_sso_be_enabled(
    settings_client: AsyncClient, settings_engine: AsyncEngine
) -> None:
    await seed_local_secret(settings_engine, "idp", {"client-secret": "s3cret"})
    body = {
        "oidcIssuer": _OIDC["oidcIssuer"],
        "oidcClientId": "a2flow",
        "oidcClientSecretRef": "idp/client-secret",
        "oidcEnabled": True,
    }

    assert assert_ok(await settings_client.patch(_PATH, json=body))["oidcEnabled"]
    # Dropping the reference with no secret entered leaves SSO without one.
    assert_err(
        await settings_client.patch(_PATH, json={"oidcClientSecretRef": None}),
        code="INVALID_TENANT",
        status=422,
    )


async def test_oidc_secret_ref_must_name_a_secret_of_the_tenant(
    settings_client: AsyncClient, settings_engine: AsyncEngine
) -> None:
    await seed_tenant(settings_engine, "tenant-other")
    await seed_local_secret(
        settings_engine, "theirs", {"k": "v"}, tenant_id="tenant-other"
    )
    for ref in ("missing/k", "theirs/k"):
        assert_err(
            await settings_client.patch(_PATH, json={"oidcClientSecretRef": ref}),
            code="FOREIGN_KEY_VIOLATION",
            status=422,
        )


async def test_oidc_secret_and_ref_together_are_rejected(
    settings_client: AsyncClient, settings_engine: AsyncEngine
) -> None:
    await seed_local_secret(settings_engine, "idp", {"client-secret": "s3cret"})
    assert_err(
        await settings_client.patch(
            _PATH,
            json={"oidcClientSecret": "x", "oidcClientSecretRef": "idp/client-secret"},
        ),
        code="INVALID_TENANT",
        status=422,
    )


async def test_oidc_issuer_private_address_rejected(
    settings_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(url_safety, "resolve_host", lambda host: ["10.0.0.5"])
    assert_err(
        await settings_client.patch(
            _PATH, json={"oidcIssuer": "https://idp.example.com/realms/a"}
        ),
        code="INVALID_TENANT",
        status=422,
    )


async def test_oidc_issuer_private_host_allowed_by_env(
    settings_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(url_safety, "resolve_host", lambda host: ["10.0.0.5"])
    monkeypatch.setenv("OIDC_ALLOWED_PRIVATE_HOSTS", "Keycloak.internal")
    body = assert_ok(
        await settings_client.patch(
            _PATH, json={"oidcIssuer": "http://keycloak.internal/realms/a"}
        )
    )
    assert body["oidcIssuer"] == "http://keycloak.internal/realms/a"


async def test_oidc_issuer_plain_http_needs_allowlisted_host(
    settings_client: AsyncClient,
) -> None:
    assert_err(
        await settings_client.patch(
            _PATH, json={"oidcIssuer": "http://idp.example.com/realms/a"}
        ),
        code="INVALID_TENANT",
        status=422,
    )


async def test_oidc_issuer_not_rechecked_when_unchanged(
    settings_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    issuer = "https://idp.example.com/realms/a"
    assert_ok(await settings_client.patch(_PATH, json={"oidcIssuer": issuer}))
    # The stored host now resolves to a private address: resending it unchanged
    # alongside an unrelated edit must still save, a different one must not.
    monkeypatch.setattr(url_safety, "resolve_host", lambda host: ["10.0.0.5"])
    body = assert_ok(
        await settings_client.patch(
            _PATH, json={"oidcIssuer": issuer, "oidcClientId": "other"}
        )
    )
    assert body["oidcClientId"] == "other"
    assert_err(
        await settings_client.patch(
            _PATH, json={"oidcIssuer": "https://idp2.example.com/realms/a"}
        ),
        code="INVALID_TENANT",
        status=422,
    )


async def _link_user(
    engine: AsyncEngine, user_id: str, tenant_id: str = DEFAULT_TEST_TENANT_ID
) -> None:
    """Insert (or re-link) a user of ``tenant_id`` holding ``oidc_subject="abc"``."""
    async with AsyncSession(engine) as session:
        user = await session.get(User, user_id)
        if user is None:
            user = User(
                id=user_id,
                username=user_id,
                first_name="L",
                last_name="U",
                password="x",
                email=f"{user_id}@example.com",
                tenant_id=tenant_id,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        user.oidc_subject = "abc"
        session.add(user)
        await session.commit()


async def _subject(engine: AsyncEngine, user_id: str) -> str | None:
    async with AsyncSession(engine) as session:
        user = await session.get(User, user_id)
        assert user is not None
        return user.oidc_subject


async def test_changing_issuer_or_client_id_clears_oidc_subjects(
    settings_client: AsyncClient, settings_engine: AsyncEngine
) -> None:
    await _link_user(settings_engine, "linked")

    assert_ok(await settings_client.patch(_PATH, json={"oidcClientId": "one"}))
    assert await _subject(settings_engine, "linked") is None  # None -> "one"

    await _link_user(settings_engine, "linked")
    assert_ok(await settings_client.patch(_PATH, json={"oidcClientId": "one"}))
    assert await _subject(settings_engine, "linked") == "abc"  # same value: no reset
    assert_ok(await settings_client.patch(_PATH, json={"oidcClientId": "two"}))
    assert await _subject(settings_engine, "linked") is None

    await _link_user(settings_engine, "linked")
    assert_ok(
        await settings_client.patch(_PATH, json={"oidcIssuer": _OIDC["oidcIssuer"]})
    )
    assert await _subject(settings_engine, "linked") is None  # issuer changed
    await _link_user(settings_engine, "linked")
    assert_ok(
        await settings_client.patch(_PATH, json={"oidcIssuer": _OIDC["oidcIssuer"]})
    )
    assert await _subject(settings_engine, "linked") == "abc"


async def test_subject_reset_leaves_other_tenants_alone(
    settings_client: AsyncClient, settings_engine: AsyncEngine
) -> None:
    await seed_tenant(settings_engine, "tenant-other")
    await _link_user(settings_engine, "mine")
    await _link_user(settings_engine, "theirs", tenant_id="tenant-other")

    assert_ok(await settings_client.patch(_PATH, json={"oidcClientId": "one"}))

    assert await _subject(settings_engine, "mine") is None
    assert await _subject(settings_engine, "theirs") == "abc"


async def test_failed_tenant_write_rolls_the_subject_reset_back(
    settings_client: AsyncClient,
    settings_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never "new provider + old subjects", nor "old provider + cleared subjects"."""
    await _link_user(settings_engine, "linked")

    async def failing_update(*args: object, **kwargs: object) -> Tenant:
        raise UniqueViolationError("Tenant", "display_name", "x")

    monkeypatch.setattr(SqlTenantRepository, "update", failing_update)
    assert_err(
        await settings_client.patch(_PATH, json={"oidcClientId": "one"}),
        code="CONFLICT_UNIQUE",
        status=409,
    )

    assert (await _tenant(settings_engine)).oidc_client_id is None
    assert await _subject(settings_engine, "linked") == "abc"


async def test_failed_subject_reset_leaves_the_provider_unchanged(
    settings_client: AsyncClient,
    settings_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed reset must stay retryable: the same PATCH still sees a change."""
    await _link_user(settings_engine, "linked")

    async def failing_reset(*args: object, **kwargs: object) -> None:
        raise ForeignKeyViolationError("User", "x")

    with monkeypatch.context() as patch:
        patch.setattr(SqlUserRepository, "clear_oidc_subjects", failing_reset)
        assert_err(
            await settings_client.patch(_PATH, json={"oidcClientId": "one"}),
            code="FOREIGN_KEY_VIOLATION",
            status=422,
        )
    assert (await _tenant(settings_engine)).oidc_client_id is None
    assert await _subject(settings_engine, "linked") == "abc"

    assert_ok(await settings_client.patch(_PATH, json={"oidcClientId": "one"}))
    assert await _subject(settings_engine, "linked") is None


async def test_redirect_uri_follows_app_base_url(
    settings_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_BASE_URL", "")
    get_settings.cache_clear()
    assert assert_ok(await settings_client.get(_PATH))["oidcRedirectUri"] is None
    monkeypatch.setenv("APP_BASE_URL", "https://a2.example.com/")
    get_settings.cache_clear()
    assert (
        assert_ok(await settings_client.get(_PATH))["oidcRedirectUri"]
        == "https://a2.example.com/api/v1/auth/oidc/callback"
    )


async def test_redirect_uris_cover_both_addresses(
    settings_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_BASE_URL", "https://a2.example.com")
    get_settings.cache_clear()
    data = assert_ok(await settings_client.get(_PATH))
    assert data["oidcRedirectUri"] == "https://a2.example.com/api/v1/auth/oidc/callback"
    assert data["oidcSubdomainRedirectUri"] == (
        f"https://{DEFAULT_TEST_TENANT_ID}.a2.example.com/api/v1/auth/oidc/callback"
    )


# ---------- LLM ----------


async def _set_llm_mode(engine: AsyncEngine, mode: LlmMode) -> None:
    """Hand the default tenant's LLM to ``mode``, as a super admin would."""
    async with AsyncSession(engine) as session:
        tenant = await session.get(Tenant, DEFAULT_TEST_TENANT_ID)
        assert tenant is not None
        tenant.llm_mode = mode
        session.add(tenant)
        await session.commit()


_LLM_BODY = {"llmModel": "litellm:openai/gpt-6.1-sol", "llmApiKey": "sk-tenant"}


@pytest.mark.parametrize("mode", [LlmMode.system_default, LlmMode.super_admin])
async def test_admin_cannot_set_the_llm_unless_it_was_handed_to_them(
    settings_client: AsyncClient, settings_engine: AsyncEngine, mode: LlmMode
) -> None:
    await _set_llm_mode(settings_engine, mode)

    assert_err(await settings_client.patch(_PATH, json=_LLM_BODY), "FORBIDDEN", 403)

    body = assert_ok(await settings_client.get(_PATH))
    assert body["llmMode"] == mode.value
    assert body["llmModel"] is None
    assert body["llmApiKeySet"] is False


async def test_admin_can_set_the_llm_once_handed_to_them(
    settings_client: AsyncClient, settings_engine: AsyncEngine
) -> None:
    await _set_llm_mode(settings_engine, LlmMode.tenant_admin)

    body = assert_ok(await settings_client.patch(_PATH, json=_LLM_BODY))

    assert body["llmMode"] == "tenant_admin"
    assert body["llmModel"] == "litellm:openai/gpt-6.1-sol"
    assert body["llmApiKeySet"] is True
    assert "sk-tenant" not in str(body)
    async with AsyncSession(settings_engine) as session:
        tenant = await session.get(Tenant, DEFAULT_TEST_TENANT_ID)
    assert tenant is not None and tenant.llm_api_key is not None
    assert tenant.llm_api_key != "sk-tenant"
    assert get_secret_cipher().decrypt(tenant.llm_api_key) == "sk-tenant"


async def test_empty_llm_key_keeps_the_stored_one_and_null_clears_it(
    settings_client: AsyncClient, settings_engine: AsyncEngine
) -> None:
    await _set_llm_mode(settings_engine, LlmMode.tenant_admin)
    assert_ok(await settings_client.patch(_PATH, json=_LLM_BODY))

    kept = assert_ok(
        await settings_client.patch(_PATH, json={"llmApiKey": "", "llmModel": "m2"})
    )
    cleared = assert_ok(
        await settings_client.patch(_PATH, json={"llmApiKey": None, "llmModel": None})
    )

    assert kept["llmApiKeySet"] is True
    assert kept["llmModel"] == "m2"
    assert cleared["llmApiKeySet"] is False
    assert cleared["llmModel"] is None


async def test_admin_cannot_set_a_model_without_a_key(
    settings_client: AsyncClient, settings_engine: AsyncEngine
) -> None:
    """The tenant's model would otherwise run, and bill, on the platform's key."""
    await _set_llm_mode(settings_engine, LlmMode.tenant_admin)

    assert_err(
        await settings_client.patch(_PATH, json={"llmModel": "m1", "llmApiKey": ""}),
        "INVALID_TENANT",
        422,
    )

    body = assert_ok(await settings_client.get(_PATH))
    assert body["llmModel"] is None


async def test_admin_cannot_clear_the_key_while_a_model_is_set(
    settings_client: AsyncClient, settings_engine: AsyncEngine
) -> None:
    await _set_llm_mode(settings_engine, LlmMode.tenant_admin)
    assert_ok(await settings_client.patch(_PATH, json=_LLM_BODY))

    assert_err(
        await settings_client.patch(_PATH, json={"llmApiKey": None}),
        "INVALID_TENANT",
        422,
    )

    body = assert_ok(await settings_client.get(_PATH))
    assert body["llmApiKeySet"] is True


async def test_unrelated_settings_still_save_while_the_llm_is_not_theirs(
    settings_client: AsyncClient,
) -> None:
    """The guard only applies to a payload that actually sets an ``llm*`` field."""
    body = assert_ok(await settings_client.patch(_PATH, json={"loginMaxFailures": 3}))
    assert body["loginMaxFailures"] == 3


async def test_admin_cannot_change_the_llm_mode(
    settings_client: AsyncClient,
) -> None:
    """Handing the LLM over is the super admin's call; the field is ignored here."""
    body = assert_ok(
        await settings_client.patch(_PATH, json={"llmMode": "tenant_admin"})
    )
    assert body["llmMode"] == "system_default"


async def test_a_referenced_key_satisfies_a_model_and_replaces_the_stored_one(
    settings_client: AsyncClient, settings_engine: AsyncEngine
) -> None:
    await _set_llm_mode(settings_engine, LlmMode.tenant_admin)
    await seed_local_secret(settings_engine, "llm", {"key": "sk-secret"})
    assert_ok(await settings_client.patch(_PATH, json=_LLM_BODY))

    body = assert_ok(
        await settings_client.patch(
            _PATH, json={"llmModel": "m1", "llmApiKeyRef": "llm/key"}
        )
    )

    assert body["llmApiKeyRef"] == "llm/key"
    assert body["llmApiKeySet"] is False
    assert (await _tenant(settings_engine)).llm_api_key is None


async def test_admin_cannot_reference_a_key_unless_the_llm_was_handed_to_them(
    settings_client: AsyncClient, settings_engine: AsyncEngine
) -> None:
    await seed_local_secret(settings_engine, "llm", {"key": "sk-secret"})
    assert_err(
        await settings_client.patch(_PATH, json={"llmApiKeyRef": "llm/key"}),
        "FORBIDDEN",
        403,
    )


async def test_handing_the_llm_over_again_clears_the_key_reference(
    settings_client: AsyncClient, settings_engine: AsyncEngine
) -> None:
    """A super admin's later hand-over starts the admin from an empty LLM."""
    await _set_llm_mode(settings_engine, LlmMode.tenant_admin)
    await seed_local_secret(settings_engine, "llm", {"key": "sk-secret"})
    assert_ok(await settings_client.patch(_PATH, json={"llmApiKeyRef": "llm/key"}))
    await _set_llm_mode(settings_engine, LlmMode.super_admin)
    super_admin = {"X-User-Roles": "super_admin"}

    assert_ok(
        await settings_client.patch(
            f"/api/v1/tenants/{DEFAULT_TEST_TENANT_ID}",
            json={"llmMode": "tenant_admin"},
            headers=super_admin,
        )
    )

    assert (await _tenant(settings_engine)).llm_api_key_ref is None


async def test_a_super_admins_key_replaces_the_admins_reference(
    settings_client: AsyncClient, settings_engine: AsyncEngine
) -> None:
    await _set_llm_mode(settings_engine, LlmMode.tenant_admin)
    await seed_local_secret(settings_engine, "llm", {"key": "sk-secret"})
    assert_ok(await settings_client.patch(_PATH, json={"llmApiKeyRef": "llm/key"}))
    await _set_llm_mode(settings_engine, LlmMode.super_admin)

    tenant = assert_ok(
        await settings_client.patch(
            f"/api/v1/tenants/{DEFAULT_TEST_TENANT_ID}",
            json={"llmApiKey": "sk-platform"},
            headers={"X-User-Roles": "super_admin"},
        )
    )

    assert tenant["llmApiKeySet"] is True
    stored = await _tenant(settings_engine)
    assert stored.llm_api_key_ref is None
    assert stored.llm_api_key is not None
