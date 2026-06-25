"""Tests for the custom user-avatar endpoints (upload, fetch, delete)."""

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
async def avatar_client() -> AsyncGenerator[AsyncClient, None]:
    from infrastructure.database import get_session
    from main import app
    from models.user import User as _User  # noqa: F401 — registers model
    from models.user_avatar import (
        UserAvatar as _UserAvatar,  # noqa: F401 — registers model
    )

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

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-image-payload"


async def _create_user(client: AsyncClient) -> str:
    """Create a user and return its id."""
    created = assert_ok(
        await client.post("/api/v1/users", json=_CREATE_BODY), status=201
    )
    return str(created["id"])


# ---------- read marker ----------


async def test_new_user_has_null_avatar_updated_at(avatar_client: AsyncClient) -> None:
    created = assert_ok(
        await avatar_client.post("/api/v1/users", json=_CREATE_BODY), status=201
    )
    assert created["avatarUpdatedAt"] is None


# ---------- upload ----------


async def test_upload_avatar_returns_user_with_marker(
    avatar_client: AsyncClient,
) -> None:
    user_id = await _create_user(avatar_client)
    response = await avatar_client.put(
        f"/api/v1/users/{user_id}/avatar",
        files={"file": ("avatar.png", _PNG_BYTES, "image/png")},
    )
    body = assert_ok(response)
    assert body["avatarUpdatedAt"] is not None


async def test_uploaded_avatar_is_served_with_content_type(
    avatar_client: AsyncClient,
) -> None:
    user_id = await _create_user(avatar_client)
    await avatar_client.put(
        f"/api/v1/users/{user_id}/avatar",
        files={"file": ("avatar.png", _PNG_BYTES, "image/png")},
    )
    response = await avatar_client.get(f"/api/v1/users/{user_id}/avatar")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == _PNG_BYTES


async def test_upload_avatar_replaces_existing(avatar_client: AsyncClient) -> None:
    user_id = await _create_user(avatar_client)
    await avatar_client.put(
        f"/api/v1/users/{user_id}/avatar",
        files={"file": ("a.png", _PNG_BYTES, "image/png")},
    )
    new_bytes = b"GIF89a-second-image"
    await avatar_client.put(
        f"/api/v1/users/{user_id}/avatar",
        files={"file": ("a.gif", new_bytes, "image/gif")},
    )
    response = await avatar_client.get(f"/api/v1/users/{user_id}/avatar")
    assert response.content == new_bytes
    assert response.headers["content-type"] == "image/gif"


async def test_upload_avatar_rejects_unsupported_type(
    avatar_client: AsyncClient,
) -> None:
    user_id = await _create_user(avatar_client)
    response = await avatar_client.put(
        f"/api/v1/users/{user_id}/avatar",
        files={"file": ("a.txt", b"not an image", "text/plain")},
    )
    assert_err(response, code="INVALID_AVATAR", status=422)


async def test_upload_avatar_rejects_oversized_image(
    avatar_client: AsyncClient,
) -> None:
    user_id = await _create_user(avatar_client)
    oversized = b"x" * (2 * 1024 * 1024 + 1)
    response = await avatar_client.put(
        f"/api/v1/users/{user_id}/avatar",
        files={"file": ("big.png", oversized, "image/png")},
    )
    assert_err(response, code="INVALID_AVATAR", status=422)


async def test_upload_avatar_rejects_empty_file(avatar_client: AsyncClient) -> None:
    user_id = await _create_user(avatar_client)
    response = await avatar_client.put(
        f"/api/v1/users/{user_id}/avatar",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert_err(response, code="INVALID_AVATAR", status=422)


async def test_upload_avatar_unknown_user_returns_422(
    avatar_client: AsyncClient,
) -> None:
    response = await avatar_client.put(
        "/api/v1/users/nonexistent/avatar",
        files={"file": ("a.png", _PNG_BYTES, "image/png")},
    )
    assert_err(response, code="FOREIGN_KEY_VIOLATION", status=422)


# ---------- fetch ----------


async def test_get_avatar_without_upload_returns_404(
    avatar_client: AsyncClient,
) -> None:
    user_id = await _create_user(avatar_client)
    response = await avatar_client.get(f"/api/v1/users/{user_id}/avatar")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- delete ----------


async def test_delete_avatar_clears_marker(avatar_client: AsyncClient) -> None:
    user_id = await _create_user(avatar_client)
    await avatar_client.put(
        f"/api/v1/users/{user_id}/avatar",
        files={"file": ("a.png", _PNG_BYTES, "image/png")},
    )
    body = assert_ok(await avatar_client.delete(f"/api/v1/users/{user_id}/avatar"))
    assert body["avatarUpdatedAt"] is None
    assert_err(
        await avatar_client.get(f"/api/v1/users/{user_id}/avatar"),
        code="NOT_FOUND",
        status=404,
    )


async def test_delete_avatar_without_upload_returns_404(
    avatar_client: AsyncClient,
) -> None:
    user_id = await _create_user(avatar_client)
    response = await avatar_client.delete(f"/api/v1/users/{user_id}/avatar")
    assert_err(response, code="NOT_FOUND", status=404)
