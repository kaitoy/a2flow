from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.bootstrap import seed_system_user
from models.user import SYSTEM_USER_ID
from tests._engine import make_test_engine
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant
from tests.conftest import _install_auth_overrides


@pytest_asyncio.fixture()
async def user_client() -> AsyncGenerator[AsyncClient, None]:
    from infrastructure.database import get_session
    from main import app
    from models.tenant import Tenant as _Tenant  # noqa: F401 — registers model
    from models.user import User as _User  # noqa: F401 — registers model

    mem_engine = await make_test_engine()
    async with AsyncSession(mem_engine) as session:
        await seed_system_user(session)
    await seed_tenant(mem_engine, DEFAULT_TEST_TENANT_ID)

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


#: Every non-super-admin user must carry a tenantId
#: (``ck_users_non_super_admin_requires_tenant``); tests that care about
#: tenant behavior override this explicitly.
_CREATE_BODY = {
    "username": "alice",
    "firstName": "Alice",
    "lastName": "Smith",
    "password": "secret123abc",
    "email": "alice@example.com",
    "tenantId": DEFAULT_TEST_TENANT_ID,
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
    """A duplicate username within the same tenant is rejected."""
    await user_client.post("/api/v1/users", json=_CREATE_BODY)
    response = await user_client.post(
        "/api/v1/users", json={**_CREATE_BODY, "email": "other@example.com"}
    )
    assert_err(response, code="CONFLICT_UNIQUE", status=409)


async def test_create_user_duplicate_username_different_tenant_allowed(
    user_client: AsyncClient,
) -> None:
    """The same username may be reused by a user in a different tenant."""
    await user_client.post("/api/v1/users", json=_CREATE_BODY)
    tenant = await _create_tenant(user_client)
    response = await user_client.post(
        "/api/v1/users",
        json={**_CREATE_BODY, "email": "other@example.com", "tenantId": tenant["id"]},
    )
    assert response.status_code == 201


async def test_create_user_duplicate_username_platform_scoped_returns_409(
    user_client: AsyncClient,
) -> None:
    """Two platform-scoped (super_admin) users cannot share a username."""
    await _create_user(user_client, roles=["super_admin"])
    response = await user_client.post(
        "/api/v1/users",
        json={
            **_CREATE_BODY,
            "email": "other@example.com",
            "roles": ["super_admin"],
            "tenantId": None,
        },
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


# ---------- hidden field query exposure (regression) ----------


async def test_list_users_filter_password_eq_returns_400(
    user_client: AsyncClient,
) -> None:
    """Filtering on the hidden ``password`` column is rejected, not silently applied."""
    response = await user_client.get(
        "/api/v1/users", params={"q": "password:eq:totallyFakePassphrase123"}
    )
    assert_err(response, code="INVALID_QUERY", status=400)


async def test_list_users_filter_password_like_returns_400(
    user_client: AsyncClient,
) -> None:
    """``like`` bypasses value coercion entirely -- the critical regression case."""
    response = await user_client.get("/api/v1/users", params={"q": "password:like:a"})
    assert_err(response, code="INVALID_QUERY", status=400)


async def test_list_users_filter_password_gt_returns_400(
    user_client: AsyncClient,
) -> None:
    """``gt``/``lt`` would otherwise let a caller binary-search the hash by ordering."""
    response = await user_client.get(
        "/api/v1/users", params={"q": "password:gt:totallyFakePassphrase123"}
    )
    assert_err(response, code="INVALID_QUERY", status=400)


async def test_sort_users_by_password_returns_400(user_client: AsyncClient) -> None:
    response = await user_client.get("/api/v1/users", params={"s": "password"})
    assert_err(response, code="INVALID_QUERY", status=400)


async def test_list_users_hidden_field_error_matches_unknown_field_shape(
    user_client: AsyncClient,
) -> None:
    """The hidden-field error is indistinguishable from a genuinely unknown field."""
    hidden = assert_err(
        await user_client.get("/api/v1/users", params={"q": "password:eq:x"}),
        code="INVALID_QUERY",
        status=400,
    )
    unknown = assert_err(
        await user_client.get("/api/v1/users", params={"q": "notAField:eq:x"}),
        code="INVALID_QUERY",
        status=400,
    )
    assert hidden["message"].startswith("Unknown field")
    assert unknown["message"].startswith("Unknown field")


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


_AVATAR_CONFIG = {"colors": ["#4A3728", "#EFEFEF", "#16BFA9"]}


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
    oversized = {"colors": ["#16BFA9"] * 9}
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}", json={"avatarConfig": oversized}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_update_user_avatar_config_rejects_non_hex_color(
    user_client: AsyncClient,
) -> None:
    created = assert_ok(
        await user_client.post("/api/v1/users", json=_CREATE_BODY), status=201
    )
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"avatarConfig": {"colors": ["rebeccapurple"]}},
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
    """Create a user (default: as super admin) and return the response body.

    A ``super_admin`` can never carry a tenant, so requesting that role (and
    not overriding ``tenantId`` explicitly) drops ``_CREATE_BODY``'s default
    tenant instead of leaving a combination the backend would reject.
    """
    body = {**_CREATE_BODY, **overrides}
    if "super_admin" in body.get("roles", []) and "tenantId" not in overrides:
        body["tenantId"] = None
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


