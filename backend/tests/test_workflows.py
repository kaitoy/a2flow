from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from httpx import AsyncClient

from models.secret import Secret as _Secret  # noqa: F401 — registers model
from tests._envelope import assert_err, assert_ok

_SKILL_BODY = {"name": "skill-a", "repo_url": "https://github.com/x/y"}
_WF_BODY = {"name": "my-workflow", "prompt": "Do the thing"}


async def _create_skill(client: AsyncClient) -> Any:
    return assert_ok(
        await client.post("/api/v1/agent-skills", json=_SKILL_BODY), status=201
    )


async def _create_workflow(
    client: AsyncClient, skill_id: str, **overrides: object
) -> Any:
    body = {**_WF_BODY, "agent_skill_id": skill_id, **overrides}
    return assert_ok(await client.post("/api/v1/workflows", json=body), status=201)


# ---------- create ----------


async def test_create_workflow_returns_201(workflow_client: AsyncClient) -> None:
    skill = await _create_skill(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflows", json={**_WF_BODY, "agent_skill_id": skill["id"]}
    )
    assert response.status_code == 201


async def test_create_workflow_response_has_id(workflow_client: AsyncClient) -> None:
    skill = await _create_skill(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflows", json={**_WF_BODY, "agent_skill_id": skill["id"]}
    )
    assert "id" in assert_ok(response, status=201)


async def test_create_workflow_response_has_correct_name(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflows", json={**_WF_BODY, "agent_skill_id": skill["id"]}
    )
    assert assert_ok(response, status=201)["name"] == "my-workflow"


