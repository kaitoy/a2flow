from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.bootstrap import seed_system_user
from models.user import SYSTEM_USER_ID
from tests._envelope import assert_err, assert_ok
from tests.conftest import _install_auth_overrides


@pytest_asyncio.fixture()
async def user_client() -> AsyncGenerator[AsyncClient, None]:
    from infrastructure.database import get_session
    from main import app
    from models.tenant import Tenant as _Tenant  # noqa: F401 — registers model
    from models.user import User as _User  # noqa: F401 — registers model

    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(mem_engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(mem_engine) as session:
        await seed_system_user(session)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    _install_auth_overrides(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-Id": SYSTEM_USER_ID},
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        await mem_engine.dispose()


_CREATE_BODY = {
    "username": "alice",
    "firstName": "Alice",
    "lastName": "Smith",
    "password": "secret123abc",
    "email": "alice@example.com",
}


# ---------- create ----------


async def test_create_user_returns_201(user_client: AsyncClient) -> None:
    response = await user_client.post("/api/v1/users", json=_CREATE_BODY)
    assert response.status_code == 201


async def test_create_user_response_has_id(user_client: AsyncClient) -> None:
    response = await user_client.post("/api/v1/users", json=_CREATE_BODY)
    assert "id" in assert_ok(response, status=201)


async def test_create_user_response_omits_password(user_client: AsyncClient) -> None:
    response = await user_client.post("/api/v1/users", json=_CREATE_BODY)
    assert "password" not in assert_ok(response, status=201)


async def test_create_user_response_has_correct_fields(
    user_client: AsyncClient,
) -> None:
    body = assert_ok(
        await user_client.post("/api/v1/users", json=_CREATE_BODY), status=201
    )
    assert body["username"] == "alice"
    assert body["firstName"] == "Alice"
    assert body["lastName"] == "Smith"
    assert body["email"] == "alice@example.com"


async def test_create_user_defaults_enabled_true_and_email_verified_false(
    user_client: AsyncClient,
) -> None:
    body = assert_ok(
        await user_client.post("/api/v1/users", json=_CREATE_BODY), status=201
    )
    assert body["enabled"] is True
    assert body["emailVerified"] is False


async def test_create_user_explicit_flags_are_reflected(
    user_client: AsyncClient,
) -> None:
    body = assert_ok(
        await user_client.post(
            "/api/v1/users",
            json={**_CREATE_BODY, "enabled": False, "emailVerified": True},
        ),
        status=201,
    )
    assert body["enabled"] is False
    assert body["emailVerified"] is True


async def test_create_user_missing_username_returns_422(
    user_client: AsyncClient,
) -> None:
    body = {k: v for k, v in _CREATE_BODY.items() if k != "username"}
    response = await user_client.post("/api/v1/users", json=body)
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_user_missing_password_returns_422(
    user_client: AsyncClient,
) -> None:
    body = {k: v for k, v in _CREATE_BODY.items() if k != "password"}
    response = await user_client.post("/api/v1/users", json=body)
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_user_duplicate_username_returns_409(
    user_client: AsyncClient,
) -> None:
    await user_client.post("/api/v1/users", json=_CREATE_BODY)
    response = await user_client.post(
        "/api/v1/users", json={**_CREATE_BODY, "email": "other@example.com"}
    )
    assert_err(response, code="CONFLICT_UNIQUE", status=409)


# ---------- list ----------


async def test_list_users_empty_initially(user_client: AsyncClient) -> None:
    response = await user_client.get("/api/v1/users")
    assert assert_ok(response) == []


async def test_list_users_returns_created_user(user_client: AsyncClient) -> None:
    await user_client.post("/api/v1/users", json=_CREATE_BODY)
    response = await user_client.get("/api/v1/users")
    assert len(assert_ok(response)) == 1


async def test_list_users_omits_password(user_client: AsyncClient) -> None:
    await user_client.post("/api/v1/users", json=_CREATE_BODY)
    data = assert_ok(await user_client.get("/api/v1/users"))
    assert all("password" not in user for user in data)


async def test_list_users_respects_limit_param(user_client: AsyncClient) -> None:
    for i in range(3):
        await user_client.post(
            "/api/v1/users",
            json={**_CREATE_BODY, "username": f"user{i}", "email": f"u{i}@x.com"},
        )
    response = await user_client.get("/api/v1/users", params={"limit": 2})
    assert len(assert_ok(response)) == 2


# ---------- get ----------


async def test_get_user_returns_correct_data(user_client: AsyncClient) -> None:
    created = assert_ok(
        await user_client.post("/api/v1/users", json=_CREATE_BODY), status=201
    )
    response = await user_client.get(f"/api/v1/users/{created['id']}")
    body = assert_ok(response)
    assert body["username"] == "alice"
    assert "password" not in body


async def test_get_user_unknown_id_returns_404(user_client: AsyncClient) -> None:
    response = await user_client.get("/api/v1/users/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- patch ----------


async def test_update_user_partial_update_leaves_other_fields_unchanged(
    user_client: AsyncClient,
) -> None:
    created = assert_ok(
        await user_client.post("/api/v1/users", json=_CREATE_BODY), status=201
    )
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}", json={"firstName": "Alicia"}
    )
    body = assert_ok(response)
    assert body["firstName"] == "Alicia"
    assert body["username"] == "alice"
    assert body["lastName"] == "Smith"


async def test_update_user_without_password_succeeds_and_omits_password(
    user_client: AsyncClient,
) -> None:
    created = assert_ok(
        await user_client.post("/api/v1/users", json=_CREATE_BODY), status=201
    )
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}", json={"firstName": "Alicia"}
    )
    assert "password" not in assert_ok(response)