async def test_admin_cannot_reach_super_admin_to_revoke_role(
    user_client: AsyncClient,
) -> None:
    """An admin (non-super) revoking super_admin via PATCH gets 404, not 403.

    The target is invisible to a plain admin at all (see
    :func:`_assert_tenant_visible`), so the role-grant/revoke guard is never
    reached.
    """
    created = await _create_user(user_client, roles=["super_admin"])
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"roles": []},
        headers={"X-User-Roles": "admin"},
    )
    assert_err(response, "NOT_FOUND", 404)


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


async def test_admin_cannot_edit_super_admin_user(user_client: AsyncClient) -> None:
    """An admin (non-super) editing a super_admin's profile fields is rejected.

    A super_admin target is invisible to a plain admin (see
    :func:`_assert_tenant_visible`), so even an otherwise-uncontroversial
    profile edit (no role change) gets 404, not a partial success.
    """
    created = await _create_user(user_client, roles=["super_admin"])
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"firstName": "Renamed"},
        headers={"X-User-Roles": "admin"},
    )
    assert_err(response, "NOT_FOUND", 404)


async def test_super_admin_revoking_super_admin_requires_tenant(
    user_client: AsyncClient,
) -> None:
    """Revoking super_admin without supplying a tenantId in the same PATCH is rejected.

    Every non-super-admin user must carry a tenant; a target losing
    super_admin without gaining one violates that invariant. (Granting
    super_admin via PATCH is covered separately by
    ``test_update_user_rejects_granting_super_admin_to_tenant_scoped_user`` —
    since every ordinary user now already has a tenant, that grant is always
    rejected, so there is no longer a "grant succeeds" case to cover here.)
    """
    created = await _create_user(user_client, roles=["super_admin"])
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"roles": []},
        headers={"X-User-Roles": "super_admin"},
    )
    assert_err(response, "INVALID_USER", 422)


async def test_roleless_user_can_update_own_avatar_config(
    user_client: AsyncClient,
) -> None:
    """A user without roles may PATCH their own avatar customization."""
    created = await _create_user(user_client)
    body = assert_ok(
        await user_client.patch(
            f"/api/v1/users/{created['id']}",
            json={"avatarConfig": {"colors": ["#16BFA9"]}},
            headers={"X-User-Id": created["id"], "X-User-Roles": ""},
        )
    )
    assert body["avatarConfig"]["colors"] == ["#16BFA9"]


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
        json={"avatarConfig": {"colors": []}},
        headers={"X-User-Id": other["id"], "X-User-Roles": "developer,approver"},
    )
    assert_err(response, "FORBIDDEN", 403)


