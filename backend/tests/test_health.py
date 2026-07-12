from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession


@pytest_asyncio.fixture()
async def db_ok_client() -> AsyncGenerator[AsyncClient, None]:
    """A client backed by an isolated in-memory database, for the reachable-DB path."""
    from infrastructure.database import get_session
    from main import app

    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine) as session:
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


@pytest_asyncio.fixture()
async def unreachable_db_client() -> AsyncGenerator[AsyncClient, None]:
    """A client whose database dependency always raises, simulating a down database."""
    from infrastructure.database import get_session
    from main import app

    async def override_get_session() -> AsyncGenerator[AsyncMock, None]:
        session = AsyncMock()
        session.execute.side_effect = SQLAlchemyError("database unreachable")
        yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


async def test_health_returns_200_when_db_reachable(db_ok_client: AsyncClient) -> None:
    response = await db_ok_client.get("/api/v1/health")
    assert response.status_code == 200


async def test_health_returns_ok_status_when_db_reachable(
    db_ok_client: AsyncClient,
) -> None:
    response = await db_ok_client.get("/api/v1/health")
    assert response.json() == {"status": "ok"}


async def test_health_content_type_is_json(db_ok_client: AsyncClient) -> None:
    response = await db_ok_client.get("/api/v1/health")
    assert "application/json" in response.headers["content-type"]


async def test_health_returns_503_when_db_unreachable(
    unreachable_db_client: AsyncClient,
) -> None:
    response = await unreachable_db_client.get("/api/v1/health")
    assert response.status_code == 503


async def test_health_returns_unavailable_status_when_db_unreachable(
    unreachable_db_client: AsyncClient,
) -> None:
    response = await unreachable_db_client.get("/api/v1/health")
    assert response.json() == {"status": "unavailable"}
