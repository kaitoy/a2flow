from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from models.user import SYSTEM_USER_ID
from tests._envelope import assert_err, assert_ok
from tests._seed import seed_users
from tests.conftest import _install_auth_overrides


@pytest_asyncio.fixture()
async def skill_client(
    mock_agent_registry: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    from dependencies import get_agent_registry
    from infrastructure.database import get_session
    from main import app
    from models.agent_skill import (
        AgentSkill as _AgentSkill,  # noqa: F401 — registers model
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


_CREATE_BODY = {"name": "My Skill", "repo_url": "https://github.com/example/repo"}


# ---------- create ----------


async def test_create_skill_returns_201(skill_client: AsyncClient) -> None:
    response = await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY)
    assert response.status_code == 201


async def test_create_skill_response_has_id(skill_client: AsyncClient) -> None:
    response = await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY)
    assert "id" in assert_ok(response, status=201)


async def test_create_skill_response_has_correct_name(
    skill_client: AsyncClient,
) -> None:
    response = await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY)
    assert assert_ok(response, status=201)["name"] == "My Skill"


async def test_create_skill_missing_name_returns_422(skill_client: AsyncClient) -> None:
    response = await skill_client.post(
        "/api/v1/agent-skills", json={"repo_url": "https://github.com/example/repo"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_skill_missing_repo_url_returns_422(
    skill_client: AsyncClient,
) -> None:
    response = await skill_client.post(
        "/api/v1/agent-skills", json={"name": "My Skill"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


# ---------- list ----------


async def test_list_skills_empty_initially(skill_client: AsyncClient) -> None:
    response = await skill_client.get("/api/v1/agent-skills")
    assert assert_ok(response) == []


async def test_list_skills_returns_created_skill(skill_client: AsyncClient) -> None:
    await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY)
    response = await skill_client.get("/api/v1/agent-skills")
    assert len(assert_ok(response)) == 1


async def test_list_skills_respects_limit_param(skill_client: AsyncClient) -> None:
    for i in range(3):
        await skill_client.post(
            "/api/v1/agent-skills",
            json={"name": f"Skill {i}", "repo_url": "https://github.com/x/y"},
        )
    response = await skill_client.get("/api/v1/agent-skills", params={"limit": 2})
    assert len(assert_ok(response)) == 2


async def test_list_skills_respects_offset_param(skill_client: AsyncClient) -> None:
    for i in range(3):
        await skill_client.post(
            "/api/v1/agent-skills",
            json={"name": f"Skill {i}", "repo_url": "https://github.com/x/y"},
        )
    response = await skill_client.get(
        "/api/v1/agent-skills", params={"limit": 10, "offset": 2}
    )
    assert len(assert_ok(response)) == 1


# ---------- sort & filter ----------


async def _create_named_skills(skill_client: AsyncClient) -> None:
    for i in range(3):
        await skill_client.post(
            "/api/v1/agent-skills",
            json={"name": f"Skill {i}", "repo_url": "https://github.com/x/y"},
        )


async def test_list_skills_sort_by_name_asc(skill_client: AsyncClient) -> None:
    await _create_named_skills(skill_client)
    response = await skill_client.get("/api/v1/agent-skills", params={"s": "name"})
    names = [s["name"] for s in assert_ok(response)]
    assert names == ["Skill 0", "Skill 1", "Skill 2"]


async def test_list_skills_sort_by_name_desc(skill_client: AsyncClient) -> None:
    await _create_named_skills(skill_client)
    response = await skill_client.get("/api/v1/agent-skills", params={"s": "-name"})
    names = [s["name"] for s in assert_ok(response)]
    assert names == ["Skill 2", "Skill 1", "Skill 0"]


async def test_list_skills_filter_eq(skill_client: AsyncClient) -> None:
    await _create_named_skills(skill_client)
    response = await skill_client.get(
        "/api/v1/agent-skills", params={"q": "name:eq:Skill 1"}
    )
    data = assert_ok(response)
    assert [s["name"] for s in data] == ["Skill 1"]


async def test_list_skills_filter_like_is_case_insensitive(
    skill_client: AsyncClient,
) -> None:
    await _create_named_skills(skill_client)
    response = await skill_client.get(
        "/api/v1/agent-skills", params={"q": "name:like:skill"}
    )
    assert len(assert_ok(response)) == 3


async def test_list_skills_invalid_sort_field_returns_400(
    skill_client: AsyncClient,
) -> None:
    response = await skill_client.get(
        "/api/v1/agent-skills", params={"s": "bogusField"}
    )
    assert_err(response, code="INVALID_QUERY", status=400)


async def test_list_skills_invalid_filter_operator_returns_400(
    skill_client: AsyncClient,
) -> None:
    response = await skill_client.get(
        "/api/v1/agent-skills", params={"q": "name:bogus:foo"}
    )
    assert_err(response, code="INVALID_QUERY", status=400)


async def test_list_skills_malformed_filter_returns_400(
    skill_client: AsyncClient,
) -> None:
    response = await skill_client.get("/api/v1/agent-skills", params={"q": "name=foo"})
    assert_err(response, code="INVALID_QUERY", status=400)


# ---------- get ----------


async def test_get_skill_returns_200(skill_client: AsyncClient) -> None:
    created = assert_ok(
        await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY), status=201
    )
    response = await skill_client.get(f"/api/v1/agent-skills/{created['id']}")
    assert response.status_code == 200


async def test_get_skill_returns_correct_data(skill_client: AsyncClient) -> None:
    created = assert_ok(
        await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY), status=201
    )
    response = await skill_client.get(f"/api/v1/agent-skills/{created['id']}")
    assert assert_ok(response)["name"] == "My Skill"


async def test_get_skill_unknown_id_returns_404(skill_client: AsyncClient) -> None:
    response = await skill_client.get("/api/v1/agent-skills/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- patch ----------


async def test_update_skill_returns_200(skill_client: AsyncClient) -> None:
    created = assert_ok(
        await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY), status=201
    )
    response = await skill_client.patch(
        f"/api/v1/agent-skills/{created['id']}", json={"name": "Renamed"}
    )
    assert response.status_code == 200


async def test_update_skill_partial_update_leaves_other_fields_unchanged(
    skill_client: AsyncClient,
) -> None:
    created = assert_ok(
        await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY), status=201
    )
    response = await skill_client.patch(
        f"/api/v1/agent-skills/{created['id']}", json={"name": "Renamed"}
    )
    assert assert_ok(response)["repoUrl"] == _CREATE_BODY["repo_url"]