# ---------- tenant assignment authorization ----------


async def _create_tenant(user_client: AsyncClient, **overrides: Any) -> Any:
    """Create a tenant (default: as super admin) and return the response body."""
    body = {"displayName": "Acme Corp", "name": "acme-corp", **overrides}
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


async def test_admin_cannot_reach_tenantless_target_to_assign_tenant_on_update(
    user_client: AsyncClient,
) -> None:
    """An admin (non-super) assigning a first tenant via PATCH gets 404, not 403.

    The target has no tenant yet (only possible while it holds super_admin),
    so it's invisible to a plain admin (see :func:`_assert_tenant_visible`)
    before the tenant-assignment guard would even run.
    """
    tenant = await _create_tenant(user_client)
    created = await _create_user(user_client, roles=["super_admin"])
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"tenantId": tenant["id"]},
        headers={"X-User-Roles": "admin"},
    )
    assert_err(response, "NOT_FOUND", 404)


async def test_admin_cannot_change_already_assigned_tenant_on_update(
    user_client: AsyncClient,
) -> None:
    """An admin (non-super) changing an already-assigned tenantId via PATCH is rejected."""
    tenant = await _create_tenant(user_client)
    created = await _create_user(user_client)
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"tenantId": tenant["id"]},
        headers={"X-User-Roles": "admin"},
    )
    assert_err(response, "INVALID_USER", 422)


async def test_super_admin_cannot_change_already_assigned_tenant_on_update(
    user_client: AsyncClient,
) -> None:
    """A tenant is immutable once assigned, even for a super admin."""
    tenant = await _create_tenant(user_client)
    created = await _create_user(user_client)
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"tenantId": tenant["id"]},
        headers={"X-User-Roles": "super_admin"},
    )
    assert_err(response, "INVALID_USER", 422)


async def test_admin_can_resubmit_unchanged_tenant_on_update(
    user_client: AsyncClient,
) -> None:
    """An admin may PATCH other fields while resending the user's current tenantId.

    The acting admin is scoped into the target's own tenant via
    ``X-User-Tenant-Id`` -- an admin from a *different* tenant would not even
    reach this business rule (see the "tenant isolation" section below).
    """
    tenant = await _create_tenant(user_client)
    created = await _create_user(
        user_client, headers={"X-User-Roles": "super_admin"}, tenantId=tenant["id"]
    )
    body = assert_ok(
        await user_client.patch(
            f"/api/v1/users/{created['id']}",
            json={"firstName": "Renamed", "tenantId": tenant["id"]},
            headers={"X-User-Roles": "admin", "X-User-Tenant-Id": tenant["id"]},
        )
    )
    assert body["firstName"] == "Renamed"
    assert body["tenantId"] == tenant["id"]


# ---------- mandatory tenant for non-super-admin ----------


async def test_create_user_rejects_missing_tenant_for_non_super_admin(
    user_client: AsyncClient,
) -> None:
    """Creating a non-super-admin user with no tenantId is rejected."""
    response = await user_client.post(
        "/api/v1/users", json={**_CREATE_BODY, "tenantId": None}
    )
    assert_err(response, "INVALID_USER", 422)


async def test_admin_create_user_auto_assigns_own_tenant(
    user_client: AsyncClient,
) -> None:
    """A plain admin creating a user without tenantId scopes it to their own tenant.

    A non-super-admin actor can't supply a tenantId explicitly (see
    ``test_admin_cannot_assign_tenant_on_create``), yet the new user must
    have one — the backend fills in the acting admin's own tenant instead of
    requiring an "assign tenant" privilege they don't have.
    """
    body = await _create_user(
        user_client, headers={"X-User-Roles": "admin"}, tenantId=None
    )
    assert body["tenantId"] == DEFAULT_TEST_TENANT_ID


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


