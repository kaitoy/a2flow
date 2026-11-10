"""Tests for the admin-managed tenant settings routes (``/tenant-settings``)."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure import url_safety
from infrastructure.bootstrap import seed_system_settings
from infrastructure.secret_cipher import get_secret_cipher
from models.system_settings import SYSTEM_SETTINGS_ID, SystemSettings
from models.tenant import Tenant
from models.user import SYSTEM_USER_ID, User
from tests._engine import make_test_engine
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_users
from tests.conftest import _install_auth_overrides

_PATH = "/api/v1/tenant-settings"


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
    settings_engine: AsyncEngine,
) -> AsyncGenerator[AsyncClient, None]:
    """Client bound to :func:`settings_engine`."""
    from infrastructure.database import get_session
    from main import app

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
    "oidcGroupsClaim": "groups",
    "oidcTrustEmail": False,
    "oidcRedirectUri": None,
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
    }


async def test_patch_updates_and_null_keeps(settings_client: AsyncClient) -> None:
    limits = {"loginMaxFailures": 3, "loginLockoutMinutes": 60}
    assert assert_ok(await settings_client.patch(_PATH, json=limits)) == {
        **limits,
        **_NO_VAULT,
        **_NO_OIDC,
    }
    assert assert_ok(
        await settings_client.patch(_PATH, json={"loginMaxFailures": None})
    ) == {**limits, **_NO_VAULT, **_NO_OIDC}


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


async def test_changing_issuer_or_client_id_clears_oidc_subjects(
    settings_client: AsyncClient, settings_engine: AsyncEngine
) -> None:
    async with AsyncSession(settings_engine) as session:
        session.add(
            User(
                id="linked",
                username="linked",
                first_name="L",
                last_name="U",
                password="x",
                email="linked@example.com",
                tenant_id=DEFAULT_TEST_TENANT_ID,
                oidc_subject="abc",
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await session.commit()

    async def subject() -> str | None:
        async with AsyncSession(settings_engine) as session:
            user = await session.get(User, "linked")
            assert user is not None
            return user.oidc_subject

    assert_ok(await settings_client.patch(_PATH, json={"oidcClientId": "one"}))
    assert await subject() is None  # first set: changed from None

    async with AsyncSession(settings_engine) as session:
        user = await session.get(User, "linked")
        assert user is not None
        user.oidc_subject = "abc"
        session.add(user)
        await session.commit()

    assert_ok(await settings_client.patch(_PATH, json={"oidcClientId": "one"}))
    assert await subject() == "abc"  # same value: no reset
    assert_ok(await settings_client.patch(_PATH, json={"oidcClientId": "two"}))
    assert await subject() is None


async def test_redirect_uri_follows_app_base_url(
    settings_client: AsyncClient, settings_engine: AsyncEngine
) -> None:
    assert assert_ok(await settings_client.get(_PATH))["oidcRedirectUri"] is None
    async with AsyncSession(settings_engine) as session:
        row = await session.get(SystemSettings, SYSTEM_SETTINGS_ID)
        assert row is not None
        row.app_base_url = "https://a2.example.com/"
        session.add(row)
        await session.commit()
    assert (
        assert_ok(await settings_client.get(_PATH))["oidcRedirectUri"]
        == "https://a2.example.com/api/v1/auth/oidc/callback"
    )
