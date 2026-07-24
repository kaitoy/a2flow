"""Tests for the impersonation feature.

Covers the eligibility rules and audit trail at the service layer, and the
request-header override mechanism (including the two correctness issues its
design deliberately guards against -- see ``dependencies/auth.py``'s module
docstring) end to end through the real HTTP/cookie/CSRF stack.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from dependencies.auth import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    IMPERSONATE_HEADER_NAME,
)
from infrastructure.password import hash_password
from models.impersonation_event import ImpersonationEvent
from models.user import SYSTEM_USER_ID, Role, User
from repositories.exceptions import ForbiddenError, NotFoundError
from repositories.impersonation_event import SqlImpersonationEventRepository
from repositories.user import SqlUserRepository
from services.impersonation import ImpersonationService
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users
from tests.conftest import AUTH_PASSWORD

TENANT_A = DEFAULT_TEST_TENANT_ID
TENANT_B = "tenant-other"


async def _seed_impersonation_cast(engine: Any) -> None:
    """Seed a small cast of users spanning roles, tenants, and edge-case states.

    ``admin-a`` / ``dev-a`` are the primary actor/target pair in tenant A;
    ``admin-a2`` is a second tenant-A admin (a same-tenant, admin-holding
    target); ``admin-b`` / ``dev-b`` live in tenant B (cross-tenant targets
    for a tenant-A actor); ``root`` / ``root2`` are platform-scoped
    super_admins (``root2`` a same-scope, super_admin-holding target).
    """
    await seed_users(engine, ids=())
    await seed_tenant(engine, TENANT_B)
    password_hash = hash_password(AUTH_PASSWORD)

    def _user(
        user_id: str, *, roles: list[str], tenant_id: str | None, **extra: Any
    ) -> User:
        return User(
            id=user_id,
            username=user_id,
            first_name=user_id,
            last_name="Test",
            password=password_hash,
            email=f"{user_id}@test.local",
            roles=roles,
            tenant_id=tenant_id,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
            **extra,
        )

    async with AsyncSession(engine) as session:
        session.add_all(
            [
                _user("admin-a", roles=[Role.admin.value], tenant_id=TENANT_A),
                _user("admin-a2", roles=[Role.admin.value], tenant_id=TENANT_A),
                _user("dev-a", roles=[Role.developer.value], tenant_id=TENANT_A),
                _user(
                    "dev-a-disabled",
                    roles=[Role.developer.value],
                    tenant_id=TENANT_A,
                    enabled=False,
                ),
                _user(
                    "dev-a-deleted",
                    roles=[Role.developer.value],
                    tenant_id=TENANT_A,
                    deleted_at=datetime.now(UTC),
                ),
                _user("admin-b", roles=[Role.admin.value], tenant_id=TENANT_B),
                _user("dev-b", roles=[Role.developer.value], tenant_id=TENANT_B),
                _user("root", roles=[Role.super_admin.value], tenant_id=None),
                _user("root2", roles=[Role.super_admin.value], tenant_id=None),
            ]
        )
        await session.commit()


# ---------- service-level: eligibility rules and audit trail ----------


@pytest_asyncio.fixture()
async def impersonation_service_engine() -> AsyncGenerator[Any, None]:
    """In-memory engine seeded with the cast, for direct ``ImpersonationService`` calls."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await _seed_impersonation_cast(engine)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _service_and_user(
    engine: Any, session: AsyncSession, user_id: str
) -> tuple[ImpersonationService, User]:
    service = ImpersonationService(
        SqlImpersonationEventRepository(session), SqlUserRepository(session)
    )
    actor = await session.get(User, user_id)
    assert actor is not None
    return service, actor


@pytest.mark.asyncio
async def test_start_unknown_target_not_found(
    impersonation_service_engine: Any,
) -> None:
    async with AsyncSession(
        impersonation_service_engine, expire_on_commit=False
    ) as session:
        service, actor = await _service_and_user(
            impersonation_service_engine, session, "admin-a"
        )
        with pytest.raises(NotFoundError):
            await service.start(actor=actor, target_user_id="nobody")


