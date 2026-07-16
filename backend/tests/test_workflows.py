from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

from models.secret import Secret as _Secret  # noqa: F401 — registers model
from tests._envelope import assert_err, assert_ok
from tests._workflow import (
    GENERATE_BODY,
    add_template,
    create_published_workflow,
    create_skill,
    generate_workflow,
    publish_workflow,
)
from tests.conftest import FAKE_COMMIT_SHA

# ---------- generate ----------


async def test_generate_workflow_returns_201(workflow_client: AsyncClient) -> None:
    skill = await create_skill(workflow_client)
    response = await workflow_client.post(
        f"/api/v1/agent-skills/{skill['id']}/workflows", json=GENERATE_BODY
    )
    assert response.status_code == 201


async def test_generate_workflow_response_is_generating(
    workflow_client: AsyncClient,
) -> None:
    """The response is the freshly registered row, before the background job ran."""
    skill = await create_skill(workflow_client)
    response = await workflow_client.post(
        f"/api/v1/agent-skills/{skill['id']}/workflows", json=GENERATE_BODY
    )
    body = assert_ok(response, status=201)
    assert body["name"] == "my-workflow"
    assert body["status"] == "generating"
    assert "prompt" not in body


async def test_generate_workflow_schedules_generation_job(
    workflow_client: AsyncClient, mock_generation_job: AsyncMock
) -> None:
    """The prompt is handed to the background job, not stored on the workflow."""
    skill = await create_skill(workflow_client)
    wf = await generate_workflow(workflow_client, skill["id"])
    mock_generation_job.assert_awaited_once()
    assert mock_generation_job.await_args is not None
    assert mock_generation_job.await_args.args == (wf["id"], GENERATE_BODY["prompt"])


