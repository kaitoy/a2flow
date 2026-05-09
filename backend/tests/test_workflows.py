from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession


@pytest_asyncio.fixture()
async def workflow_client(
    mock_adk_agent: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    from database import get_session
    from dependencies import get_adk_agent
    from main import app
    from models.agent_skill import (
        AgentSkill as _AgentSkill,  # noqa: F401 — registers model
    )
    from models.workflow import Workflow as _Workflow  # noqa: F401 — registers model

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
    app.dependency_overrides[get_adk_agent] = lambda: mock_adk_agent
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        await mem_engine.dispose()


_SKILL_BODY = {"name": "Skill A", "repo_url": "https://github.com/x/y"}
_WF_BODY = {"name": "My Workflow", "prompt": "Do the thing"}


async def _create_skill(client: AsyncClient) -> Any:
    return (await client.post("/agent-skills", json=_SKILL_BODY)).json()


async def _create_workflow(
    client: AsyncClient, skill_id: str, **overrides: object
) -> Any:
    body = {**_WF_BODY, "agent_skill_id": skill_id, **overrides}
    return (await client.post("/workflows", json=body)).json()


# ---------- create ----------


async def test_create_workflow_returns_201(workflow_client: AsyncClient) -> None:
    skill = await _create_skill(workflow_client)
    response = await workflow_client.post(
        "/workflows", json={**_WF_BODY, "agent_skill_id": skill["id"]}
    )
    assert response.status_code == 201


async def test_create_workflow_response_has_id(workflow_client: AsyncClient) -> None:
    skill = await _create_skill(workflow_client)
    response = await workflow_client.post(
        "/workflows", json={**_WF_BODY, "agent_skill_id": skill["id"]}
    )
    assert "id" in response.json()


async def test_create_workflow_response_has_correct_name(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    response = await workflow_client.post(
        "/workflows", json={**_WF_BODY, "agent_skill_id": skill["id"]}
    )
    assert response.json()["name"] == "My Workflow"


async def test_create_workflow_missing_name_returns_422(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    response = await workflow_client.post(
        "/workflows", json={"prompt": "p", "agent_skill_id": skill["id"]}
    )
    assert response.status_code == 422


async def test_create_workflow_missing_prompt_returns_422(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    response = await workflow_client.post(
        "/workflows", json={"name": "wf", "agent_skill_id": skill["id"]}
    )
    assert response.status_code == 422


async def test_create_workflow_missing_agent_skill_id_returns_422(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.post("/workflows", json=_WF_BODY)
    assert response.status_code == 422


async def test_create_workflow_unknown_agent_skill_id_returns_422(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.post(
        "/workflows", json={**_WF_BODY, "agent_skill_id": "nonexistent"}
    )
    assert response.status_code == 422


# ---------- list ----------


async def test_list_workflows_empty_initially(workflow_client: AsyncClient) -> None:
    response = await workflow_client.get("/workflows")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_workflows_returns_created_workflow(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    await _create_workflow(workflow_client, skill["id"])
    response = await workflow_client.get("/workflows")
    assert len(response.json()) == 1


async def test_list_workflows_respects_limit_param(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    for i in range(3):
        await _create_workflow(workflow_client, skill["id"], name=f"WF {i}")
    response = await workflow_client.get("/workflows", params={"limit": 2})
    assert len(response.json()) == 2


async def test_list_workflows_respects_offset_param(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    for i in range(3):
        await _create_workflow(workflow_client, skill["id"], name=f"WF {i}")
    response = await workflow_client.get(
        "/workflows", params={"limit": 10, "offset": 2}
    )
    assert len(response.json()) == 1


# ---------- get ----------


async def test_get_workflow_returns_200(workflow_client: AsyncClient) -> None:
    skill = await _create_skill(workflow_client)
    created = await _create_workflow(workflow_client, skill["id"])
    response = await workflow_client.get(f"/workflows/{created['id']}")
    assert response.status_code == 200


async def test_get_workflow_returns_correct_data(workflow_client: AsyncClient) -> None:
    skill = await _create_skill(workflow_client)
    created = await _create_workflow(workflow_client, skill["id"])
    response = await workflow_client.get(f"/workflows/{created['id']}")
    assert response.json()["name"] == "My Workflow"


async def test_get_workflow_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get("/workflows/nonexistent")
    assert response.status_code == 404


# ---------- patch ----------


async def test_update_workflow_returns_200(workflow_client: AsyncClient) -> None:
    skill = await _create_skill(workflow_client)
    created = await _create_workflow(workflow_client, skill["id"])
    response = await workflow_client.patch(
        f"/workflows/{created['id']}", json={"name": "Renamed"}
    )
    assert response.status_code == 200


async def test_update_workflow_partial_update_leaves_other_fields_unchanged(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    created = await _create_workflow(workflow_client, skill["id"])
    response = await workflow_client.patch(
        f"/workflows/{created['id']}", json={"name": "Renamed"}
    )
    assert response.json()["prompt"] == _WF_BODY["prompt"]


async def test_update_workflow_updates_agent_skill_id(
    workflow_client: AsyncClient,
) -> None:
    skill1 = await _create_skill(workflow_client)
    skill2 = (
        await workflow_client.post(
            "/agent-skills",
            json={"name": "Skill B", "repo_url": "https://github.com/x/z"},
        )
    ).json()
    created = await _create_workflow(workflow_client, skill1["id"])
    response = await workflow_client.patch(
        f"/workflows/{created['id']}", json={"agent_skill_id": skill2["id"]}
    )
    assert response.json()["agent_skill_id"] == skill2["id"]


async def test_update_workflow_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.patch("/workflows/nonexistent", json={"name": "X"})
    assert response.status_code == 404


# ---------- delete ----------


async def test_delete_workflow_returns_204(workflow_client: AsyncClient) -> None:
    skill = await _create_skill(workflow_client)
    created = await _create_workflow(workflow_client, skill["id"])
    response = await workflow_client.delete(f"/workflows/{created['id']}")
    assert response.status_code == 204


async def test_delete_workflow_removes_from_list(workflow_client: AsyncClient) -> None:
    skill = await _create_skill(workflow_client)
    created = await _create_workflow(workflow_client, skill["id"])
    await workflow_client.delete(f"/workflows/{created['id']}")
    response = await workflow_client.get("/workflows")
    assert response.json() == []


async def test_delete_workflow_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.delete("/workflows/nonexistent")
    assert response.status_code == 404


async def test_delete_agent_skill_returns_409_when_used_by_workflow(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    await _create_workflow(workflow_client, skill["id"])
    response = await workflow_client.delete(f"/agent-skills/{skill['id']}")
    assert response.status_code == 409


# ---------- created_by / updated_by ----------


async def test_create_workflow_populates_created_and_updated_by_from_header(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    response = await workflow_client.post(
        "/workflows",
        json={**_WF_BODY, "agent_skill_id": skill["id"]},
        headers={"X-User-Id": "alice"},
    )
    body = response.json()
    assert body["created_by"] == "alice"
    assert body["updated_by"] == "alice"


async def test_create_workflow_without_header_defaults_to_empty_string(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    response = await workflow_client.post(
        "/workflows", json={**_WF_BODY, "agent_skill_id": skill["id"]}
    )
    body = response.json()
    assert body["created_by"] == ""
    assert body["updated_by"] == ""


async def test_update_workflow_preserves_created_by_and_overwrites_updated_by(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    created = (
        await workflow_client.post(
            "/workflows",
            json={**_WF_BODY, "agent_skill_id": skill["id"]},
            headers={"X-User-Id": "alice"},
        )
    ).json()
    response = await workflow_client.patch(
        f"/workflows/{created['id']}",
        json={"name": "Renamed"},
        headers={"X-User-Id": "bob"},
    )
    body = response.json()
    assert body["created_by"] == "alice"
    assert body["updated_by"] == "bob"