@pytest.mark.asyncio
async def test_start_cross_tenant_target_not_found_for_admin(
    impersonation_service_engine: Any,
) -> None:
    async with AsyncSession(
        impersonation_service_engine, expire_on_commit=False
    ) as session:
        service, actor = await _service_and_user(
            impersonation_service_engine, session, "admin-a"
        )
        with pytest.raises(NotFoundError):
            await service.start(actor=actor, target_user_id="dev-b")


@pytest.mark.asyncio
async def test_start_cross_tenant_allowed_for_super_admin(
    impersonation_service_engine: Any,
) -> None:
    async with AsyncSession(
        impersonation_service_engine, expire_on_commit=False
    ) as session:
        service, actor = await _service_and_user(
            impersonation_service_engine, session, "root"
        )
        target = await service.start(actor=actor, target_user_id="dev-b")
        assert target.id == "dev-b"


@pytest.mark.asyncio
async def test_start_self_forbidden(impersonation_service_engine: Any) -> None:
    async with AsyncSession(
        impersonation_service_engine, expire_on_commit=False
    ) as session:
        service, actor = await _service_and_user(
            impersonation_service_engine, session, "admin-a"
        )
        with pytest.raises(ForbiddenError):
            await service.start(actor=actor, target_user_id="admin-a")


@pytest.mark.asyncio
async def test_start_system_user_forbidden_for_super_admin(
    impersonation_service_engine: Any,
) -> None:
    async with AsyncSession(
        impersonation_service_engine, expire_on_commit=False
    ) as session:
        service, actor = await _service_and_user(
            impersonation_service_engine, session, "root"
        )
        with pytest.raises(ForbiddenError):
            await service.start(actor=actor, target_user_id=SYSTEM_USER_ID)


@pytest.mark.asyncio
async def test_start_disabled_target_forbidden(
    impersonation_service_engine: Any,
) -> None:
    async with AsyncSession(
        impersonation_service_engine, expire_on_commit=False
    ) as session:
        service, actor = await _service_and_user(
            impersonation_service_engine, session, "admin-a"
        )
        with pytest.raises(ForbiddenError):
            await service.start(actor=actor, target_user_id="dev-a-disabled")


@pytest.mark.asyncio
async def test_start_deleted_target_forbidden(
    impersonation_service_engine: Any,
) -> None:
    async with AsyncSession(
        impersonation_service_engine, expire_on_commit=False
    ) as session:
        service, actor = await _service_and_user(
            impersonation_service_engine, session, "admin-a"
        )
        with pytest.raises(ForbiddenError):
            await service.start(actor=actor, target_user_id="dev-a-deleted")


@pytest.mark.asyncio
async def test_start_admin_target_forbidden(
    impersonation_service_engine: Any,
) -> None:
    async with AsyncSession(
        impersonation_service_engine, expire_on_commit=False
    ) as session:
        service, actor = await _service_and_user(
            impersonation_service_engine, session, "admin-a"
        )
        with pytest.raises(ForbiddenError):
            await service.start(actor=actor, target_user_id="admin-a2")


@pytest.mark.asyncio
async def test_start_admin_target_allowed_for_super_admin(
    impersonation_service_engine: Any,
) -> None:
    """A super_admin actor may impersonate an admin target, even cross-tenant."""
    async with AsyncSession(
        impersonation_service_engine, expire_on_commit=False
    ) as session:
        service, actor = await _service_and_user(
            impersonation_service_engine, session, "root"
        )
        target = await service.start(actor=actor, target_user_id="admin-b")
        assert target.id == "admin-b"


@pytest.mark.asyncio
async def test_start_super_admin_target_forbidden(
    impersonation_service_engine: Any,
) -> None:
    async with AsyncSession(
        impersonation_service_engine, expire_on_commit=False
    ) as session:
        service, actor = await _service_and_user(
            impersonation_service_engine, session, "root"
        )
        with pytest.raises(ForbiddenError):
            await service.start(actor=actor, target_user_id="root2")