async def test_update_user_rejects_clearing_already_assigned_tenant_to_grant_super_admin(
    user_client: AsyncClient,
) -> None:
    """A user with an already-assigned tenant can never become super_admin.

    Granting super_admin requires clearing tenant_id (a super admin can never
    carry one), but a tenant is immutable once assigned — so once a user has
    a tenant, that promotion path is permanently closed.
    """
    tenant = await _create_tenant(user_client)
    created = await _create_user(
        user_client, headers={"X-User-Roles": "super_admin"}, tenantId=tenant["id"]
    )
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"roles": ["super_admin"], "tenantId": None},
        headers={"X-User-Roles": "super_admin"},
    )
    assert_err(response, "INVALID_USER", 422)


# ---------- super_admin exclusivity ----------


async def test_create_user_rejects_super_admin_with_another_role(
    user_client: AsyncClient,
) -> None:
    """Creating a user with super_admin alongside another role is rejected."""
    response = await user_client.post(
        "/api/v1/users",
        json={**_CREATE_BODY, "roles": ["super_admin", "admin"], "tenantId": None},
        headers={"X-User-Roles": "super_admin"},
    )
    assert_err(response, "INVALID_USER", 422)


async def test_admin_cannot_create_super_admin_with_another_role(
    user_client: AsyncClient,
) -> None:
    """An admin (non-super) attempting the same combo still gets the existing role-grant 403."""
    response = await user_client.post(
        "/api/v1/users",
        json={**_CREATE_BODY, "roles": ["super_admin", "admin"], "tenantId": None},
        headers={"X-User-Roles": "admin"},
    )
    assert_err(response, "FORBIDDEN", 403)


async def test_update_user_rejects_adding_role_to_super_admin(
    user_client: AsyncClient,
) -> None:
    """Adding a role to an existing super_admin user via PATCH is rejected."""
    created = await _create_user(
        user_client, headers={"X-User-Roles": "super_admin"}, roles=["super_admin"]
    )
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"roles": ["super_admin", "developer"]},
        headers={"X-User-Roles": "super_admin"},
    )
    assert_err(response, "INVALID_USER", 422)


async def test_update_user_rejects_granting_super_admin_alongside_existing_role(
    user_client: AsyncClient,
) -> None:
    """Granting super_admin to a user that keeps another role in the same PATCH is rejected."""
    created = await _create_user(user_client, roles=["developer"])
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"roles": ["super_admin", "developer"]},
        headers={"X-User-Roles": "super_admin"},
    )
    assert_err(response, "INVALID_USER", 422)


# ---------- tenant isolation ----------


async def test_list_users_excludes_other_tenant_for_tenant_scoped_caller(
    user_client: AsyncClient,
) -> None:
    """A tenant-scoped caller's list never includes another tenant's users."""
    other_tenant = await _create_tenant(user_client, name="tenant-isolation-list")
    await _create_user(
        user_client,
        tenantId=other_tenant["id"],
        username="other-tenant-user",
        email="other@x.com",
    )
    await user_client.post("/api/v1/users", json=_CREATE_BODY)

    listed = assert_ok(
        await user_client.get("/api/v1/users", headers={"X-User-Roles": "admin"})
    )
    assert listed
    assert all(u["tenantId"] == DEFAULT_TEST_TENANT_ID for u in listed)


async def test_list_users_ignores_client_tenant_filter_for_tenant_scoped_caller(
    user_client: AsyncClient,
) -> None:
    """A caller-supplied ``tenantId`` filter can't widen a tenant-scoped caller's list."""
    other_tenant = await _create_tenant(user_client, name="tenant-isolation-list-q")
    await _create_user(
        user_client,
        tenantId=other_tenant["id"],
        username="other-tenant-user-q",
        email="other-q@x.com",
    )
    response = await user_client.get(
        "/api/v1/users",
        params={"q": f"tenantId:eq:{other_tenant['id']}"},
        headers={"X-User-Roles": "admin"},
    )
    assert assert_ok(response) == []


