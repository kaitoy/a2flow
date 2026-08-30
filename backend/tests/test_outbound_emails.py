"""Tests for the admin-gated ``/outbound-emails`` List/Get/Delete API.

There is no Create or Update route (see :mod:`models.outbound_email`), so every
row here is inserted directly through :class:`repositories.outbound_email.SqlOutboundEmailRepository`
rather than through the API. Covers the split role gate (reads require ``admin``,
Delete requires ``super_admin``), tenant isolation, and the terminal-status rule
on delete.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from dependencies.auth import ALL_TENANTS_SENTINEL, TENANT_HEADER_NAME
from infrastructure.bootstrap import seed_system_user
from models.outbound_email import (
    OutboundEmail,
    OutboundEmailCreate,
    OutboundEmailStatus,
)
from models.user import SYSTEM_USER_ID
from repositories.outbound_email import SqlOutboundEmailRepository
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant
from tests.conftest import _install_auth_overrides

_PATH = "/api/v1/outbound-emails"

#: A second tenant used by the isolation tests.
OTHER_TENANT_ID = "tenant-other"

#: Headers selecting a plain (non-super-admin) admin.
ADMIN: dict[str, str] = {"X-User-Id": "alice", "X-User-Roles": "admin"}

#: Headers selecting a role-less user.
NOBODY: dict[str, str] = {"X-User-Id": "bob", "X-User-Roles": ""}


@pytest_asyncio.fixture()
async def outbound_email_env() -> AsyncGenerator[tuple[AsyncClient, AsyncEngine], None]:
    """Yield an API client (default caller: super_admin in the default tenant) plus the backing engine."""
    from infrastructure.database import get_session
    from main import app

    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(mem_engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(mem_engine) as session:
        await seed_system_user(session)
    await seed_tenant(mem_engine, DEFAULT_TEST_TENANT_ID)
    await seed_tenant(mem_engine, OTHER_TENANT_ID)

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
            yield ac, mem_engine
    finally:
        app.dependency_overrides.clear()
        await mem_engine.dispose()


async def _seed_email(
    engine: AsyncEngine,
    *,
    tenant_id: str = DEFAULT_TEST_TENANT_ID,
    status: OutboundEmailStatus = OutboundEmailStatus.pending,
) -> str:
    """Insert one OutboundEmail row directly (no Create endpoint exists) and return its id."""
    async with AsyncSession(engine) as session:
        repo = SqlOutboundEmailRepository(session, tenant_id=tenant_id)
        email = repo.stage(
            OutboundEmailCreate(
                to_email="recipient@example.com",
                subject="Approval requested",
                body="Please review.",
            ),
            user_id=SYSTEM_USER_ID,
        )
        email.status = status
        await session.commit()
        await session.refresh(email)
        return str(email.id)


async def _get_row(engine: AsyncEngine, email_id: str) -> OutboundEmail | None:
    """Return the row freshly read from the database, or None."""
    async with AsyncSession(engine) as session:
        return await session.get(OutboundEmail, email_id)


# ---------- authorization ----------


async def test_super_admin_can_list(
    outbound_email_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = outbound_email_env
    await _seed_email(engine)
    body = assert_ok(await client.get(_PATH))
    assert len(body) == 1


async def test_super_admin_can_get(
    outbound_email_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = outbound_email_env
    email_id = await _seed_email(engine)
    body = assert_ok(await client.get(f"{_PATH}/{email_id}"))
    assert body["id"] == email_id
    assert body["toEmail"] == "recipient@example.com"
    assert body["status"] == "pending"
    assert body["tenantId"] == DEFAULT_TEST_TENANT_ID


@pytest.mark.parametrize(
    "status", [OutboundEmailStatus.sent, OutboundEmailStatus.failed]
)
async def test_super_admin_can_delete_a_terminal_row(
    outbound_email_env: tuple[AsyncClient, AsyncEngine], status: OutboundEmailStatus
) -> None:
    client, engine = outbound_email_env
    email_id = await _seed_email(engine, status=status)
    assert assert_ok(await client.delete(f"{_PATH}/{email_id}")) is None
    assert await _get_row(engine, email_id) is None


async def test_plain_admin_can_list(
    outbound_email_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Reads sit at ``admin``: the queue is part of the audit trail a tenant's
    administrators follow, unlike Delete, which destroys that evidence."""
    client, engine = outbound_email_env
    email_id = await _seed_email(engine)
    rows = assert_ok(await client.get(_PATH, headers=ADMIN))
    assert [row["id"] for row in rows] == [email_id]