async def test_generate_workflow_becomes_draft_after_job(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    wf = await generate_workflow(workflow_client, skill["id"])
    body = assert_ok(await workflow_client.get(f"/api/v1/workflows/{wf['id']}"))
    assert body["status"] == "draft"


async def test_generate_workflow_creates_planning_session(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    wf = await generate_workflow(workflow_client, skill["id"])
    ps = assert_ok(
        await workflow_client.get(f"/api/v1/workflows/{wf['id']}/planning-session")
    )
    assert ps["workflowId"] == wf["id"]
    assert ps["agentSkillId"] == skill["id"]
    assert ps["agentSkillCommitSha"] == FAKE_COMMIT_SHA


async def test_generate_workflow_missing_name_returns_422(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    response = await workflow_client.post(
        f"/api/v1/agent-skills/{skill['id']}/workflows", json={"prompt": "p"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_generate_workflow_missing_prompt_returns_422(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    response = await workflow_client.post(
        f"/api/v1/agent-skills/{skill['id']}/workflows", json={"name": "wf"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_generate_workflow_unknown_skill_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.post(
        "/api/v1/agent-skills/nonexistent/workflows", json=GENERATE_BODY
    )
    assert_err(response, code="NOT_FOUND", status=404)


async def test_generate_workflow_with_unpublished_skill_returns_409(
    workflow_client: AsyncClient, mock_sync_job: AsyncMock
) -> None:
    """A skill whose clone has not published a revision cannot plan a workflow."""
    mock_sync_job.side_effect = None  # the clone never publishes anything
    skill = await create_skill(workflow_client)
    response = await workflow_client.post(
        f"/api/v1/agent-skills/{skill['id']}/workflows", json=GENERATE_BODY
    )
    err = assert_err(response, code="SKILL_NOT_READY", status=409)
    assert err["details"] == {"skillId": skill["id"]}


async def test_generate_workflow_duplicate_name_returns_409(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    await generate_workflow(workflow_client, skill["id"])
    response = await workflow_client.post(
        f"/api/v1/agent-skills/{skill['id']}/workflows", json=GENERATE_BODY
    )
    assert_err(response, code="CONFLICT_UNIQUE", status=409)


# ---------- list ----------


async def test_list_workflows_empty_initially(workflow_client: AsyncClient) -> None:
    response = await workflow_client.get("/api/v1/workflows")
    assert assert_ok(response) == []


async def test_list_workflows_returns_created_workflow(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    await generate_workflow(workflow_client, skill["id"])
    response = await workflow_client.get("/api/v1/workflows")
    assert len(assert_ok(response)) == 1


async def test_list_workflows_respects_limit_param(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    for i in range(3):
        await generate_workflow(workflow_client, skill["id"], name=f"wf-{i}")
    response = await workflow_client.get("/api/v1/workflows", params={"limit": 2})
    assert len(assert_ok(response)) == 2


async def test_list_workflows_respects_offset_param(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    for i in range(3):
        await generate_workflow(workflow_client, skill["id"], name=f"wf-{i}")
    response = await workflow_client.get(
        "/api/v1/workflows", params={"limit": 10, "offset": 2}
    )
    assert len(assert_ok(response)) == 1


# ---------- sort & filter ----------


async def test_list_workflows_sort_by_name_asc(workflow_client: AsyncClient) -> None:
    skill = await create_skill(workflow_client)
    for name in ("Charlie", "Alpha", "Bravo"):
        await generate_workflow(workflow_client, skill["id"], name=name)
    response = await workflow_client.get("/api/v1/workflows", params={"s": "name"})
    names = [w["name"] for w in assert_ok(response)]
    assert names == ["Alpha", "Bravo", "Charlie"]


async def test_list_workflows_filter_eq_by_name(workflow_client: AsyncClient) -> None:
    skill = await create_skill(workflow_client)
    for name in ("Alpha", "Bravo"):
        await generate_workflow(workflow_client, skill["id"], name=name)
    response = await workflow_client.get(
        "/api/v1/workflows", params={"q": "name:eq:Bravo"}
    )
    assert [w["name"] for w in assert_ok(response)] == ["Bravo"]


async def test_list_workflows_filter_createdat_gte_returns_all(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    for name in ("Alpha", "Bravo"):
        await generate_workflow(workflow_client, skill["id"], name=name)
    response = await workflow_client.get(
        "/api/v1/workflows", params={"q": "createdAt:gte:2000-01-01T00:00:00Z"}
    )
    assert len(assert_ok(response)) == 2


async def test_list_workflows_filter_createdat_gt_future_returns_none(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    await generate_workflow(workflow_client, skill["id"], name="Alpha")
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
    skill = await create_skill(workflow_client)
    created = await generate_workflow(workflow_client, skill["id"])
    response = await workflow_client.get(f"/api/v1/workflows/{created['id']}")
    assert response.status_code == 200


async def test_get_workflow_returns_correct_data(workflow_client: AsyncClient) -> None:
    skill = await create_skill(workflow_client)
    created = await generate_workflow(workflow_client, skill["id"])
    response = await workflow_client.get(f"/api/v1/workflows/{created['id']}")
    assert assert_ok(response)["name"] == "my-workflow"


async def test_get_workflow_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get("/api/v1/workflows/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- create removed ----------


async def test_post_workflows_is_removed(workflow_client: AsyncClient) -> None:
    """Workflows are born from generation only; the bare POST no longer exists."""
    response = await workflow_client.post(
        "/api/v1/workflows", json={"name": "wf", "agent_skill_id": "x"}
    )
    assert response.status_code == 405


# ---------- patch ----------


async def test_update_workflow_returns_200(workflow_client: AsyncClient) -> None:
    skill = await create_skill(workflow_client)
    created = await generate_workflow(workflow_client, skill["id"])
    response = await workflow_client.patch(
        f"/api/v1/workflows/{created['id']}", json={"name": "Renamed"}
    )
    assert response.status_code == 200


async def test_update_workflow_partial_update_leaves_other_fields_unchanged(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    created = await generate_workflow(workflow_client, skill["id"])
    response = await workflow_client.patch(
        f"/api/v1/workflows/{created['id']}", json={"description": "About this"}
    )
    body = assert_ok(response)
    assert body["name"] == "my-workflow"
    assert body["description"] == "About this"


async def test_update_workflow_cannot_change_agent_skill_id(
    workflow_client: AsyncClient,
) -> None:
    """The bound skill is fixed at generation time; PATCH ignores the field."""
    skill1 = await create_skill(workflow_client)
    skill2 = await create_skill(
        workflow_client, name="skill-b", repo_url="https://github.com/x/z"
    )
    created = await generate_workflow(workflow_client, skill1["id"])
    response = await workflow_client.patch(
        f"/api/v1/workflows/{created['id']}", json={"agent_skill_id": skill2["id"]}
    )
    assert assert_ok(response)["agentSkillId"] == skill1["id"]


async def test_update_workflow_cannot_change_status(
    workflow_client: AsyncClient,
) -> None:
    """``status`` is server-managed (generation/publish); PATCH ignores it."""
    skill = await create_skill(workflow_client)
    created = await generate_workflow(workflow_client, skill["id"])
    response = await workflow_client.patch(
        f"/api/v1/workflows/{created['id']}", json={"status": "published"}
    )
    assert assert_ok(response)["status"] == "draft"


async def test_update_workflow_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.patch(
        "/api/v1/workflows/nonexistent", json={"name": "X"}
    )
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- delete ----------


async def test_delete_workflow_returns_200(workflow_client: AsyncClient) -> None:
    skill = await create_skill(workflow_client)
    created = await generate_workflow(workflow_client, skill["id"])
    response = await workflow_client.delete(f"/api/v1/workflows/{created['id']}")
    assert assert_ok(response, status=200) is None


async def test_delete_workflow_removes_from_list(workflow_client: AsyncClient) -> None:
    skill = await create_skill(workflow_client)
    created = await generate_workflow(workflow_client, skill["id"])
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
    skill = await create_skill(workflow_client)
    await generate_workflow(workflow_client, skill["id"])
    response = await workflow_client.delete(f"/api/v1/agent-skills/{skill['id']}")
    assert_err(response, code="CONFLICT_REFERENCED", status=409)


# ---------- created_by / updated_by ----------


async def test_generate_workflow_populates_created_and_updated_by_from_header(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    response = await workflow_client.post(
        f"/api/v1/agent-skills/{skill['id']}/workflows",
        json=GENERATE_BODY,
        headers={"X-User-Id": "alice"},
    )
    body = assert_ok(response, status=201)
    assert body["createdBy"] == "alice"
    assert body["updatedBy"] == "alice"


async def test_generate_workflow_with_unknown_user_returns_422(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    response = await workflow_client.post(
        f"/api/v1/agent-skills/{skill['id']}/workflows",
        json=GENERATE_BODY,
        headers={"X-User-Id": "ghost-user"},
    )
    assert_err(response, code="FOREIGN_KEY_VIOLATION", status=422)


async def test_update_workflow_preserves_created_by_and_overwrites_updated_by(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    created = assert_ok(
        await workflow_client.post(
            f"/api/v1/agent-skills/{skill['id']}/workflows",
            json=GENERATE_BODY,
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


# ---------- publish ----------


async def test_publish_workflow_without_templates_returns_409(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    wf = await generate_workflow(workflow_client, skill["id"])
    response = await workflow_client.post(f"/api/v1/workflows/{wf['id']}/publish")
    err = assert_err(response, code="WORKFLOW_NOT_RUNNABLE", status=409)
    assert err["details"]["workflowId"] == wf["id"]


async def test_publish_workflow_while_generating_returns_409(
    workflow_client: AsyncClient, mock_generation_job: AsyncMock
) -> None:
    mock_generation_job.side_effect = None  # the generation run never finishes
    skill = await create_skill(workflow_client)
    wf = await generate_workflow(workflow_client, skill["id"])
    await add_template(workflow_client, wf["id"])
    response = await workflow_client.post(f"/api/v1/workflows/{wf['id']}/publish")
    assert_err(response, code="WORKFLOW_NOT_RUNNABLE", status=409)


async def test_publish_workflow_sets_status_published(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    wf = await generate_workflow(workflow_client, skill["id"])
    await add_template(workflow_client, wf["id"])
    body = await publish_workflow(workflow_client, wf["id"])
    assert body["status"] == "published"


async def test_publish_workflow_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.post("/api/v1/workflows/nonexistent/publish")
    assert_err(response, code="NOT_FOUND", status=404)


async def test_republish_after_adjustment_is_allowed(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    wf = await create_published_workflow(workflow_client, skill["id"])
    await add_template(workflow_client, wf["id"], title="Extra step")
    body = await publish_workflow(workflow_client, wf["id"])
    assert body["status"] == "published"


# ---------- execute ----------


async def test_execute_workflow_returns_201_with_workflow_session(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    wf = await create_published_workflow(workflow_client, skill["id"])
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


async def test_execute_unpublished_workflow_returns_409(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    wf = await generate_workflow(workflow_client, skill["id"])
    await add_template(workflow_client, wf["id"])
    response = await workflow_client.post(f"/api/v1/workflows/{wf['id']}/execute")
    err = assert_err(response, code="WORKFLOW_NOT_RUNNABLE", status=409)
    assert err["details"]["workflowId"] == wf["id"]


async def test_execute_workflow_does_not_clone(
    workflow_client: AsyncClient,
    mock_skill_manager: MagicMock,
) -> None:
    """Cloning happens at registration and on pull, never on the hot path of a run."""
    skill = await create_skill(workflow_client)
    wf = await create_published_workflow(workflow_client, skill["id"])

    assert_ok(
        await workflow_client.post(f"/api/v1/workflows/{wf['id']}/execute"), status=201
    )

    mock_skill_manager.clone.assert_not_awaited()


async def test_execute_workflow_pins_the_skills_published_revision(
    workflow_client: AsyncClient,
) -> None:
    """The session records the revision it started against, not a local path.

    That is what lets any replica resolve the same code later, and what keeps a
    later pull of the skill from swapping the code out from under the run.
    """
    skill = await create_skill(workflow_client)
    wf = await create_published_workflow(workflow_client, skill["id"])

    body = assert_ok(
        await workflow_client.post(f"/api/v1/workflows/{wf['id']}/execute"), status=201
    )

    assert body["agentSkillCommitSha"] == FAKE_COMMIT_SHA
    assert "skillDir" not in body


async def test_execute_workflow_snapshot_contains_skill_info(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    wf = await create_published_workflow(workflow_client, skill["id"])
    response = await workflow_client.post(f"/api/v1/workflows/{wf['id']}/execute")
    body = assert_ok(response, status=201)
    assert body["agentSkillId"] == skill["id"]
    assert body["agentSkillName"] == skill["name"]
    assert "workflowPrompt" not in body


async def test_execute_workflow_uses_user_header(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    wf = await create_published_workflow(workflow_client, skill["id"])
    response = await workflow_client.post(
        f"/api/v1/workflows/{wf['id']}/execute",
        headers={"X-User-Id": "alice"},
    )
    body = assert_ok(response, status=201)
    assert body["userId"] == "alice"


async def test_execute_workflow_copies_templates_into_session_tasks(
    workflow_client: AsyncClient,
) -> None:
    """Templates become pending session tasks, with dependency ids remapped."""
    skill = await create_skill(workflow_client)
    wf = await generate_workflow(workflow_client, skill["id"])
    first = await add_template(workflow_client, wf["id"], title="First")
    second = await add_template(
        workflow_client, wf["id"], title="Second", depends_on_ids=[first["id"]]
    )
    await publish_workflow(workflow_client, wf["id"])

    ws = assert_ok(
        await workflow_client.post(f"/api/v1/workflows/{wf['id']}/execute"), status=201
    )
    tasks = assert_ok(
        await workflow_client.get(
            f"/api/v1/workflow-sessions/{ws['id']}/workflow-tasks"
        )
    )

    assert [t["title"] for t in tasks] == ["First", "Second"]
    assert all(t["status"] == "pending" for t in tasks)
    by_title = {t["title"]: t for t in tasks}
    assert by_title["Second"]["dependsOnIds"] == [by_title["First"]["id"]]
    # The copies reference the run's tasks, not the workflow's templates.
    assert by_title["First"]["id"] != first["id"]
    assert by_title["Second"]["dependsOnIds"] != [second["dependsOnIds"]]


async def test_execute_twice_creates_independent_task_copies(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    wf = await create_published_workflow(workflow_client, skill["id"])
    ws1 = assert_ok(
        await workflow_client.post(f"/api/v1/workflows/{wf['id']}/execute"), status=201
    )
    ws2 = assert_ok(
        await workflow_client.post(f"/api/v1/workflows/{wf['id']}/execute"), status=201
    )
    tasks1 = assert_ok(
        await workflow_client.get(
            f"/api/v1/workflow-sessions/{ws1['id']}/workflow-tasks"
        )
    )
    tasks2 = assert_ok(
        await workflow_client.get(
            f"/api/v1/workflow-sessions/{ws2['id']}/workflow-tasks"
        )
    )
    assert len(tasks1) == len(tasks2) == 1
    assert tasks1[0]["id"] != tasks2[0]["id"]
