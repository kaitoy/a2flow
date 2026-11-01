"""Tests for the admin-managed tenant settings routes (``/tenant-settings``)."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from models.user import SYSTEM_USER_ID
from tests._engine import make_test_engine
from tests._envelope import assert_err, assert_ok
from tests._seed import seed_users
from tests.conftest import _install_auth_overrides

_PATH = "/api/v1/tenant-settings"


@pytest_asyncio.fixture()
async def settings_client() -> AsyncGenerator[AsyncClient, None]:
    """Client bound to a throwaway database holding the default test tenant."""
    from infrastructure.database import get_session
    from main import app

    engine = await make_test_engine()
    await seed_users(engine, ids=())

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
        await engine.dispose()


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
    }


async def test_patch_updates_and_null_keeps(settings_client: AsyncClient) -> None:
    limits = {"loginMaxFailures": 3, "loginLockoutMinutes": 60}
    assert assert_ok(await settings_client.patch(_PATH, json=limits)) == {
        **limits,
        **_NO_VAULT,
    }
    assert assert_ok(
        await settings_client.patch(_PATH, json={"loginMaxFailures": None})
    ) == {**limits, **_NO_VAULT}


async def test_global_vault_credential_is_not_a_tenant_setting(
    settings_client: AsyncClient,
) -> None:
    """Only a super admin registers it (on the tenant record); here it is ignored."""
    response = await settings_client.patch(
        _PATH,
        json={"globalVaultAuthMethod": "token", "globalVaultCredential": "hvs.x"},
    )
    body = assert_ok(response)
    assert body == {"loginMaxFailures": 5, "loginLockoutMinutes": 15, **_NO_VAULT}


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
