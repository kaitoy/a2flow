from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from google.adk.sessions import InMemorySessionService
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession


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
    from database import get_session
    from dependencies import (
        get_agent_registry,
        get_session_service,
        get_skill_manager,
    )
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

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_agent_registry] = lambda: mock_agent_registry
    app.dependency_overrides[get_session_service] = lambda: real_session_service
    app.dependency_overrides[get_skill_manager] = lambda: mock_skill_manager
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        await mem_engine.dispose()