async def test_update_user_with_password_succeeds(user_client: AsyncClient) -> None:
    created = assert_ok(
        await user_client.post("/api/v1/users", json=_CREATE_BODY), status=201
    )
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}", json={"password": "newsecret456"}
    )
    assert assert_ok(response)["username"] == "alice"


async def test_update_user_ignores_username_change(
    user_client: AsyncClient,
) -> None:
    created = assert_ok(
        await user_client.post("/api/v1/users", json=_CREATE_BODY), status=201
    )
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"username": "renamed", "firstName": "Alicia"},
    )
    body = assert_ok(response)
    # username is immutable: the change is dropped, other fields still apply.
    assert body["username"] == "alice"
    assert body["firstName"] == "Alicia"


async def test_update_user_unknown_id_returns_404(user_client: AsyncClient) -> None:
    response = await user_client.patch(
        "/api/v1/users/nonexistent", json={"firstName": "X"}
    )
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- avatar config ----------


_AVATAR_CONFIG = {
    "selections": {"head": "braids", "body": "hoodie"},
    "colors": {"hair": "#4A3728"},
    "background": "#EFEFEF",
}


async def test_create_user_avatar_config_defaults_none(
    user_client: AsyncClient,
) -> None:
    body = assert_ok(
        await user_client.post("/api/v1/users", json=_CREATE_BODY), status=201
    )
    assert body["avatarConfig"] is None


async def test_update_user_avatar_config_round_trips(user_client: AsyncClient) -> None:
    created = assert_ok(
        await user_client.post("/api/v1/users", json=_CREATE_BODY), status=201
    )
    updated = assert_ok(
        await user_client.patch(
            f"/api/v1/users/{created['id']}", json={"avatarConfig": _AVATAR_CONFIG}
        )
    )
    assert updated["avatarConfig"] == _AVATAR_CONFIG
    fetched = assert_ok(await user_client.get(f"/api/v1/users/{created['id']}"))
    assert fetched["avatarConfig"] == _AVATAR_CONFIG


async def test_update_user_avatar_config_can_be_cleared(
    user_client: AsyncClient,
) -> None:
    created = assert_ok(
        await user_client.post("/api/v1/users", json=_CREATE_BODY), status=201
    )
    await user_client.patch(
        f"/api/v1/users/{created['id']}", json={"avatarConfig": _AVATAR_CONFIG}
    )
    cleared = assert_ok(
        await user_client.patch(
            f"/api/v1/users/{created['id']}", json={"avatarConfig": None}
        )
    )
    assert cleared["avatarConfig"] is None


async def test_update_user_avatar_config_rejects_oversized(
    user_client: AsyncClient,
) -> None:
    created = assert_ok(
        await user_client.post("/api/v1/users", json=_CREATE_BODY), status=201
    )
    oversized = {"selections": {f"slot{i}": "part" for i in range(51)}}
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}", json={"avatarConfig": oversized}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


# ---------- delete ----------