async def test_list_users_super_admin_excludes_other_tenant_regular_user(
    user_client: AsyncClient,
) -> None:
    """A super admin's list is scoped to their acting tenant for regular users."""
    other_tenant = await _create_tenant(user_client, name="tenant-isolation-list-sa")
    created = await _create_user(
        user_client,
        tenantId=other_tenant["id"],
        username="other-tenant-user-sa",
        email="other-sa@x.com",
    )
    listed = assert_ok(await user_client.get("/api/v1/users"))
    assert all(u["id"] != created["id"] for u in listed)


async def test_list_users_super_admin_sees_every_super_admin_regardless_of_tenant(
    user_client: AsyncClient,
) -> None:
    """A super admin's list always includes every other super_admin user."""
    other_super_admin = await _create_user(
        user_client,
        headers={"X-User-Roles": "super_admin"},
        username="other-super-admin",
        email="other-super-admin@x.com",
        roles=["super_admin"],
    )
    listed = assert_ok(await user_client.get("/api/v1/users"))
    assert any(u["id"] == other_super_admin["id"] for u in listed)


async def test_list_users_super_admin_switches_acting_tenant_via_header(
    user_client: AsyncClient,
) -> None:
    """Switching the acting tenant changes which regular users are visible,
    while a super admin stays visible regardless of the selection."""
    from dependencies.auth import TENANT_HEADER_NAME

    tenant_b = await _create_tenant(user_client, name="tenant-switch-users-b")
    user_a = await _create_user(
        user_client, username="user-in-a", email="user-in-a@x.com"
    )
    user_b = await _create_user(
        user_client,
        tenantId=tenant_b["id"],
        username="user-in-b",
        email="user-in-b@x.com",
    )
    other_super_admin = await _create_user(
        user_client,
        headers={"X-User-Roles": "super_admin"},
        username="switch-super-admin",
        email="switch-super-admin@x.com",
        roles=["super_admin"],
    )

    def _headers(tenant_id: str) -> dict[str, str]:
        return {"X-User-Tenant-Id": "", TENANT_HEADER_NAME: tenant_id}

    listed_a = assert_ok(
        await user_client.get("/api/v1/users", headers=_headers(DEFAULT_TEST_TENANT_ID))
    )
    ids_a = {u["id"] for u in listed_a}
    assert user_a["id"] in ids_a
    assert user_b["id"] not in ids_a
    assert other_super_admin["id"] in ids_a

    listed_b = assert_ok(
        await user_client.get("/api/v1/users", headers=_headers(tenant_b["id"]))
    )
    ids_b = {u["id"] for u in listed_b}
    assert user_b["id"] in ids_b
    assert user_a["id"] not in ids_b
    assert other_super_admin["id"] in ids_b


async def test_list_users_platform_scoped_super_admin_requires_tenant_header(
    user_client: AsyncClient,
) -> None:
    """A super admin with no acting tenant selected is forbidden, same as any
    other tenant-scoped route (see ``CurrentTenantIdDep``)."""
    response = await user_client.get("/api/v1/users", headers={"X-User-Tenant-Id": ""})
    assert_err(response, "FORBIDDEN", 403)


async def test_get_user_other_tenant_returns_404_for_tenant_scoped_caller(
    user_client: AsyncClient,
) -> None:
    other_tenant = await _create_tenant(user_client, name="tenant-isolation-get")
    created = await _create_user(
        user_client,
        tenantId=other_tenant["id"],
        username="other-tenant-user-get",
        email="other-get@x.com",
    )
    response = await user_client.get(
        f"/api/v1/users/{created['id']}", headers={"X-User-Roles": "admin"}
    )
    assert_err(response, "NOT_FOUND", 404)


