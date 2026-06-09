"""Tests for the notifications API (``GET``/``PATCH /api/v1/notifications``).

The endpoints are scoped to the authenticated user (the test auth override reads
``X-User-Id``), so these tests focus on per-user isolation, the ``unread_only``
filter, and the mark-read flow including the cross-user 404 guard.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from models.notification import Notification, NotificationType
from tests._envelope import assert_err, assert_ok
from tests._seed import seed_users

# Import the conftest auth-override installer indirectly by reusing its behaviour
# through the public app dependency overrides set up below.
from tests.conftest import _install_auth_overrides


@pytest_asyncio.fixture()
async def notif_env() -> AsyncGenerator[tuple[AsyncClient, AsyncEngine], None]:
    """Yield an API client and the engine backing it, with users seeded.

    Exposing the engine lets each test insert Notification rows directly before
    exercising the endpoints.
    """
    from infrastructure.database import get_session
    from main import app

    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(mem_engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await seed_users(mem_engine)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    _install_auth_overrides(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac, mem_engine
    finally:
        app.dependency_overrides.clear()
        await mem_engine.dispose()


async def _insert_notification(
    eng: AsyncEngine,
    *,
    user_id: str,
    title: str = "Hello",
    read: bool = False,
    notification_type: NotificationType = NotificationType.approval_request,
) -> str:
    """Insert a Notification addressed to ``user_id`` and return its id."""
    async with AsyncSession(eng) as db:
        notification = Notification(
            user_id=user_id,
            type=notification_type,
            title=title,
            read=read,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(notification)
        await db.commit()
        await db.refresh(notification)
        return notification.id


async def test_list_returns_only_callers_notifications(
    notif_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = notif_env
    await _insert_notification(eng, user_id="alice", title="For Alice")
    await _insert_notification(eng, user_id="bob", title="For Bob")

    res = await client.get("/api/v1/notifications", headers={"X-User-Id": "alice"})
    data = assert_ok(res)
    assert [n["title"] for n in data] == ["For Alice"]


async def test_list_unread_only_filter(
    notif_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = notif_env
    await _insert_notification(eng, user_id="alice", title="Read one", read=True)
    await _insert_notification(eng, user_id="alice", title="Unread one", read=False)

    res = await client.get(
        "/api/v1/notifications",
        params={"unread_only": "true"},
        headers={"X-User-Id": "alice"},
    )
    data = assert_ok(res)
    assert [n["title"] for n in data] == ["Unread one"]


async def test_mark_notification_read(
    notif_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = notif_env
    notif_id = await _insert_notification(eng, user_id="alice", read=False)

    res = await client.patch(
        f"/api/v1/notifications/{notif_id}", headers={"X-User-Id": "alice"}
    )
    data = assert_ok(res)
    assert data["read"] is True


async def test_mark_other_users_notification_is_404(
    notif_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = notif_env
    notif_id = await _insert_notification(eng, user_id="bob")

    res = await client.patch(
        f"/api/v1/notifications/{notif_id}", headers={"X-User-Id": "alice"}
    )
    assert_err(res, "NOT_FOUND", 404)
