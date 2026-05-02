from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from google.adk.sessions import InMemorySessionService
from httpx import ASGITransport, AsyncClient


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


@pytest_asyncio.fixture()
async def client_with_real_sessions(
    real_session_service: InMemorySessionService,
    mock_adk_agent: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    from main import app, get_adk_agent, get_session_service

    app.dependency_overrides[get_session_service] = lambda: real_session_service
    app.dependency_overrides[get_adk_agent] = lambda: mock_adk_agent
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