async def test_delete_user_returns_200(user_client: AsyncClient) -> None:
    created = assert_ok(
        await user_client.post("/api/v1/users", json=_CREATE_BODY), status=201
    )
    response = await user_client.delete(f"/api/v1/users/{created['id']}")
    assert assert_ok(response, status=200) is None


async def test_delete_user_removes_from_list(user_client: AsyncClient) -> None:
    created = assert_ok(
        await user_client.post("/api/v1/users", json=_CREATE_BODY), status=201
    )
    await user_client.delete(f"/api/v1/users/{created['id']}")
    response = await user_client.get("/api/v1/users")
    assert assert_ok(response) == []


async def test_delete_user_unknown_id_returns_404(user_client: AsyncClient) -> None:
    response = await user_client.delete("/api/v1/users/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- created_by / updated_by ----------


async def _create_actor(user_client: AsyncClient, username: str) -> str:
    """Create a user (as the default system actor) and return its id for use as an actor."""
    actor = assert_ok(
        await user_client.post(
            "/api/v1/users",
            json={**_CREATE_BODY, "username": username, "email": f"{username}@x.com"},
        ),
        status=201,
    )
    return str(actor["id"])


async def test_create_user_populates_created_and_updated_by_from_header(
    user_client: AsyncClient,
) -> None:
    admin_id = await _create_actor(user_client, "admin")
    response = await user_client.post(
        "/api/v1/users", json=_CREATE_BODY, headers={"X-User-Id": admin_id}
    )
    body = assert_ok(response, status=201)
    assert body["createdBy"] == admin_id
    assert body["updatedBy"] == admin_id


async def test_update_user_preserves_created_by_and_overwrites_updated_by(
    user_client: AsyncClient,
) -> None:
    admin_id = await _create_actor(user_client, "admin")
    root_id = await _create_actor(user_client, "root")
    created = assert_ok(
        await user_client.post(
            "/api/v1/users", json=_CREATE_BODY, headers={"X-User-Id": admin_id}
        ),
        status=201,
    )
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"firstName": "Alicia"},
        headers={"X-User-Id": root_id},
    )
    body = assert_ok(response)
    assert body["createdBy"] == admin_id
    assert body["updatedBy"] == root_id


async def test_create_user_with_unknown_actor_returns_422(
    user_client: AsyncClient,
) -> None:
    response = await user_client.post(
        "/api/v1/users", json=_CREATE_BODY, headers={"X-User-Id": "ghost-user"}
    )
    assert_err(response, code="FOREIGN_KEY_VIOLATION", status=422)


# ---------- soft / hard delete ----------


async def test_delete_unreferenced_user_hard_deletes(user_client: AsyncClient) -> None:
    created = assert_ok(
        await user_client.post("/api/v1/users", json=_CREATE_BODY), status=201
    )
    await user_client.delete(f"/api/v1/users/{created['id']}")
    assert_err(
        await user_client.get(f"/api/v1/users/{created['id']}"),
        code="NOT_FOUND",
        status=404,
    )


async def test_delete_referenced_user_soft_deletes(user_client: AsyncClient) -> None:
    # ``actor`` creates ``dependent``; ``actor`` is then referenced via
    # ``dependent.created_by`` and can only be soft-deleted.
    actor_id = await _create_actor(user_client, "actor")
    assert_ok(
        await user_client.post(
            "/api/v1/users",
            json={**_CREATE_BODY, "username": "dependent", "email": "dep@x.com"},
            headers={"X-User-Id": actor_id},
        ),
        status=201,
    )

    await user_client.delete(f"/api/v1/users/{actor_id}")

    # Hidden from the list, but still fetchable with ``deletedAt`` populated.
    listed = assert_ok(await user_client.get("/api/v1/users"))
    assert all(u["id"] != actor_id for u in listed)
    fetched = assert_ok(await user_client.get(f"/api/v1/users/{actor_id}"))
    assert fetched["deletedAt"] is not None
    assert fetched["enabled"] is False


async def test_system_user_is_hidden_from_list(user_client: AsyncClient) -> None:
    listed = assert_ok(await user_client.get("/api/v1/users"))
    assert all(u["id"] != SYSTEM_USER_ID for u in listed)


# ---------- field validation ----------