async def test_plain_admin_can_get(
    outbound_email_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = outbound_email_env
    email_id = await _seed_email(engine)
    body = assert_ok(await client.get(f"{_PATH}/{email_id}", headers=ADMIN))
    assert body["id"] == email_id


async def test_plain_admin_is_forbidden_from_delete(
    outbound_email_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = outbound_email_env
    email_id = await _seed_email(engine, status=OutboundEmailStatus.sent)
    assert_err(
        await client.delete(f"{_PATH}/{email_id}", headers=ADMIN),
        code="FORBIDDEN",
        status=403,
    )


async def test_role_less_user_is_forbidden(
    outbound_email_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = outbound_email_env
    assert_err(await client.get(_PATH, headers=NOBODY), code="FORBIDDEN", status=403)


async def test_list_is_forbidden_for_a_platform_scoped_caller_without_a_tenant_header(
    outbound_email_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Unlike system-settings, this router is tenant-scoped: a tenant-less
    super_admin must select a tenant via `X-Tenant-Id`, same as any other
    tenant-scoped resource."""
    client, _ = outbound_email_env
    assert_err(
        await client.get(_PATH, headers={"X-User-Tenant-Id": ""}),
        code="FORBIDDEN",
        status=403,
    )


# ---------- tenant isolation ----------


async def test_list_does_not_mix_tenants(
    outbound_email_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = outbound_email_env
    await _seed_email(engine, tenant_id=DEFAULT_TEST_TENANT_ID)
    await _seed_email(engine, tenant_id=OTHER_TENANT_ID)
    body = assert_ok(await client.get(_PATH))
    assert len(body) == 1


async def test_get_of_another_tenants_row_is_not_found(
    outbound_email_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = outbound_email_env
    email_id = await _seed_email(engine, tenant_id=OTHER_TENANT_ID)
    assert_err(await client.get(f"{_PATH}/{email_id}"), code="NOT_FOUND", status=404)


async def test_delete_of_another_tenants_row_is_not_found(
    outbound_email_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, engine = outbound_email_env
    email_id = await _seed_email(
        engine, tenant_id=OTHER_TENANT_ID, status=OutboundEmailStatus.sent
    )
    assert_err(await client.delete(f"{_PATH}/{email_id}"), code="NOT_FOUND", status=404)
    assert await _get_row(engine, email_id) is not None


# ---------- read ----------


async def test_get_unknown_row_returns_404(
    outbound_email_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = outbound_email_env
    assert_err(
        await client.get(f"{_PATH}/does-not-exist"), code="NOT_FOUND", status=404
    )


# ---------- delete ----------


@pytest.mark.parametrize(
    "status", [OutboundEmailStatus.pending, OutboundEmailStatus.sending]
)
async def test_delete_rejects_a_non_terminal_row(
    outbound_email_env: tuple[AsyncClient, AsyncEngine], status: OutboundEmailStatus
) -> None:
    client, engine = outbound_email_env
    email_id = await _seed_email(engine, status=status)
    err = assert_err(
        await client.delete(f"{_PATH}/{email_id}"),
        code="OUTBOUND_EMAIL_NOT_DELETABLE",
        status=409,
    )
    assert err["details"] == {"outboundEmailId": email_id, "status": status.value}
    assert await _get_row(engine, email_id) is not None


async def test_delete_unknown_row_returns_404(
    outbound_email_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = outbound_email_env
    assert_err(
        await client.delete(f"{_PATH}/does-not-exist"), code="NOT_FOUND", status=404
    )


# ---------- all-tenants read mode ----------


def _all_tenants_headers() -> dict[str, str]:
    return {"X-User-Tenant-Id": "", TENANT_HEADER_NAME: ALL_TENANTS_SENTINEL}


async def test_all_tenants_list_spans_every_tenant(
    outbound_email_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A platform-scoped super_admin selecting "all tenants" sees every tenant's rows."""
    client, engine = outbound_email_env
    email_a = await _seed_email(engine, tenant_id=DEFAULT_TEST_TENANT_ID)
    email_b = await _seed_email(engine, tenant_id=OTHER_TENANT_ID)

    body = assert_ok(await client.get(_PATH, headers=_all_tenants_headers()))
    ids = {row["id"] for row in body}
    assert email_a in ids
    assert email_b in ids


async def test_all_tenants_get_reaches_any_tenants_row(
    outbound_email_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Fetching a single row by id works across tenants in "all tenants" mode."""
    client, engine = outbound_email_env
    email_id = await _seed_email(engine, tenant_id=OTHER_TENANT_ID)

    body = assert_ok(
        await client.get(f"{_PATH}/{email_id}", headers=_all_tenants_headers())
    )
    assert body["id"] == email_id


async def test_all_tenants_rejects_delete(
    outbound_email_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Delete stays on the strict resolver, so "all tenants" 403s it like any write."""
    client, engine = outbound_email_env
    email_id = await _seed_email(
        engine, tenant_id=OTHER_TENANT_ID, status=OutboundEmailStatus.sent
    )
    assert_err(
        await client.delete(f"{_PATH}/{email_id}", headers=_all_tenants_headers()),
        code="FORBIDDEN",
        status=403,
    )
    assert await _get_row(engine, email_id) is not None
