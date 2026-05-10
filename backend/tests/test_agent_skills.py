from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from tests._envelope import assert_err, assert_ok


@pytest_asyncio.fixture()
async def skill_client(
    mock_adk_agent: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    from database import get_session
    from dependencies import get_adk_agent
    from main import app
    from models.agent_skill import (
        AgentSkill as _AgentSkill,  # noqa: F401 — registers model
    )

    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_adk_agent] = lambda: mock_adk_agent
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        await mem_engine.dispose()


_CREATE_BODY = {"name": "My Skill", "repo_url": "https://github.com/example/repo"}


# ---------- create ----------


async def test_create_skill_returns_201(skill_client: AsyncClient) -> None:
    response = await skill_client.post("/agent-skills", json=_CREATE_BODY)
    assert response.status_code == 201


async def test_create_skill_response_has_id(skill_client: AsyncClient) -> None:
    response = await skill_client.post("/agent-skills", json=_CREATE_BODY)
    assert "id" in assert_ok(response, status=201)


async def test_create_skill_response_has_correct_name(
    skill_client: AsyncClient,
) -> None:
    response = await skill_client.post("/agent-skills", json=_CREATE_BODY)
    assert assert_ok(response, status=201)["name"] == "My Skill"


async def test_create_skill_missing_name_returns_422(skill_client: AsyncClient) -> None:
    response = await skill_client.post(
        "/agent-skills", json={"repo_url": "https://github.com/example/repo"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_skill_missing_repo_url_returns_422(
    skill_client: AsyncClient,
) -> None:
    response = await skill_client.post("/agent-skills", json={"name": "My Skill"})
    assert_err(response, code="VALIDATION_ERROR", status=422)


# ---------- list ----------


async def test_list_skills_empty_initially(skill_client: AsyncClient) -> None:
    response = await skill_client.get("/agent-skills")
    assert assert_ok(response) == []


async def test_list_skills_returns_created_skill(skill_client: AsyncClient) -> None:
    await skill_client.post("/agent-skills", json=_CREATE_BODY)
    response = await skill_client.get("/agent-skills")
    assert len(assert_ok(response)) == 1


async def test_list_skills_respects_limit_param(skill_client: AsyncClient) -> None:
    for i in range(3):
        await skill_client.post(
            "/agent-skills",
            json={"name": f"Skill {i}", "repo_url": "https://github.com/x/y"},
        )
    response = await skill_client.get("/agent-skills", params={"limit": 2})
    assert len(assert_ok(response)) == 2


async def test_list_skills_respects_offset_param(skill_client: AsyncClient) -> None:
    for i in range(3):
        await skill_client.post(
            "/agent-skills",
            json={"name": f"Skill {i}", "repo_url": "https://github.com/x/y"},
        )
    response = await skill_client.get(
        "/agent-skills", params={"limit": 10, "offset": 2}
    )
    assert len(assert_ok(response)) == 1


# ---------- get ----------


async def test_get_skill_returns_200(skill_client: AsyncClient) -> None:
    created = assert_ok(
        await skill_client.post("/agent-skills", json=_CREATE_BODY), status=201
    )
    response = await skill_client.get(f"/agent-skills/{created['id']}")
    assert response.status_code == 200


async def test_get_skill_returns_correct_data(skill_client: AsyncClient) -> None:
    created = assert_ok(
        await skill_client.post("/agent-skills", json=_CREATE_BODY), status=201
    )
    response = await skill_client.get(f"/agent-skills/{created['id']}")
    assert assert_ok(response)["name"] == "My Skill"


async def test_get_skill_unknown_id_returns_404(skill_client: AsyncClient) -> None:
    response = await skill_client.get("/agent-skills/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- patch ----------


async def test_update_skill_returns_200(skill_client: AsyncClient) -> None:
    created = assert_ok(
        await skill_client.post("/agent-skills", json=_CREATE_BODY), status=201
    )
    response = await skill_client.patch(
        f"/agent-skills/{created['id']}", json={"name": "Renamed"}
    )
    assert response.status_code == 200


async def test_update_skill_partial_update_leaves_other_fields_unchanged(
    skill_client: AsyncClient,
) -> None:
    created = assert_ok(
        await skill_client.post("/agent-skills", json=_CREATE_BODY), status=201
    )
    response = await skill_client.patch(
        f"/agent-skills/{created['id']}", json={"name": "Renamed"}
    )
    assert assert_ok(response)["repo_url"] == _CREATE_BODY["repo_url"]


async def test_update_skill_unknown_id_returns_404(skill_client: AsyncClient) -> None:
    response = await skill_client.patch("/agent-skills/nonexistent", json={"name": "X"})
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- delete ----------


async def test_delete_skill_returns_200(skill_client: AsyncClient) -> None:
    created = assert_ok(
        await skill_client.post("/agent-skills", json=_CREATE_BODY), status=201
    )
    response = await skill_client.delete(f"/agent-skills/{created['id']}")
    assert assert_ok(response, status=200) is None


async def test_delete_skill_removes_from_list(skill_client: AsyncClient) -> None:
    created = assert_ok(
        await skill_client.post("/agent-skills", json=_CREATE_BODY), status=201
    )
    await skill_client.delete(f"/agent-skills/{created['id']}")
    response = await skill_client.get("/agent-skills")
    assert assert_ok(response) == []


async def test_delete_skill_unknown_id_returns_404(skill_client: AsyncClient) -> None:
    response = await skill_client.delete("/agent-skills/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- created_by / updated_by ----------


async def test_create_skill_populates_created_and_updated_by_from_header(
    skill_client: AsyncClient,
) -> None:
    response = await skill_client.post(
        "/agent-skills", json=_CREATE_BODY, headers={"X-User-Id": "alice"}
    )
    body = assert_ok(response, status=201)
    assert body["created_by"] == "alice"
    assert body["updated_by"] == "alice"


async def test_create_skill_without_header_defaults_to_empty_string(
    skill_client: AsyncClient,
) -> None:
    response = await skill_client.post("/agent-skills", json=_CREATE_BODY)
    body = assert_ok(response, status=201)
    assert body["created_by"] == ""
    assert body["updated_by"] == ""


async def test_update_skill_preserves_created_by_and_overwrites_updated_by(
    skill_client: AsyncClient,
) -> None:
    created = assert_ok(
        await skill_client.post(
            "/agent-skills", json=_CREATE_BODY, headers={"X-User-Id": "alice"}
        ),
        status=201,
    )
    response = await skill_client.patch(
        f"/agent-skills/{created['id']}",
        json={"name": "Renamed"},
        headers={"X-User-Id": "bob"},
    )
    body = assert_ok(response)
    assert body["created_by"] == "alice"
    assert body["updated_by"] == "bob"