async def test_create_user_rejects_short_password(user_client: AsyncClient) -> None:
    """A password shorter than 12 characters returns 422."""
    response = await user_client.post(
        "/api/v1/users", json={**_CREATE_BODY, "password": "short"}
    )
    assert_err(response, "VALIDATION_ERROR", 422)


async def test_create_user_rejects_invalid_email(user_client: AsyncClient) -> None:
    """A malformed email address returns 422."""
    response = await user_client.post(
        "/api/v1/users", json={**_CREATE_BODY, "email": "not-an-email"}
    )
    assert_err(response, "VALIDATION_ERROR", 422)


async def test_create_user_rejects_username_with_bad_charset(
    user_client: AsyncClient,
) -> None:
    """A username with characters outside the slug set returns 422."""
    response = await user_client.post(
        "/api/v1/users", json={**_CREATE_BODY, "username": "has space"}
    )
    assert_err(response, "VALIDATION_ERROR", 422)


# ---------- roles & self-service authorization ----------


async def _create_user(
    user_client: AsyncClient, headers: dict[str, str] | None = None, **overrides: Any
) -> Any:
    """Create a user (default: as super admin) and return the response body."""
    body = {**_CREATE_BODY, **overrides}
    return assert_ok(
        await user_client.post("/api/v1/users", json=body, headers=headers or {}),
        status=201,
    )


async def test_create_user_persists_roles(user_client: AsyncClient) -> None:
    """Roles supplied at creation are stored and returned, deduplicated."""
    body = await _create_user(
        user_client, roles=["developer", "requester", "developer"]
    )
    assert body["roles"] == ["developer", "requester"]


async def test_create_user_rejects_unknown_role(user_client: AsyncClient) -> None:
    """A role outside the Role enum returns 422."""
    response = await user_client.post(
        "/api/v1/users", json={**_CREATE_BODY, "roles": ["wizard"]}
    )
    assert_err(response, "VALIDATION_ERROR", 422)


async def test_admin_cannot_create_super_admin(user_client: AsyncClient) -> None:
    """An admin (non-super) creating a super_admin user is rejected."""
    response = await user_client.post(
        "/api/v1/users",
        json={**_CREATE_BODY, "roles": ["super_admin"]},
        headers={"X-User-Roles": "admin"},
    )
    assert_err(response, "FORBIDDEN", 403)


async def test_super_admin_can_create_super_admin(user_client: AsyncClient) -> None:
    """A super admin may create another super_admin user."""
    body = await _create_user(
        user_client, headers={"X-User-Roles": "super_admin"}, roles=["super_admin"]
    )
    assert body["roles"] == ["super_admin"]


async def test_admin_cannot_grant_super_admin(user_client: AsyncClient) -> None:
    """An admin (non-super) granting super_admin via PATCH is rejected."""
    created = await _create_user(user_client)
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"roles": ["super_admin"]},
        headers={"X-User-Roles": "admin"},
    )
    assert_err(response, "FORBIDDEN", 403)


async def test_admin_cannot_revoke_super_admin(user_client: AsyncClient) -> None:
    """An admin (non-super) revoking super_admin via PATCH is rejected."""
    created = await _create_user(user_client, roles=["super_admin"])
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"roles": []},
        headers={"X-User-Roles": "admin"},
    )
    assert_err(response, "FORBIDDEN", 403)


async def test_admin_can_update_other_roles(user_client: AsyncClient) -> None:
    """An admin may grant and revoke non-super roles freely."""
    created = await _create_user(user_client, roles=["requester"])
    body = assert_ok(
        await user_client.patch(
            f"/api/v1/users/{created['id']}",
            json={"roles": ["developer", "approver"]},
            headers={"X-User-Roles": "admin"},
        )
    )
    assert body["roles"] == ["developer", "approver"]


async def test_admin_can_edit_super_admin_user_without_touching_roles(
    user_client: AsyncClient,
) -> None:
    """An admin editing a super_admin's profile (roles unchanged) is allowed."""
    created = await _create_user(user_client, roles=["super_admin"])
    body = assert_ok(
        await user_client.patch(
            f"/api/v1/users/{created['id']}",
            json={"firstName": "Renamed"},
            headers={"X-User-Roles": "admin"},
        )
    )
    assert body["firstName"] == "Renamed"
    assert body["roles"] == ["super_admin"]