async def test_create_workflow_missing_name_returns_422(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflows", json={"prompt": "p", "agent_skill_id": skill["id"]}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_workflow_missing_prompt_returns_422(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflows", json={"name": "wf", "agent_skill_id": skill["id"]}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_workflow_missing_agent_skill_id_returns_422(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.post("/api/v1/workflows", json=_WF_BODY)
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_workflow_unknown_agent_skill_id_returns_422(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.post(
        "/api/v1/workflows", json={**_WF_BODY, "agent_skill_id": "nonexistent"}
    )
    assert_err(response, code="FOREIGN_KEY_VIOLATION", status=422)


# ---------- list ----------


async def test_list_workflows_empty_initially(workflow_client: AsyncClient) -> None:
    response = await workflow_client.get("/api/v1/workflows")
    assert assert_ok(response) == []


async def test_list_workflows_returns_created_workflow(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    await _create_workflow(workflow_client, skill["id"])
    response = await workflow_client.get("/api/v1/workflows")
    assert len(assert_ok(response)) == 1


async def test_list_workflows_respects_limit_param(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    for i in range(3):
        await _create_workflow(workflow_client, skill["id"], name=f"wf-{i}")
    response = await workflow_client.get("/api/v1/workflows", params={"limit": 2})
    assert len(assert_ok(response)) == 2


async def test_list_workflows_respects_offset_param(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    for i in range(3):
        await _create_workflow(workflow_client, skill["id"], name=f"wf-{i}")
    response = await workflow_client.get(
        "/api/v1/workflows", params={"limit": 10, "offset": 2}
    )
    assert len(assert_ok(response)) == 1


# ---------- sort & filter ----------


async def test_list_workflows_sort_by_name_asc(workflow_client: AsyncClient) -> None:
    skill = await _create_skill(workflow_client)
    for name in ("Charlie", "Alpha", "Bravo"):
        await _create_workflow(workflow_client, skill["id"], name=name)
    response = await workflow_client.get("/api/v1/workflows", params={"s": "name"})
    names = [w["name"] for w in assert_ok(response)]
    assert names == ["Alpha", "Bravo", "Charlie"]


async def test_list_workflows_filter_eq_by_name(workflow_client: AsyncClient) -> None:
    skill = await _create_skill(workflow_client)
    for name in ("Alpha", "Bravo"):
        await _create_workflow(workflow_client, skill["id"], name=name)
    response = await workflow_client.get(
        "/api/v1/workflows", params={"q": "name:eq:Bravo"}
    )
    assert [w["name"] for w in assert_ok(response)] == ["Bravo"]


async def test_list_workflows_filter_createdat_gte_returns_all(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    for name in ("Alpha", "Bravo"):
        await _create_workflow(workflow_client, skill["id"], name=name)
    response = await workflow_client.get(
        "/api/v1/workflows", params={"q": "createdAt:gte:2000-01-01T00:00:00Z"}
    )
    assert len(assert_ok(response)) == 2


async def test_list_workflows_filter_createdat_gt_future_returns_none(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    await _create_workflow(workflow_client, skill["id"], name="Alpha")
    response = await workflow_client.get(
        "/api/v1/workflows", params={"q": "createdAt:gt:2999-01-01T00:00:00Z"}
    )
    assert assert_ok(response) == []


async def test_list_workflows_invalid_filter_field_returns_400(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get(
        "/api/v1/workflows", params={"q": "bogus:eq:x"}
    )
    assert_err(response, code="INVALID_QUERY", status=400)


# ---------- get ----------


async def test_get_workflow_returns_200(workflow_client: AsyncClient) -> None:
    skill = await _create_skill(workflow_client)
    created = await _create_workflow(workflow_client, skill["id"])
    response = await workflow_client.get(f"/api/v1/workflows/{created['id']}")
    assert response.status_code == 200


async def test_get_workflow_returns_correct_data(workflow_client: AsyncClient) -> None:
    skill = await _create_skill(workflow_client)
    created = await _create_workflow(workflow_client, skill["id"])
    response = await workflow_client.get(f"/api/v1/workflows/{created['id']}")
    assert assert_ok(response)["name"] == "my-workflow"


async def test_get_workflow_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get("/api/v1/workflows/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- patch ----------


async def test_update_workflow_returns_200(workflow_client: AsyncClient) -> None:
    skill = await _create_skill(workflow_client)
    created = await _create_workflow(workflow_client, skill["id"])
    response = await workflow_client.patch(
        f"/api/v1/workflows/{created['id']}", json={"name": "Renamed"}
    )
    assert response.status_code == 200


async def test_update_workflow_partial_update_leaves_other_fields_unchanged(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    created = await _create_workflow(workflow_client, skill["id"])
    response = await workflow_client.patch(
        f"/api/v1/workflows/{created['id']}", json={"name": "Renamed"}
    )
    assert assert_ok(response)["prompt"] == _WF_BODY["prompt"]


async def test_update_workflow_updates_agent_skill_id(
    workflow_client: AsyncClient,
) -> None:
    skill1 = await _create_skill(workflow_client)
    skill2 = assert_ok(
        await workflow_client.post(
            "/api/v1/agent-skills",
            json={"name": "skill-b", "repo_url": "https://github.com/x/z"},
        ),
        status=201,
    )
    created = await _create_workflow(workflow_client, skill1["id"])
    response = await workflow_client.patch(
        f"/api/v1/workflows/{created['id']}", json={"agent_skill_id": skill2["id"]}
    )
    assert assert_ok(response)["agentSkillId"] == skill2["id"]


async def test_update_workflow_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.patch(
        "/api/v1/workflows/nonexistent", json={"name": "X"}
    )
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- delete ----------


async def test_delete_workflow_returns_200(workflow_client: AsyncClient) -> None:
    skill = await _create_skill(workflow_client)
    created = await _create_workflow(workflow_client, skill["id"])
    response = await workflow_client.delete(f"/api/v1/workflows/{created['id']}")
    assert assert_ok(response, status=200) is None


async def test_delete_workflow_removes_from_list(workflow_client: AsyncClient) -> None:
    skill = await _create_skill(workflow_client)
    created = await _create_workflow(workflow_client, skill["id"])
    await workflow_client.delete(f"/api/v1/workflows/{created['id']}")
    response = await workflow_client.get("/api/v1/workflows")
    assert assert_ok(response) == []


async def test_delete_workflow_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.delete("/api/v1/workflows/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


async def test_delete_agent_skill_returns_409_when_used_by_workflow(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    await _create_workflow(workflow_client, skill["id"])
    response = await workflow_client.delete(f"/api/v1/agent-skills/{skill['id']}")
    assert_err(response, code="CONFLICT_REFERENCED", status=409)


# ---------- created_by / updated_by ----------


async def test_create_workflow_populates_created_and_updated_by_from_header(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflows",
        json={**_WF_BODY, "agent_skill_id": skill["id"]},
        headers={"X-User-Id": "alice"},
    )
    body = assert_ok(response, status=201)
    assert body["createdBy"] == "alice"
    assert body["updatedBy"] == "alice"


async def test_create_workflow_with_unknown_user_returns_422(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflows",
        json={**_WF_BODY, "agent_skill_id": skill["id"]},
        headers={"X-User-Id": "ghost-user"},
    )
    assert_err(response, code="FOREIGN_KEY_VIOLATION", status=422)


async def test_update_workflow_preserves_created_by_and_overwrites_updated_by(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    created = assert_ok(
        await workflow_client.post(
            "/api/v1/workflows",
            json={**_WF_BODY, "agent_skill_id": skill["id"]},
            headers={"X-User-Id": "alice"},
        ),
        status=201,
    )
    response = await workflow_client.patch(
        f"/api/v1/workflows/{created['id']}",
        json={"name": "Renamed"},
        headers={"X-User-Id": "bob"},
    )
    body = assert_ok(response)
    assert body["createdBy"] == "alice"
    assert body["updatedBy"] == "bob"


# ---------- execute ----------


async def test_execute_workflow_returns_201_with_workflow_session(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    wf = await _create_workflow(workflow_client, skill["id"])
    response = await workflow_client.post(f"/api/v1/workflows/{wf['id']}/execute")
    body = assert_ok(response, status=201)
    assert "id" in body
    assert "sessionId" in body
    assert body["workflowName"] == "my-workflow"


async def test_execute_workflow_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.post("/api/v1/workflows/nonexistent/execute")
    assert_err(response, code="NOT_FOUND", status=404)


async def test_execute_workflow_clones_skill_repo(
    workflow_client: AsyncClient,
    mock_skill_manager: MagicMock,
) -> None:
    skill = await _create_skill(workflow_client)
    wf = await _create_workflow(workflow_client, skill["id"])

    captured_ids: list[str] = []

    async def _capture(s: Any, auth: Any = None) -> Any:
        captured_ids.append(s.id)
        return Path("/tmp/skill")

    mock_skill_manager.ensure_cloned.side_effect = _capture

    await workflow_client.post(f"/api/v1/workflows/{wf['id']}/execute")
    mock_skill_manager.ensure_cloned.assert_awaited_once()
    assert captured_ids[0] == skill["id"]


async def test_execute_workflow_passes_repo_auth_to_clone(
    workflow_client: AsyncClient,
    mock_skill_manager: MagicMock,
) -> None:
    """A skill with repo_auth_secret resolves it and clones with credentials."""
    assert_ok(
        await workflow_client.post(
            "/api/v1/secrets",
            json={"name": "git-token", "type": "local", "value": "tok-123"},
        ),
        status=201,
    )
    skill = assert_ok(
        await workflow_client.post(
            "/api/v1/agent-skills",
            json={**_SKILL_BODY, "repo_auth_secret": "git-token"},
        ),
        status=201,
    )
    wf = await _create_workflow(workflow_client, skill["id"])

    captured_auth: list[Any] = []

    async def _capture(s: Any, auth: Any = None) -> Any:
        captured_auth.append(auth)
        return Path("/tmp/skill")

    mock_skill_manager.ensure_cloned.side_effect = _capture

    response = await workflow_client.post(f"/api/v1/workflows/{wf['id']}/execute")
    assert_ok(response, status=201)
    assert captured_auth == [("x-access-token", "tok-123")]


async def test_execute_workflow_with_missing_auth_secret_returns_502(
    workflow_client: AsyncClient,
    mock_skill_manager: MagicMock,
) -> None:
    """A dangling repo_auth_secret fails lazily at execute time with 502."""
    assert_ok(
        await workflow_client.post(
            "/api/v1/secrets",
            json={"name": "doomed", "type": "local", "value": "tok"},
        ),
        status=201,
    )
    skill = assert_ok(
        await workflow_client.post(
            "/api/v1/agent-skills",
            json={**_SKILL_BODY, "repo_auth_secret": "doomed"},
        ),
        status=201,
    )
    wf = await _create_workflow(workflow_client, skill["id"])
    secrets = assert_ok(await workflow_client.get("/api/v1/secrets"))
    await workflow_client.delete(f"/api/v1/secrets/{secrets[0]['id']}")

    response = await workflow_client.post(f"/api/v1/workflows/{wf['id']}/execute")
    err = assert_err(response, code="SECRET_RESOLUTION_FAILED", status=502)
    assert err["details"] == {"secret": "doomed"}
    mock_skill_manager.ensure_cloned.assert_not_awaited()


async def test_execute_workflow_snapshot_contains_skill_info(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    wf = await _create_workflow(workflow_client, skill["id"])
    response = await workflow_client.post(f"/api/v1/workflows/{wf['id']}/execute")
    body = assert_ok(response, status=201)
    assert body["agentSkillId"] == skill["id"]
    assert body["agentSkillName"] == skill["name"]
    assert body["workflowPrompt"] == _WF_BODY["prompt"]


async def test_execute_workflow_uses_user_header(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    wf = await _create_workflow(workflow_client, skill["id"])
    response = await workflow_client.post(
        f"/api/v1/workflows/{wf['id']}/execute",
        headers={"X-User-Id": "alice"},
    )
    body = assert_ok(response, status=201)
    assert body["userId"] == "alice"