async def test_get_user_platform_scoped_target_returns_404_for_tenant_scoped_caller(
    user_client: AsyncClient,
) -> None:
    """A tenant-scoped caller cannot view a platform-scoped user (e.g. a super_admin).

    Only a super_admin actor is exempt from the tenant boundary (see
    :func:`_assert_tenant_visible`); a plain admin gets 404, the same as any
    other cross-tenant reference, so existence is never leaked.
    """
    super_admin = await _create_user(user_client, roles=["super_admin"])
    response = await user_client.get(
        f"/api/v1/users/{super_admin['id']}", headers={"X-User-Roles": "admin"}
    )
    assert_err(response, "NOT_FOUND", 404)


async def test_get_user_other_tenant_succeeds_for_super_admin(
    user_client: AsyncClient,
) -> None:
    """A super admin can still fetch a user in any tenant (regression guard)."""
    other_tenant = await _create_tenant(user_client, name="tenant-isolation-get-sa")
    created = await _create_user(
        user_client,
        tenantId=other_tenant["id"],
        username="other-tenant-user-get-sa",
        email="other-get-sa@x.com",
    )
    response = await user_client.get(f"/api/v1/users/{created['id']}")
    assert assert_ok(response)["id"] == created["id"]


async def test_update_user_other_tenant_returns_404_for_tenant_scoped_admin(
    user_client: AsyncClient,
) -> None:
    other_tenant = await _create_tenant(user_client, name="tenant-isolation-update")
    created = await _create_user(
        user_client,
        tenantId=other_tenant["id"],
        username="other-tenant-user-update",
        email="other-update@x.com",
    )
    response = await user_client.patch(
        f"/api/v1/users/{created['id']}",
        json={"firstName": "Hacked"},
        headers={"X-User-Roles": "admin"},
    )
    assert_err(response, "NOT_FOUND", 404)


async def test_delete_user_other_tenant_returns_404_for_tenant_scoped_admin(
    user_client: AsyncClient,
) -> None:
    other_tenant = await _create_tenant(user_client, name="tenant-isolation-delete")
    created = await _create_user(
        user_client,
        tenantId=other_tenant["id"],
        username="other-tenant-user-delete",
        email="other-delete@x.com",
    )
    response = await user_client.delete(
        f"/api/v1/users/{created['id']}", headers={"X-User-Roles": "admin"}
    )
    assert_err(response, "NOT_FOUND", 404)
    # The target survives -- a super admin can still fetch it afterwards.
    fetched = assert_ok(await user_client.get(f"/api/v1/users/{created['id']}"))
    assert fetched["id"] == created["id"]


async def test_delete_super_admin_returns_404_for_tenant_scoped_admin(
    user_client: AsyncClient,
) -> None:
    """A plain admin deleting a super_admin user gets 404, not success.

    A super_admin target is invisible to a plain admin (see
    :func:`_assert_tenant_visible`), same as a cross-tenant target.
    """
    created = await _create_user(user_client, roles=["super_admin"])
    response = await user_client.delete(
        f"/api/v1/users/{created['id']}", headers={"X-User-Roles": "admin"}
    )
    assert_err(response, "NOT_FOUND", 404)
    # The target survives -- a super admin can still fetch it afterwards.
    fetched = assert_ok(await user_client.get(f"/api/v1/users/{created['id']}"))
    assert fetched["id"] == created["id"]


# ---------- resolve-names ----------


async def _resolve_names(
    user_client: AsyncClient, ids: list[str], headers: dict[str, str] | None = None
) -> dict[str, str]:
    """Resolve ``ids`` and return the response as an ``{id: displayName}`` map."""
    entries = assert_ok(
        await user_client.post(
            "/api/v1/users/resolve-names", json={"ids": ids}, headers=headers or {}
        )
    )
    return {entry["id"]: entry["displayName"] for entry in entries}


async def test_resolve_names_returns_display_name_for_same_tenant_user(
    user_client: AsyncClient,
) -> None:
    created = await _create_user(user_client)
    resolved = await _resolve_names(
        user_client, [created["id"]], headers={"X-User-Roles": "admin"}
    )
    assert resolved == {created["id"]: "Alice Smith"}