async def test_super_admin_can_grant_and_revoke_super_admin(
    user_client: AsyncClient,
) -> None:
    """A super admin may grant and then revoke the super_admin role."""
    created = await _create_user(user_client)
    granted = assert_ok(
        await user_client.patch(
            f"/api/v1/users/{created['id']}",
            json={"roles": ["super_admin"]},
            headers={"X-User-Roles": "super_admin"},
        )
    )
    assert granted["roles"] == ["super_admin"]
    revoked = assert_ok(
        await user_client.patch(
            f"/api/v1/users/{created['id']}",
            json={"roles": []},
            headers={"X-User-Roles": "super_admin"},
        )
    )
    assert revoked["roles"] == []


async def test_roleless_user_can_update_own_avatar_config(
    user_client: AsyncClient,
) -> None:
    """A user without roles may PATCH their own avatar customization."""
    created = await _create_user(user_client)
    body = assert_ok(
        await user_client.patch(
            f"/api/v1/users/{created['id']}",
            json={"avatarConfig": {"selections": {"hair": "h1"}}},
            headers={"X-User-Id": created["id"], "X-User-Roles": ""},
        )
    )
    assert body["avatarConfig"]["selections"] == {"hair": "h1"}


async def test_roleless_user_cannot_update_own_profile_fields(
    user_client: AsyncClient,
) -> None:
    """A non-admin PATCHing their own non-self-service field is rejected."""
    created = await _create_user(user_client)
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"firstName": "Hacked"},
        headers={"X-User-Id": created["id"], "X-User-Roles": ""},
    )
    assert_err(response, "FORBIDDEN", 403)


async def test_roleless_user_cannot_update_other_user(
    user_client: AsyncClient,
) -> None:
    """A non-admin PATCHing another user is rejected even for avatar_config."""
    created = await _create_user(user_client)
    other = await _create_user(
        user_client, username="mallory", email="mallory@example.com"
    )
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"avatarConfig": {"selections": {}}},
        headers={"X-User-Id": other["id"], "X-User-Roles": "developer,approver"},
    )
    assert_err(response, "FORBIDDEN", 403)


# ---------- tenant assignment authorization ----------


async def _create_tenant(user_client: AsyncClient, **overrides: Any) -> Any:
    """Create a tenant (default: as super admin) and return the response body."""
    body = {"name": "Acme Corp", "slug": "acme-corp", **overrides}
    return assert_ok(await user_client.post("/api/v1/tenants", json=body), status=201)


async def test_admin_cannot_assign_tenant_on_create(user_client: AsyncClient) -> None:
    """An admin (non-super) creating a user with a tenantId is rejected."""
    tenant = await _create_tenant(user_client)
    response = await user_client.post(
        "/api/v1/users",
        json={**_CREATE_BODY, "tenantId": tenant["id"]},
        headers={"X-User-Roles": "admin"},
    )
    assert_err(response, "FORBIDDEN", 403)


async def test_super_admin_can_assign_tenant_on_create(
    user_client: AsyncClient,
) -> None:
    """A super admin may assign a tenant when creating a user."""
    tenant = await _create_tenant(user_client)
    body = await _create_user(
        user_client, headers={"X-User-Roles": "super_admin"}, tenantId=tenant["id"]
    )
    assert body["tenantId"] == tenant["id"]


async def test_admin_cannot_change_tenant_on_update(user_client: AsyncClient) -> None:
    """An admin (non-super) changing a user's tenantId via PATCH is rejected."""
    tenant = await _create_tenant(user_client)
    created = await _create_user(user_client)
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"tenantId": tenant["id"]},
        headers={"X-User-Roles": "admin"},
    )
    assert_err(response, "FORBIDDEN", 403)


async def test_super_admin_can_change_tenant_on_update(
    user_client: AsyncClient,
) -> None:
    """A super admin may change a user's tenant via PATCH."""
    tenant = await _create_tenant(user_client)
    created = await _create_user(user_client)
    body = assert_ok(
        await user_client.patch(
            f"/api/v1/users/{created['id']}",
            json={"tenantId": tenant["id"]},
            headers={"X-User-Roles": "super_admin"},
        )
    )
    assert body["tenantId"] == tenant["id"]