@pytest.mark.asyncio
async def test_start_creates_open_event_and_closes_prior_one(
    impersonation_service_engine: Any,
) -> None:
    async with AsyncSession(
        impersonation_service_engine, expire_on_commit=False
    ) as session:
        service, actor = await _service_and_user(
            impersonation_service_engine, session, "admin-a"
        )
        await service.start(actor=actor, target_user_id="dev-a")
        first_open = (
            await session.exec(
                select(ImpersonationEvent).where(
                    col(ImpersonationEvent.impersonator_id) == "admin-a",
                    col(ImpersonationEvent.ended_at).is_(None),
                )
            )
        ).one()
        assert first_open.target_user_id == "dev-a"

        await service.start(actor=actor, target_user_id="dev-a")
        # Starting again for the same actor closes the previous open event and
        # opens exactly one new one.
        open_events = (
            await session.exec(
                select(ImpersonationEvent).where(
                    col(ImpersonationEvent.impersonator_id) == "admin-a",
                    col(ImpersonationEvent.ended_at).is_(None),
                )
            )
        ).all()
        assert len(open_events) == 1
        refreshed_first = await session.get(ImpersonationEvent, first_open.id)
        assert refreshed_first is not None
        assert refreshed_first.ended_at is not None


@pytest.mark.asyncio
async def test_resolve_effective_user_no_open_event_returns_actor(
    impersonation_service_engine: Any,
) -> None:
    async with AsyncSession(
        impersonation_service_engine, expire_on_commit=False
    ) as session:
        service, actor = await _service_and_user(
            impersonation_service_engine, session, "admin-a"
        )
        effective = await service.resolve_effective_user(
            actor=actor, target_user_id="dev-a"
        )
        assert effective.id == "admin-a"


@pytest.mark.asyncio
async def test_resolve_effective_user_valid_event_returns_target(
    impersonation_service_engine: Any,
) -> None:
    async with AsyncSession(
        impersonation_service_engine, expire_on_commit=False
    ) as session:
        service, actor = await _service_and_user(
            impersonation_service_engine, session, "admin-a"
        )
        await service.start(actor=actor, target_user_id="dev-a")
        effective = await service.resolve_effective_user(
            actor=actor, target_user_id="dev-a"
        )
        assert effective.id == "dev-a"


@pytest.mark.asyncio
async def test_resolve_effective_user_invalidated_target_falls_back_and_closes_event(
    impersonation_service_engine: Any,
) -> None:
    async with AsyncSession(
        impersonation_service_engine, expire_on_commit=False
    ) as session:
        service, actor = await _service_and_user(
            impersonation_service_engine, session, "admin-a"
        )
        await service.start(actor=actor, target_user_id="dev-a")

        target = await session.get(User, "dev-a")
        assert target is not None
        target.enabled = False
        session.add(target)
        await session.commit()

        effective = await service.resolve_effective_user(
            actor=actor, target_user_id="dev-a"
        )
        assert effective.id == "admin-a"

        events_repo = SqlImpersonationEventRepository(session)
        assert (
            await events_repo.get_open(
                impersonator_id="admin-a", target_user_id="dev-a"
            )
        ) is None


@pytest.mark.asyncio
async def test_resolve_effective_user_actor_demoted_falls_back_and_closes_event(
    impersonation_service_engine: Any,
) -> None:
    """An actor demoted from super_admin mid-session loses an admin impersonation.

    Builds a detached copy of ``actor`` with an empty ``roles`` rather than
    mutating the session-tracked instance in place -- the latter would
    autoflush an ``UPDATE`` that violates
    ``ck_users_non_super_admin_requires_tenant`` (a real demotion would also
    need a new ``tenant_id``, which is out of scope for this test). The
    detached copy simulates what a fresh per-request fetch via
    ``get_session_user`` would return after a real demotion, which is the
    only thing :meth:`resolve_effective_user` actually reads.
    """
    async with AsyncSession(
        impersonation_service_engine, expire_on_commit=False
    ) as session:
        service, actor = await _service_and_user(
            impersonation_service_engine, session, "root"
        )
        await service.start(actor=actor, target_user_id="admin-a")

        demoted_actor = actor.model_copy(update={"roles": []})

        effective = await service.resolve_effective_user(
            actor=demoted_actor, target_user_id="admin-a"
        )
        assert effective.id == "root"

        events_repo = SqlImpersonationEventRepository(session)
        assert (
            await events_repo.get_open(impersonator_id="root", target_user_id="admin-a")
        ) is None