async def test_resolve_names_deduplicates_repeated_ids(
    user_client: AsyncClient,
) -> None:
    created = await _create_user(user_client)
    entries = assert_ok(
        await user_client.post(
            "/api/v1/users/resolve-names",
            json={"ids": [created["id"], created["id"], created["id"]]},
        )
    )
    assert len(entries) == 1


async def test_resolve_names_with_no_ids_returns_empty_list(
    user_client: AsyncClient,
) -> None:
    assert (
        assert_ok(
            await user_client.post("/api/v1/users/resolve-names", json={"ids": []})
        )
        == []
    )


async def test_resolve_names_omits_unknown_id(user_client: AsyncClient) -> None:
    """An id with no matching user is dropped rather than failing the batch."""
    created = await _create_user(user_client)
    resolved = await _resolve_names(user_client, ["ghost", created["id"]])
    assert resolved == {created["id"]: "Alice Smith"}


async def test_resolve_names_resolves_soft_deleted_user(
    user_client: AsyncClient,
) -> None:
    """A soft-deleted user still resolves, so the records they own keep a name.

    Unlike ``list``, which hides them -- see ``SqlUserRepository.get_many``.
    """
    owner = await _create_user(user_client)
    # Referencing the owner from another row forces DELETE down the
    # soft-delete path (the created_by FK is RESTRICT).
    await _create_user(
        user_client,
        headers={"X-User-Id": owner["id"]},
        username="referencing-user",
        email="referencing@x.com",
    )
    assert_ok(await user_client.delete(f"/api/v1/users/{owner['id']}"))

    resolved = await _resolve_names(user_client, [owner["id"]])
    assert resolved == {owner["id"]: "Alice Smith"}


async def test_resolve_names_omits_user_from_another_tenant(
    user_client: AsyncClient,
) -> None:
    """The tenant boundary of ``GET /users/{id}`` applies here too."""
    other_tenant = await _create_tenant(user_client, name="tenant-isolation-resolve")
    created = await _create_user(
        user_client,
        tenantId=other_tenant["id"],
        username="other-tenant-user-resolve",
        email="other-resolve@x.com",
    )
    resolved = await _resolve_names(
        user_client, [created["id"]], headers={"X-User-Roles": "admin"}
    )
    assert resolved == {}


async def test_resolve_names_masks_super_admin_for_tenant_scoped_caller(
    user_client: AsyncClient,
) -> None:
    """A super_admin is invisible to a plain admin, but not anonymous either."""
    super_admin = await _create_user(user_client, roles=["super_admin"])
    resolved = await _resolve_names(
        user_client, [super_admin["id"]], headers={"X-User-Roles": "admin"}
    )
    assert resolved == {super_admin["id"]: "Super Admin"}


async def test_resolve_names_masks_system_user_for_tenant_scoped_caller(
    user_client: AsyncClient,
) -> None:
    """The seeded system user owns bootstrap records, so it needs a label."""
    resolved = await _resolve_names(
        user_client, [SYSTEM_USER_ID], headers={"X-User-Roles": "admin"}
    )
    assert resolved == {SYSTEM_USER_ID: "System User"}


async def test_resolve_names_gives_super_admin_caller_the_real_names(
    user_client: AsyncClient,
) -> None:
    """A super admin is exempt from the boundary, so nothing is masked for them."""
    super_admin = await _create_user(user_client, roles=["super_admin"])
    resolved = await _resolve_names(user_client, [super_admin["id"], SYSTEM_USER_ID])
    assert resolved == {super_admin["id"]: "Alice Smith", SYSTEM_USER_ID: "System User"}


async def test_resolve_names_rejects_more_ids_than_the_limit(
    user_client: AsyncClient,
) -> None:
    from models.user import MAX_RESOLVE_NAME_IDS

    response = await user_client.post(
        "/api/v1/users/resolve-names",
        json={"ids": [f"id-{i}" for i in range(MAX_RESOLVE_NAME_IDS + 1)]},
    )
    assert_err(response, "VALIDATION_ERROR", 422)
