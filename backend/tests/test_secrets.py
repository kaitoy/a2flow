"""Integration tests for the Secret CRUD endpoints.

The central invariant: no response from any route ever contains an ``entries``
key or any value — neither the submitted plaintext nor the stored ciphertext.
Responses expose only the entry ``keys``.
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
from tests._seed import seed_tenant, seed_users
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
    await seed_tenant(eng)
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


_LOCAL_BODY = {
    "name": "github-token",
    "type": "local",
    "entries": {"token": "tok-123"},
}
_MULTI_BODY = {
    "name": "aws-credentials",
    "type": "local",
    "entries": {"AWS_ACCESS_KEY_ID": "AKIA1", "AWS_SECRET_ACCESS_KEY": "sk-1"},
}
_VAULT_BODY = {
    "name": "vault-token",
    "type": "vault",
    "vaultMount": "secret",
    "vaultPath": "myapp/github",
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


async def test_create_local_secret_response_has_keys_but_no_values(
    secrets_client: AsyncClient,
) -> None:
    body = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY), status=201
    )
    assert body["name"] == "github-token"
    assert body["type"] == "local"
    assert body["keys"] == ["token"]
    assert "entries" not in body
    assert "value" not in body


async def test_create_multi_entry_secret_lists_every_key_sorted(
    secrets_client: AsyncClient,
) -> None:
    body = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_MULTI_BODY), status=201
    )
    assert body["keys"] == ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
    assert "entries" not in body


async def test_create_vault_secret_response_has_reference_but_no_value(
    secrets_client: AsyncClient,
) -> None:
    body = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_VAULT_BODY), status=201
    )
    assert body["type"] == "vault"
    assert body["vaultMount"] == "secret"
    assert body["vaultPath"] == "myapp/github"
    assert body["keys"] == []
    assert "entries" not in body


async def test_create_multi_entry_secret_stores_each_value_encrypted(
    secrets_client: AsyncClient, mem_engine: AsyncEngine
) -> None:
    body = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_MULTI_BODY), status=201
    )
    stored = await _db_secret(mem_engine, body["id"])
    cipher = get_secret_cipher()
    assert stored.entries["AWS_ACCESS_KEY_ID"] != "AKIA1"
    assert cipher.decrypt(stored.entries["AWS_ACCESS_KEY_ID"]) == "AKIA1"
    assert cipher.decrypt(stored.entries["AWS_SECRET_ACCESS_KEY"]) == "sk-1"


async def test_create_local_secret_without_entries_returns_422(
    secrets_client: AsyncClient,
) -> None:
    response = await secrets_client.post(
        "/api/v1/secrets", json={"name": "x", "type": "local"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_local_secret_with_empty_entry_value_returns_422(
    secrets_client: AsyncClient,
) -> None:
    """The keep-existing sentinel is a PATCH-only affordance; POST rejects it."""
    response = await secrets_client.post(
        "/api/v1/secrets", json={**_LOCAL_BODY, "entries": {"token": ""}}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_local_secret_with_vault_fields_returns_422(
    secrets_client: AsyncClient,
) -> None:
    response = await secrets_client.post(
        "/api/v1/secrets", json={**_LOCAL_BODY, "vaultPath": "p"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_vault_secret_missing_path_returns_422(
    secrets_client: AsyncClient,
) -> None:
    body = {k: v for k, v in _VAULT_BODY.items() if k != "vaultPath"}
    response = await secrets_client.post("/api/v1/secrets", json=body)
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_vault_secret_with_entries_returns_422(
    secrets_client: AsyncClient,
) -> None:
    response = await secrets_client.post(
        "/api/v1/secrets", json={**_VAULT_BODY, "entries": {"token": "v"}}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_secret_rejects_non_slug_name(
    secrets_client: AsyncClient,
) -> None:
    response = await secrets_client.post(
        "/api/v1/secrets", json={**_LOCAL_BODY, "name": "has space"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_secret_rejects_non_slug_entry_key(
    secrets_client: AsyncClient,
) -> None:
    """A key with ``/`` would make ``${secret:NAME/KEY}`` ambiguous."""
    response = await secrets_client.post(
        "/api/v1/secrets", json={**_LOCAL_BODY, "entries": {"a/b": "v"}}
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
    assert all("entries" not in item for item in items)


async def test_get_secret_returns_keys_without_values(
    secrets_client: AsyncClient,
) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_MULTI_BODY), status=201
    )
    body = assert_ok(await secrets_client.get(f"/api/v1/secrets/{created['id']}"))
    assert body["name"] == "aws-credentials"
    assert body["keys"] == ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
    assert "entries" not in body


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
    assert "entries" not in body


async def test_update_entries_replaces_ciphertext(
    secrets_client: AsyncClient, mem_engine: AsyncEngine
) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY), status=201
    )
    before = (await _db_secret(mem_engine, created["id"])).entries["token"]
    assert_ok(
        await secrets_client.patch(
            f"/api/v1/secrets/{created['id']}", json={"entries": {"token": "tok-456"}}
        )
    )
    stored = await _db_secret(mem_engine, created["id"])
    assert stored.entries["token"] != before
    assert get_secret_cipher().decrypt(stored.entries["token"]) == "tok-456"


async def test_update_omitting_entries_keeps_the_stored_map(
    secrets_client: AsyncClient, mem_engine: AsyncEngine
) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_MULTI_BODY), status=201
    )
    before = dict((await _db_secret(mem_engine, created["id"])).entries)
    assert_ok(
        await secrets_client.patch(
            f"/api/v1/secrets/{created['id']}", json={"name": "renamed"}
        )
    )
    assert (await _db_secret(mem_engine, created["id"])).entries == before


async def test_update_entries_replaces_wholesale_dropping_missing_keys(
    secrets_client: AsyncClient, mem_engine: AsyncEngine
) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_MULTI_BODY), status=201
    )
    body = assert_ok(
        await secrets_client.patch(
            f"/api/v1/secrets/{created['id']}",
            json={"entries": {"AWS_ACCESS_KEY_ID": "AKIA2"}},
        )
    )
    assert body["keys"] == ["AWS_ACCESS_KEY_ID"]
    stored = await _db_secret(mem_engine, created["id"])
    assert "AWS_SECRET_ACCESS_KEY" not in stored.entries


async def test_update_empty_entry_value_keeps_the_stored_ciphertext(
    secrets_client: AsyncClient, mem_engine: AsyncEngine
) -> None:
    """Blank means "keep it" — the only way to preserve a value never sent back."""
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_MULTI_BODY), status=201
    )
    before = dict((await _db_secret(mem_engine, created["id"])).entries)
    assert_ok(
        await secrets_client.patch(
            f"/api/v1/secrets/{created['id']}",
            json={
                "entries": {"AWS_ACCESS_KEY_ID": "AKIA2", "AWS_SECRET_ACCESS_KEY": ""}
            },
        )
    )
    stored = await _db_secret(mem_engine, created["id"])
    cipher = get_secret_cipher()
    assert cipher.decrypt(stored.entries["AWS_ACCESS_KEY_ID"]) == "AKIA2"
    assert stored.entries["AWS_SECRET_ACCESS_KEY"] == before["AWS_SECRET_ACCESS_KEY"]


async def test_update_empty_value_for_a_new_key_returns_422(
    secrets_client: AsyncClient,
) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY), status=201
    )
    response = await secrets_client.patch(
        f"/api/v1/secrets/{created['id']}",
        json={"entries": {"token": "", "brand-new": ""}},
    )
    assert_err(response, code="INVALID_SECRET", status=422)


async def test_update_clearing_every_entry_returns_422(
    secrets_client: AsyncClient,
) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY), status=201
    )
    response = await secrets_client.patch(
        f"/api/v1/secrets/{created['id']}", json={"entries": {}}
    )
    assert_err(response, code="INVALID_SECRET", status=422)


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


async def test_update_vault_secret_with_entries_returns_422(
    secrets_client: AsyncClient,
) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_VAULT_BODY), status=201
    )
    response = await secrets_client.patch(
        f"/api/v1/secrets/{created['id']}", json={"entries": {"token": "v"}}
    )
    assert_err(response, code="INVALID_SECRET", status=422)


async def test_update_switch_local_to_vault_clears_entries(
    secrets_client: AsyncClient, mem_engine: AsyncEngine
) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY), status=201
    )
    body = assert_ok(
        await secrets_client.patch(
            f"/api/v1/secrets/{created['id']}",
            json={"type": "vault", "vaultMount": "secret", "vaultPath": "p"},
        )
    )
    assert body["type"] == "vault"
    assert body["keys"] == []
    assert (await _db_secret(mem_engine, created["id"])).entries == {}


async def test_update_switch_local_to_vault_missing_fields_returns_422(
    secrets_client: AsyncClient,
) -> None:
    created = assert_ok(
        await secrets_client.post("/api/v1/secrets", json=_LOCAL_BODY), status=201
    )
    response = await secrets_client.patch(
        f"/api/v1/secrets/{created['id']}", json={"type": "vault"}
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
            json={"type": "local", "entries": {"token": "tok-789"}},
        )
    )
    assert body["type"] == "local"
    assert body["vaultMount"] is None
    assert body["vaultPath"] is None
    assert body["keys"] == ["token"]
    stored = await _db_secret(mem_engine, created["id"])
    assert get_secret_cipher().decrypt(stored.entries["token"]) == "tok-789"


async def test_update_switch_vault_to_local_without_entries_returns_422(
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
