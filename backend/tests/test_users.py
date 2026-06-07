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


@pytest_asyncio.fixture()
async def user_client() -> AsyncGenerator[AsyncClient, None]:
    from infrastructure.database import get_session
    from main import app
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


async def test_update_user_duplicate_username_returns_409(
    user_client: AsyncClient,
) -> None:
    await user_client.post("/api/v1/users", json=_CREATE_BODY)
    other = assert_ok(
        await user_client.post(
            "/api/v1/users",
            json={**_CREATE_BODY, "username": "bob", "email": "bob@x.com"},
        ),
        status=201,
    )
    response = await user_client.patch(
        f"/api/v1/users/{other['id']}", json={"username": "alice"}
    )
    assert_err(response, code="CONFLICT_UNIQUE", status=409)


async def test_update_user_unknown_id_returns_404(user_client: AsyncClient) -> None:
    response = await user_client.patch(
        "/api/v1/users/nonexistent", json={"firstName": "X"}
    )
    assert_err(response, code="NOT_FOUND", status=404)


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
