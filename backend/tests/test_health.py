from httpx import AsyncClient


async def test_health_returns_200(client_with_real_sessions: AsyncClient) -> None:
    response = await client_with_real_sessions.get("/api/v1/health")
    assert response.status_code == 200


async def test_health_returns_ok_status(client_with_real_sessions: AsyncClient) -> None:
    response = await client_with_real_sessions.get("/api/v1/health")
    assert response.json() == {"status": "ok"}


async def test_health_content_type_is_json(
    client_with_real_sessions: AsyncClient,
) -> None:
    response = await client_with_real_sessions.get("/api/v1/health")
    assert "application/json" in response.headers["content-type"]