async def test_admin_can_resubmit_unchanged_tenant_on_update(
    user_client: AsyncClient,
) -> None:
    """An admin may PATCH other fields while resending the user's current tenantId."""
    tenant = await _create_tenant(user_client)
    created = await _create_user(
        user_client, headers={"X-User-Roles": "super_admin"}, tenantId=tenant["id"]
    )
    body = assert_ok(
        await user_client.patch(
            f"/api/v1/users/{created['id']}",
            json={"firstName": "Renamed", "tenantId": tenant["id"]},
            headers={"X-User-Roles": "admin"},
        )
    )
    assert body["firstName"] == "Renamed"
    assert body["tenantId"] == tenant["id"]


# ---------- super_admin cannot carry a tenant ----------


async def test_create_user_rejects_super_admin_with_tenant(
    user_client: AsyncClient,
) -> None:
    """A super admin creating a super_admin user with a tenantId is rejected."""
    tenant = await _create_tenant(user_client)
    response = await user_client.post(
        "/api/v1/users",
        json={**_CREATE_BODY, "roles": ["super_admin"], "tenantId": tenant["id"]},
        headers={"X-User-Roles": "super_admin"},
    )
    assert_err(response, "INVALID_USER", 422)


async def test_admin_cannot_create_super_admin_with_tenant(
    user_client: AsyncClient,
) -> None:
    """An admin (non-super) attempting the same combo still gets the existing role-grant 403."""
    tenant = await _create_tenant(user_client)
    response = await user_client.post(
        "/api/v1/users",
        json={**_CREATE_BODY, "roles": ["super_admin"], "tenantId": tenant["id"]},
        headers={"X-User-Roles": "admin"},
    )
    assert_err(response, "FORBIDDEN", 403)


async def test_update_user_rejects_granting_super_admin_to_tenant_scoped_user(
    user_client: AsyncClient,
) -> None:
    """Granting super_admin to a user who already has a tenantId is rejected."""
    tenant = await _create_tenant(user_client)
    created = await _create_user(
        user_client, headers={"X-User-Roles": "super_admin"}, tenantId=tenant["id"]
    )
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"roles": ["super_admin"]},
        headers={"X-User-Roles": "super_admin"},
    )
    assert_err(response, "INVALID_USER", 422)


async def test_update_user_rejects_assigning_tenant_to_super_admin(
    user_client: AsyncClient,
) -> None:
    """Assigning a tenantId to an existing super_admin user is rejected."""
    tenant = await _create_tenant(user_client)
    created = await _create_user(user_client, roles=["super_admin"])
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"tenantId": tenant["id"]},
        headers={"X-User-Roles": "super_admin"},
    )
    assert_err(response, "INVALID_USER", 422)


async def test_update_user_rejects_simultaneous_super_admin_grant_and_tenant_assign(
    user_client: AsyncClient,
) -> None:
    """A single PATCH granting super_admin and assigning a tenantId together is rejected."""
    tenant = await _create_tenant(user_client)
    created = await _create_user(user_client)
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"roles": ["super_admin"], "tenantId": tenant["id"]},
        headers={"X-User-Roles": "super_admin"},
    )
    assert_err(response, "INVALID_USER", 422)


async def test_update_user_allows_revoking_super_admin_while_assigning_tenant(
    user_client: AsyncClient,
) -> None:
    """Revoking super_admin and assigning a tenantId in the same PATCH succeeds."""
    tenant = await _create_tenant(user_client)
    created = await _create_user(user_client, roles=["super_admin"])
    body = assert_ok(
        await user_client.patch(
            f"/api/v1/users/{created['id']}",
            json={"roles": [], "tenantId": tenant["id"]},
            headers={"X-User-Roles": "super_admin"},
        )
    )
    assert body["roles"] == []
    assert body["tenantId"] == tenant["id"]


async def test_update_user_allows_clearing_tenant_while_granting_super_admin(
    user_client: AsyncClient,
) -> None:
    """Granting super_admin and clearing the tenantId in the same PATCH succeeds."""
    tenant = await _create_tenant(user_client)
    created = await _create_user(
        user_client, headers={"X-User-Roles": "super_admin"}, tenantId=tenant["id"]
    )
    body = assert_ok(
        await user_client.patch(
            f"/api/v1/users/{created['id']}",
            json={"roles": ["super_admin"], "tenantId": None},
            headers={"X-User-Roles": "super_admin"},
        )
    )
    assert body["roles"] == ["super_admin"]
    assert body["tenantId"] is None