@pytest.mark.asyncio
async def test_stop_closes_open_event(impersonation_service_engine: Any) -> None:
    async with AsyncSession(
        impersonation_service_engine, expire_on_commit=False
    ) as session:
        service, actor = await _service_and_user(
            impersonation_service_engine, session, "admin-a"
        )
        await service.start(actor=actor, target_user_id="dev-a")
        await service.stop(actor=actor)
        events_repo = SqlImpersonationEventRepository(session)
        assert (
            await events_repo.get_open(
                impersonator_id="admin-a", target_user_id="dev-a"
            )
        ) is None


@pytest.mark.asyncio
async def test_stop_is_noop_when_nothing_open(
    impersonation_service_engine: Any,
) -> None:
    async with AsyncSession(
        impersonation_service_engine, expire_on_commit=False
    ) as session:
        service, actor = await _service_and_user(
            impersonation_service_engine, session, "admin-a"
        )
        await service.stop(actor=actor)  # must not raise


# ---------- end to end: real cookies, CSRF, and the router wiring ----------


@pytest_asyncio.fixture()
async def impersonation_client() -> AsyncGenerator[tuple[AsyncClient, Any], None]:
    """Real-cookie HTTP client (no dependency overrides) backed by the seeded cast."""
    from infrastructure.database import get_session
    from main import app

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await _seed_impersonation_cast(engine)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac, engine
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def _login(client: AsyncClient, username: str, *, tenant_name: str | None) -> Any:
    """Log in as one of the seeded cast members and return the parsed response data."""
    body: dict[str, str] = {"username": username, "password": AUTH_PASSWORD}
    if tenant_name is not None:
        body["tenantName"] = tenant_name
    return assert_ok(await client.post("/api/v1/auth/login", json=body))


@pytest.mark.asyncio
async def test_me_shape_has_no_impersonation_before_impersonating(
    impersonation_client: tuple[AsyncClient, Any],
) -> None:
    client, _engine = impersonation_client
    await _login(client, "admin-a", tenant_name=TENANT_A)
    me = assert_ok(await client.get("/api/v1/auth/me"))
    assert me["user"]["id"] == "admin-a"
    assert me["impersonatedBy"] is None


@pytest.mark.asyncio
async def test_start_impersonation_requires_admin_role(
    impersonation_client: tuple[AsyncClient, Any],
) -> None:
    client, _engine = impersonation_client
    await _login(client, "dev-a", tenant_name=TENANT_A)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert csrf is not None
    assert_err(
        await client.post(
            "/api/v1/auth/impersonate",
            json={"targetUserId": "dev-b"},
            headers={CSRF_HEADER_NAME: csrf},
        ),
        code="FORBIDDEN",
        status=403,
    )


@pytest.mark.asyncio
async def test_start_impersonation_requires_csrf(
    impersonation_client: tuple[AsyncClient, Any],
) -> None:
    client, _engine = impersonation_client
    await _login(client, "admin-a", tenant_name=TENANT_A)
    assert_err(
        await client.post("/api/v1/auth/impersonate", json={"targetUserId": "dev-a"}),
        code="CSRF_FAILED",
        status=403,
    )


@pytest.mark.asyncio
async def test_stop_impersonation_requires_csrf(
    impersonation_client: tuple[AsyncClient, Any],
) -> None:
    client, _engine = impersonation_client
    await _login(client, "admin-a", tenant_name=TENANT_A)
    assert_err(
        await client.delete("/api/v1/auth/impersonate"),
        code="CSRF_FAILED",
        status=403,
    )


@pytest.mark.asyncio
async def test_cross_tenant_impersonation_not_found_end_to_end(
    impersonation_client: tuple[AsyncClient, Any],
) -> None:
    client, _engine = impersonation_client
    await _login(client, "admin-a", tenant_name=TENANT_A)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert csrf is not None
    assert_err(
        await client.post(
            "/api/v1/auth/impersonate",
            json={"targetUserId": "dev-b"},
            headers={CSRF_HEADER_NAME: csrf},
        ),
        code="NOT_FOUND",
        status=404,
    )


@pytest.mark.asyncio
async def test_admin_target_impersonation_forbidden_end_to_end(
    impersonation_client: tuple[AsyncClient, Any],
) -> None:
    client, _engine = impersonation_client
    await _login(client, "admin-a", tenant_name=TENANT_A)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert csrf is not None
    assert_err(
        await client.post(
            "/api/v1/auth/impersonate",
            json={"targetUserId": "admin-a2"},
            headers={CSRF_HEADER_NAME: csrf},
        ),
        code="FORBIDDEN",
        status=403,
    )


