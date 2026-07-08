"""Integration tests for the Secret CRUD endpoints.

The central invariant: no response from any route ever contains a ``value``
key — neither the submitted plaintext nor the stored ciphertext.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.secret_cipher import get_secret_cipher
from models.secret import Secret
from models.user import SYSTEM_USER_ID
from tests._envelope import assert_err, assert_ok
from tests._seed import seed_users
from tests.conftest import _install_auth_overrides


@pytest_asyncio.fixture()
async def mem_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Yield an isolated in-memory engine with the schema created and users seeded."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(eng.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await seed_users(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture()
async def secrets_client(
    mem_engine: AsyncEngine,
) -> AsyncGenerator[AsyncClient, None]:
    from infrastructure.database import get_session
    from main import app

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


_LOCAL_BODY = {"name": "github-token", "type": "local", "value": "tok-123"}
_VAULT_BODY = {
    "name": "vault-token",
    "type": "vault",
    "vaultMount": "secret",
    "vaultPath": "myapp/github",
    "vaultKey": "token",
}


async def _db_secret(mem_engine: AsyncEngine, secret_id: str) -> Secret:
    """Fetch the raw Secret row for ciphertext assertions."""
    async with AsyncSession(mem_engine) as db:
        secret = await db.get(Secret, secret_id)
        assert secret is not None
        return secret


# ---------- create ----------


async def test_create_local_secret_returns_201(secrets_client: AsyncClient) -> None:
    response = await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY)
    assert response.status_code == 201


async def test_create_local_secret_response_has_no_value(
    secrets_client: AsyncClient,
) -> None:
    body = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY), status=201
    )
    assert body["name"] == "github-token"
    assert body["type"] == "local"
    assert "value" not in body


async def test_create_vault_secret_response_has_reference_but_no_value(
    secrets_client: AsyncClient,
) -> None:
    body = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_VAULT_BODY), status=201
    )
    assert body["type"] == "vault"
    assert body["vaultMount"] == "secret"
    assert body["vaultPath"] == "myapp/github"
    assert body["vaultKey"] == "token"
    assert "value" not in body


async def test_create_local_secret_stores_ciphertext(
    secrets_client: AsyncClient, mem_engine: AsyncEngine
) -> None:
    body = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY), status=201
    )
    stored = await _db_secret(mem_engine, body["id"])
    assert stored.value is not None
    assert stored.value != "tok-123"
    assert get_secret_cipher().decrypt(stored.value) == "tok-123"


async def test_create_local_secret_without_value_returns_422(
    secrets_client: AsyncClient,
) -> None:
    response = await secrets_client.post(
        "/api/v1/secrets", json={"name": "x", "type": "local"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_local_secret_with_vault_fields_returns_422(
    secrets_client: AsyncClient,
) -> None:
    response = await secrets_client.post(
        "/api/v1/secrets", json={**_LOCAL_BODY, "vaultPath": "p"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_vault_secret_missing_key_returns_422(
    secrets_client: AsyncClient,
) -> None:
    body = {k: v for k, v in _VAULT_BODY.items() if k != "vaultKey"}
    response = await secrets_client.post("/api/v1/secrets", json=body)
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_vault_secret_with_value_returns_422(
    secrets_client: AsyncClient,
) -> None:
    response = await secrets_client.post(
        "/api/v1/secrets", json={**_VAULT_BODY, "value": "v"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_secret_rejects_non_slug_name(
    secrets_client: AsyncClient,
) -> None:
    response = await secrets_client.post(
        "/api/v1/secrets", json={**_LOCAL_BODY, "name": "has space"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_secret_duplicate_name_returns_409(
    secrets_client: AsyncClient,
) -> None:
    await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY)
    response = await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY)
    assert_err(response, code="CONFLICT_UNIQUE", status=409)


# ---------- list / get ----------


async def test_list_secrets_empty_initially(secrets_client: AsyncClient) -> None:
    response = await secrets_client.get("/api/v1/secrets")
    assert assert_ok(response) == []


async def test_list_secrets_returns_created_without_values(
    secrets_client: AsyncClient,
) -> None:
    await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY)
    await secrets_client.post("/api/v1/secrets", json=_VAULT_BODY)
    items = assert_ok(await secrets_client.get("/api/v1/secrets"))
    assert len(items) == 2
    assert all("value" not in item for item in items)


async def test_get_secret_returns_data_without_value(
    secrets_client: AsyncClient,
) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY), status=201
    )
    body = assert_ok(await secrets_client.get(f"/api/v1/secrets/{created['id']}"))
    assert body["name"] == "github-token"
    assert "value" not in body


async def test_get_secret_unknown_id_returns_404(secrets_client: AsyncClient) -> None:
    response = await secrets_client.get("/api/v1/secrets/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- patch ----------


async def test_update_secret_rename(secrets_client: AsyncClient) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY), status=201
    )
    body = assert_ok(
        await secrets_client.patch(
            f"/api/v1/secrets/{created['id']}", json={"name": "renamed"}
        )
    )
    assert body["name"] == "renamed"
    assert "value" not in body


async def test_update_secret_value_replaces_ciphertext(
    secrets_client: AsyncClient, mem_engine: AsyncEngine
) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY), status=201
    )
    before = (await _db_secret(mem_engine, created["id"])).value
    assert_ok(
        await secrets_client.patch(
            f"/api/v1/secrets/{created['id']}", json={"value": "tok-456"}
        )
    )
    stored = await _db_secret(mem_engine, created["id"])
    assert stored.value != before
    assert stored.value is not None
    assert get_secret_cipher().decrypt(stored.value) == "tok-456"


async def test_update_secret_omitting_value_keeps_ciphertext(
    secrets_client: AsyncClient, mem_engine: AsyncEngine
) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY), status=201
    )
    before = (await _db_secret(mem_engine, created["id"])).value
    assert_ok(
        await secrets_client.patch(
            f"/api/v1/secrets/{created['id']}", json={"name": "renamed"}
        )
    )
    assert (await _db_secret(mem_engine, created["id"])).value == before


async def test_update_local_secret_with_vault_fields_returns_422(
    secrets_client: AsyncClient,
) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY), status=201
    )
    response = await secrets_client.patch(
        f"/api/v1/secrets/{created['id']}", json={"vaultPath": "p"}
    )
    assert_err(response, code="INVALID_SECRET", status=422)


async def test_update_vault_secret_with_value_returns_422(
    secrets_client: AsyncClient,
) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_VAULT_BODY), status=201
    )
    response = await secrets_client.patch(
        f"/api/v1/secrets/{created['id']}", json={"value": "v"}
    )
    assert_err(response, code="INVALID_SECRET", status=422)


async def test_update_switch_local_to_vault_clears_value(
    secrets_client: AsyncClient, mem_engine: AsyncEngine
) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY), status=201
    )
    body = assert_ok(
        await secrets_client.patch(
            f"/api/v1/secrets/{created['id']}",
            json={
                "type": "vault",
                "vaultMount": "secret",
                "vaultPath": "p",
                "vaultKey": "k",
            },
        )
    )
    assert body["type"] == "vault"
    assert (await _db_secret(mem_engine, created["id"])).value is None


async def test_update_switch_local_to_vault_missing_fields_returns_422(
    secrets_client: AsyncClient,
) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY), status=201
    )
    response = await secrets_client.patch(
        f"/api/v1/secrets/{created['id']}",
        json={"type": "vault", "vaultMount": "secret"},
    )
    assert_err(response, code="INVALID_SECRET", status=422)


async def test_update_switch_vault_to_local_clears_vault_fields(
    secrets_client: AsyncClient, mem_engine: AsyncEngine
) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_VAULT_BODY), status=201
    )
    body = assert_ok(
        await secrets_client.patch(
            f"/api/v1/secrets/{created['id']}",
            json={"type": "local", "value": "tok-789"},
        )
    )
    assert body["type"] == "local"
    assert body["vaultMount"] is None
    assert body["vaultPath"] is None
    assert body["vaultKey"] is None
    stored = await _db_secret(mem_engine, created["id"])
    assert stored.value is not None
    assert get_secret_cipher().decrypt(stored.value) == "tok-789"


async def test_update_switch_vault_to_local_without_value_returns_422(
    secrets_client: AsyncClient,
) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_VAULT_BODY), status=201
    )
    response = await secrets_client.patch(
        f"/api/v1/secrets/{created['id']}", json={"type": "local"}
    )
    assert_err(response, code="INVALID_SECRET", status=422)


async def test_update_secret_unknown_id_returns_404(
    secrets_client: AsyncClient,
) -> None:
    response = await secrets_client.patch(
        "/api/v1/secrets/nonexistent", json={"name": "x"}
    )
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- delete ----------


async def test_delete_secret_returns_200(secrets_client: AsyncClient) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY), status=201
    )
    response = await secrets_client.delete(f"/api/v1/secrets/{created['id']}")
    assert assert_ok(response, status=200) is None


async def test_delete_secret_unknown_id_returns_404(
    secrets_client: AsyncClient,
) -> None:
    response = await secrets_client.delete("/api/v1/secrets/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)
