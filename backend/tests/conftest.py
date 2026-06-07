from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import Request
from google.adk.sessions import InMemorySessionService
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from models.user import SYSTEM_USER_ID, User
from tests._seed import seed_users


def _override_get_current_user_id(request: Request) -> str:
    """Test stand-in for the auth dependency that trusts the ``X-User-Id`` header.

    Returns the id straight from the header (defaulting to ``""``), so existing
    tests keep selecting their acting user via ``X-User-Id`` and the
    repository's foreign-key enforcement still rejects unknown ids exactly as
    before — without going through real login.
    """
    return request.headers.get("X-User-Id", "")


async def _override_get_current_user(request: Request) -> User:
    """Test stand-in for the route guard; returns a synthetic user holding the id."""
    return User.model_construct(id=request.headers.get("X-User-Id", ""))


def _override_verify_csrf() -> None:
    """Test stand-in that disables CSRF validation for header-authenticated tests."""
    return None


def _install_auth_overrides(app: Any) -> None:
    """Override the auth and CSRF dependencies with the header-based test stand-ins."""
    from dependencies.auth import (
        get_current_user,
        get_current_user_id,
        verify_csrf,
    )

    app.dependency_overrides[get_current_user] = _override_get_current_user
    app.dependency_overrides[get_current_user_id] = _override_get_current_user_id
    app.dependency_overrides[verify_csrf] = _override_verify_csrf


@pytest.fixture()
def real_session_service() -> InMemorySessionService:
    return InMemorySessionService()  # type: ignore[no-untyped-call]


@pytest.fixture()
def mock_adk_agent() -> MagicMock:
    agent = MagicMock()

    async def _empty_gen(
        *args: object, **kwargs: object
    ) -> AsyncGenerator[object, None]:
        return
        yield

    agent.run = _empty_gen
    return agent


@pytest.fixture()
def mock_agent_registry(mock_adk_agent: MagicMock) -> MagicMock:
    registry = MagicMock()
    registry.get.return_value = mock_adk_agent
    return registry


@pytest.fixture()
def mock_skill_manager() -> MagicMock:
    manager = MagicMock()
    manager.ensure_cloned = AsyncMock(return_value=Path("/tmp/skill"))
    return manager


@pytest_asyncio.fixture()
async def client_with_real_sessions(
    real_session_service: InMemorySessionService,
    mock_agent_registry: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    from dependencies import (
        get_agent_registry,
        get_session_service,
    )
    from main import app

    app.dependency_overrides[get_session_service] = lambda: real_session_service
    app.dependency_overrides[get_agent_registry] = lambda: mock_agent_registry
    _install_auth_overrides(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def workflow_client(
    mock_agent_registry: MagicMock,
    mock_skill_manager: MagicMock,
    real_session_service: InMemorySessionService,
) -> AsyncGenerator[AsyncClient, None]:
    from dependencies import (
        get_agent_registry,
        get_session_service,
        get_skill_manager,
    )
    from infrastructure.database import get_session
    from main import app
    from models.agent_skill import (
        AgentSkill as _AgentSkill,  # noqa: F401 — registers model
    )
    from models.workflow import Workflow as _Workflow  # noqa: F401 — registers model
    from models.workflow_session import (
        WorkflowSession as _WorkflowSession,  # noqa: F401 — registers model
    )
    from models.workflow_task import (
        WorkflowTask as _WorkflowTask,  # noqa: F401 — registers model
    )

    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(mem_engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await seed_users(mem_engine)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_agent_registry] = lambda: mock_agent_registry
    app.dependency_overrides[get_session_service] = lambda: real_session_service
    app.dependency_overrides[get_skill_manager] = lambda: mock_skill_manager
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


#: Credentials of the enabled user seeded for the real-auth ``auth_client``.
AUTH_USERNAME = "loginuser"
AUTH_PASSWORD = "login-password-123"


@pytest_asyncio.fixture()
async def auth_client() -> AsyncGenerator[AsyncClient, None]:
    """Yield a client exercising the real auth/CSRF flow (no dependency overrides).

    Backed by an in-memory database seeded with the system user and one enabled
    login user (:data:`AUTH_USERNAME` / :data:`AUTH_PASSWORD`, password hashed),
    so tests can drive ``/auth/login``, ``/auth/me``, and ``/auth/logout`` end
    to end. The ``httpx`` client keeps a cookie jar across requests, so cookies
    set at login are sent automatically on later calls.
    """
    from dependencies.auth import get_current_user, verify_csrf  # noqa: F401
    from infrastructure.database import get_session
    from infrastructure.password import hash_password
    from main import app
    from models.auth_session import AuthSession as _AuthSession  # noqa: F401
    from models.user import User as _User  # noqa: F401

    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(mem_engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await seed_users(mem_engine, ids=())
    async with AsyncSession(mem_engine) as session:
        session.add(
            _User(
                username=AUTH_USERNAME,
                first_name="Login",
                last_name="User",
                password=hash_password(AUTH_PASSWORD),
                email="login@test.local",
                enabled=True,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await session.commit()

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        await mem_engine.dispose()
