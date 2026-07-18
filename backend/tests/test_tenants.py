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
async def tenant_client() -> AsyncGenerator[AsyncClient, None]:
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


_CREATE_BODY = {"name": "Acme Corp", "slug": "acme-corp"}


# ---------- create ----------


async def test_create_tenant_returns_201(tenant_client: AsyncClient) -> None:
    response = await tenant_client.post("/api/v1/tenants", json=_CREATE_BODY)
    assert response.status_code == 201


async def test_create_tenant_response_has_correct_fields(
    tenant_client: AsyncClient,
) -> None:
    body = assert_ok(
        await tenant_client.post("/api/v1/tenants", json=_CREATE_BODY), status=201
    )
    assert body["name"] == "Acme Corp"
    assert body["slug"] == "acme-corp"
    assert body["enabled"] is True


async def test_create_tenant_explicit_enabled_false_is_reflected(
    tenant_client: AsyncClient,
) -> None:
    body = assert_ok(
        await tenant_client.post(
            "/api/v1/tenants", json={**_CREATE_BODY, "enabled": False}
        ),
        status=201,
    )
    assert body["enabled"] is False


async def test_create_tenant_missing_name_returns_422(
    tenant_client: AsyncClient,
) -> None:
    body = {k: v for k, v in _CREATE_BODY.items() if k != "name"}
    response = await tenant_client.post("/api/v1/tenants", json=body)
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_tenant_rejects_uppercase_slug(
    tenant_client: AsyncClient,
) -> None:
    response = await tenant_client.post(
        "/api/v1/tenants", json={**_CREATE_BODY, "slug": "Acme-Corp"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_tenant_duplicate_name_returns_409(
    tenant_client: AsyncClient,
) -> None:
    await tenant_client.post("/api/v1/tenants", json=_CREATE_BODY)
    response = await tenant_client.post(
        "/api/v1/tenants", json={**_CREATE_BODY, "slug": "acme-corp-2"}
    )
    assert_err(response, code="CONFLICT_UNIQUE", status=409)


async def test_create_tenant_duplicate_slug_returns_409(
    tenant_client: AsyncClient,
) -> None:
    await tenant_client.post("/api/v1/tenants", json=_CREATE_BODY)
    response = await tenant_client.post(
        "/api/v1/tenants", json={**_CREATE_BODY, "name": "Acme Corp 2"}
    )
    assert_err(response, code="CONFLICT_UNIQUE", status=409)


async def test_non_super_admin_cannot_create_tenant(
    tenant_client: AsyncClient,
) -> None:
    response = await tenant_client.post(
        "/api/v1/tenants", json=_CREATE_BODY, headers={"X-User-Roles": "admin"}
    )
    assert_err(response, code="FORBIDDEN", status=403)


# ---------- list ----------


async def test_list_tenants_empty_initially(tenant_client: AsyncClient) -> None:
    response = await tenant_client.get("/api/v1/tenants")
    assert assert_ok(response) == []


async def test_list_tenants_returns_created_tenant(tenant_client: AsyncClient) -> None:
    await tenant_client.post("/api/v1/tenants", json=_CREATE_BODY)
    response = await tenant_client.get("/api/v1/tenants")
    assert len(assert_ok(response)) == 1


# ---------- get ----------


async def test_get_tenant_returns_correct_data(tenant_client: AsyncClient) -> None:
    created = assert_ok(
        await tenant_client.post("/api/v1/tenants", json=_CREATE_BODY), status=201
    )
    response = await tenant_client.get(f"/api/v1/tenants/{created['id']}")
    body = assert_ok(response)
    assert body["name"] == "Acme Corp"


async def test_get_tenant_unknown_id_returns_404(tenant_client: AsyncClient) -> None:
    response = await tenant_client.get("/api/v1/tenants/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- patch ----------


async def test_update_tenant_partial_update_leaves_other_fields_unchanged(
    tenant_client: AsyncClient,
) -> None:
    created = assert_ok(
        await tenant_client.post("/api/v1/tenants", json=_CREATE_BODY), status=201
    )
    response = await tenant_client.patch(
        f"/api/v1/tenants/{created['id']}", json={"enabled": False}
    )
    body = assert_ok(response)
    assert body["enabled"] is False
    assert body["name"] == "Acme Corp"
    assert body["slug"] == "acme-corp"


async def test_update_tenant_unknown_id_returns_404(tenant_client: AsyncClient) -> None:
    response = await tenant_client.patch(
        "/api/v1/tenants/nonexistent", json={"enabled": False}
    )
    assert_err(response, code="NOT_FOUND", status=404)


async def test_update_tenant_duplicate_slug_returns_409(
    tenant_client: AsyncClient,
) -> None:
    await tenant_client.post("/api/v1/tenants", json=_CREATE_BODY)
    other = assert_ok(
        await tenant_client.post(
            "/api/v1/tenants", json={"name": "Other", "slug": "other"}
        ),
        status=201,
    )
    response = await tenant_client.patch(
        f"/api/v1/tenants/{other['id']}", json={"slug": "acme-corp"}
    )
    assert_err(response, code="CONFLICT_UNIQUE", status=409)


async def test_non_super_admin_cannot_update_tenant(
    tenant_client: AsyncClient,
) -> None:
    created = assert_ok(
        await tenant_client.post("/api/v1/tenants", json=_CREATE_BODY), status=201
    )
    response = await tenant_client.patch(
        f"/api/v1/tenants/{created['id']}",
        json={"enabled": False},
        headers={"X-User-Roles": "admin"},
    )
    assert_err(response, code="FORBIDDEN", status=403)


# ---------- delete ----------


async def test_delete_tenant_returns_200(tenant_client: AsyncClient) -> None:
    created = assert_ok(
        await tenant_client.post("/api/v1/tenants", json=_CREATE_BODY), status=201
    )
    response = await tenant_client.delete(f"/api/v1/tenants/{created['id']}")
    assert assert_ok(response, status=200) is None


async def test_delete_tenant_removes_from_list(tenant_client: AsyncClient) -> None:
    created = assert_ok(
        await tenant_client.post("/api/v1/tenants", json=_CREATE_BODY), status=201
    )
    await tenant_client.delete(f"/api/v1/tenants/{created['id']}")
    response = await tenant_client.get("/api/v1/tenants")
    assert assert_ok(response) == []


async def test_delete_tenant_unknown_id_returns_404(tenant_client: AsyncClient) -> None:
    response = await tenant_client.delete("/api/v1/tenants/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


async def test_delete_tenant_with_assigned_user_returns_409(
    tenant_client: AsyncClient,
) -> None:
    created = assert_ok(
        await tenant_client.post("/api/v1/tenants", json=_CREATE_BODY), status=201
    )
    await tenant_client.post(
        "/api/v1/users",
        json={
            "username": "alice",
            "firstName": "Alice",
            "lastName": "Smith",
            "password": "secret123abc",
            "email": "alice@example.com",
            "tenantId": created["id"],
        },
    )
    response = await tenant_client.delete(f"/api/v1/tenants/{created['id']}")
    assert_err(response, code="CONFLICT_REFERENCED", status=409)


async def test_non_super_admin_cannot_delete_tenant(
    tenant_client: AsyncClient,
) -> None:
    created = assert_ok(
        await tenant_client.post("/api/v1/tenants", json=_CREATE_BODY), status=201
    )
    response = await tenant_client.delete(
        f"/api/v1/tenants/{created['id']}", headers={"X-User-Roles": "admin"}
    )
    assert_err(response, code="FORBIDDEN", status=403)