@pytest.mark.asyncio
async def test_super_admin_can_impersonate_admin_target_end_to_end(
    impersonation_client: tuple[AsyncClient, Any],
) -> None:
    """Unlike a regular admin, a super_admin actor may impersonate an admin target."""
    client, _engine = impersonation_client
    await _login(client, "root", tenant_name=None)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert csrf is not None
    started = assert_ok(
        await client.post(
            "/api/v1/auth/impersonate",
            json={"targetUserId": "admin-a"},
            headers={CSRF_HEADER_NAME: csrf},
        )
    )
    assert started["user"]["id"] == "admin-a"
    assert started["impersonatedBy"]["id"] == "root"


@pytest.mark.asyncio
async def test_full_lifecycle_admin_impersonates_developer(
    impersonation_client: tuple[AsyncClient, Any],
) -> None:
    """Start -> a write is attributed to the target -> stop -> stale header self-heals.

    Also regression-tests the two correctness fixes documented in
    ``dependencies/auth.py``: stopping must succeed even though the request
    still carries the impersonation header (the ``require_actor_roles`` fix),
    and a header left over after stopping must silently fall back to the real
    actor rather than error (the "never raise on a stale header" design).
    """
    client, engine = impersonation_client
    await _login(client, "admin-a", tenant_name=TENANT_A)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert csrf is not None

    started = assert_ok(
        await client.post(
            "/api/v1/auth/impersonate",
            json={"targetUserId": "dev-a"},
            headers={CSRF_HEADER_NAME: csrf},
        )
    )
    assert started["user"]["id"] == "dev-a"
    assert started["impersonatedBy"]["id"] == "admin-a"

    imp_headers = {IMPERSONATE_HEADER_NAME: "dev-a"}
    me_impersonating = assert_ok(
        await client.get("/api/v1/auth/me", headers=imp_headers)
    )
    assert me_impersonating["user"]["id"] == "dev-a"
    assert me_impersonating["impersonatedBy"]["id"] == "admin-a"

    created = assert_ok(
        await client.post(
            "/api/v1/mcp-servers",
            json={"name": "impersonated-mcp", "url": "https://mcp.example.com/mcp"},
            headers={**imp_headers, CSRF_HEADER_NAME: csrf},
        ),
        status=201,
    )
    assert created["createdBy"] == "dev-a"

    stopped = assert_ok(
        await client.delete(
            "/api/v1/auth/impersonate",
            headers={**imp_headers, CSRF_HEADER_NAME: csrf},
        )
    )
    assert stopped["user"]["id"] == "admin-a"
    assert stopped["impersonatedBy"] is None

    me_after_stop = assert_ok(await client.get("/api/v1/auth/me", headers=imp_headers))
    assert me_after_stop["user"]["id"] == "admin-a"
    assert me_after_stop["impersonatedBy"] is None

    async with AsyncSession(engine) as session:
        event = (
            await session.exec(
                select(ImpersonationEvent).where(
                    col(ImpersonationEvent.impersonator_id) == "admin-a"
                )
            )
        ).one()
        assert event.ended_at is not None


@pytest.mark.asyncio
async def test_deleting_user_with_impersonation_history_soft_deletes(
    impersonation_client: tuple[AsyncClient, Any],
) -> None:
    """A RESTRICT FK from ImpersonationEvent falls back to the existing soft-delete path."""
    client, engine = impersonation_client
    await _login(client, "admin-a", tenant_name=TENANT_A)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    assert csrf is not None

    assert_ok(
        await client.post(
            "/api/v1/auth/impersonate",
            json={"targetUserId": "dev-a"},
            headers={CSRF_HEADER_NAME: csrf},
        )
    )
    assert_ok(
        await client.delete(
            "/api/v1/auth/impersonate", headers={CSRF_HEADER_NAME: csrf}
        )
    )
    assert_ok(
        await client.delete("/api/v1/users/admin-a", headers={CSRF_HEADER_NAME: csrf})
    )

    async with AsyncSession(engine) as session:
        user = await session.get(User, "admin-a")
        assert user is not None
        assert user.deleted_at is not None
        assert user.enabled is False