async def test_update_skill_unknown_id_returns_404(skill_client: AsyncClient) -> None:
    response = await skill_client.patch(
        "/api/v1/agent-skills/nonexistent", json={"name": "X"}
    )
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- delete ----------


async def test_delete_skill_returns_200(skill_client: AsyncClient) -> None:
    created = assert_ok(
        await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY), status=201
    )
    response = await skill_client.delete(f"/api/v1/agent-skills/{created['id']}")
    assert assert_ok(response, status=200) is None


async def test_delete_skill_removes_from_list(skill_client: AsyncClient) -> None:
    created = assert_ok(
        await skill_client.post("/api/v1/agent-skills", json=_CREATE_BODY), status=201
    )
    await skill_client.delete(f"/api/v1/agent-skills/{created['id']}")
    response = await skill_client.get("/api/v1/agent-skills")
    assert assert_ok(response) == []


async def test_delete_skill_unknown_id_returns_404(skill_client: AsyncClient) -> None:
    response = await skill_client.delete("/api/v1/agent-skills/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- created_by / updated_by ----------


async def test_create_skill_populates_created_and_updated_by_from_header(
    skill_client: AsyncClient,
) -> None:
    response = await skill_client.post(
        "/api/v1/agent-skills", json=_CREATE_BODY, headers={"X-User-Id": "alice"}
    )
    body = assert_ok(response, status=201)
    assert body["createdBy"] == "alice"
    assert body["updatedBy"] == "alice"


async def test_create_skill_with_unknown_user_returns_422(
    skill_client: AsyncClient,
) -> None:
    response = await skill_client.post(
        "/api/v1/agent-skills",
        json=_CREATE_BODY,
        headers={"X-User-Id": "ghost-user"},
    )
    assert_err(response, code="FOREIGN_KEY_VIOLATION", status=422)


async def test_update_skill_preserves_created_by_and_overwrites_updated_by(
    skill_client: AsyncClient,
) -> None:
    created = assert_ok(
        await skill_client.post(
            "/api/v1/agent-skills", json=_CREATE_BODY, headers={"X-User-Id": "alice"}
        ),
        status=201,
    )
    response = await skill_client.patch(
        f"/api/v1/agent-skills/{created['id']}",
        json={"name": "Renamed"},
        headers={"X-User-Id": "bob"},
    )
    body = assert_ok(response)
    assert body["createdBy"] == "alice"
    assert body["updatedBy"] == "bob"
