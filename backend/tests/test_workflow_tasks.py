"""Integration tests for the WorkflowTask CRUD endpoints."""

import itertools
from typing import Any

from httpx import AsyncClient

from tests._envelope import assert_err, assert_ok

_WF_PROMPT = "Do the thing"
_uniq = itertools.count()


def _next_suffix() -> int:
    """Return a per-process monotonic int used to keep names unique across helper calls."""
    return next(_uniq)


async def _create_workflow_session(client: AsyncClient) -> Any:
    """Create a fresh skill + workflow and execute it to produce a WorkflowSession.

    A monotonic suffix is appended to the skill and workflow names so callers can
    invoke this multiple times within a single test (e.g., to verify per-session
    filtering) without tripping UNIQUE constraints on ``agent_skills.name`` or
    ``workflows.name``.
    """
    n = _next_suffix()
    skill = assert_ok(
        await client.post(
            "/api/v1/agent-skills",
            json={"name": f"Skill {n}", "repo_url": f"https://github.com/x/y{n}"},
        ),
        status=201,
    )
    wf = assert_ok(
        await client.post(
            "/api/v1/workflows",
            json={
                "name": f"Workflow {n}",
                "prompt": _WF_PROMPT,
                "agent_skill_id": skill["id"],
            },
        ),
        status=201,
    )
    return assert_ok(
        await client.post(f"/api/v1/workflows/{wf['id']}/execute"), status=201
    )


async def _create_task(
    client: AsyncClient,
    ws_id: str,
    *,
    title: str = "Step",
    position: int = 0,
    headers: dict[str, str] | None = None,
    **extra: object,
) -> Any:
    body = {"workflowSessionId": ws_id, "title": title, "position": position, **extra}
    return assert_ok(
        await client.post("/api/v1/workflow-tasks", json=body, headers=headers or {}),
        status=201,
    )


# ---------- create ----------


async def test_create_task_returns_201(workflow_client: AsyncClient) -> None:
    ws = await _create_workflow_session(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflow-tasks",
        json={"workflowSessionId": ws["id"], "title": "Step 1", "position": 0},
    )
    assert response.status_code == 201


async def test_create_task_response_contains_expected_fields(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflow-tasks",
        json={
            "workflowSessionId": ws["id"],
            "title": "Step 1",
            "description": "Outline the doc",
            "position": 0,
        },
    )
    body = assert_ok(response, status=201)
    assert body["id"]
    assert body["workflowSessionId"] == ws["id"]
    assert body["title"] == "Step 1"
    assert body["description"] == "Outline the doc"
    assert body["status"] == "pending"
    assert body["position"] == 0


async def test_create_task_defaults_status_to_pending(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    body = await _create_task(workflow_client, ws["id"])
    assert body["status"] == "pending"


async def test_create_task_missing_title_returns_422(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflow-tasks",
        json={"workflowSessionId": ws["id"]},
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_task_missing_session_id_returns_422(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.post(
        "/api/v1/workflow-tasks", json={"title": "Step 1"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_create_task_unknown_session_returns_422(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.post(
        "/api/v1/workflow-tasks",
        json={"workflowSessionId": "nonexistent", "title": "Step 1"},
    )
    assert_err(response, code="FOREIGN_KEY_VIOLATION", status=422)


async def test_create_task_invalid_status_returns_422(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflow-tasks",
        json={
            "workflowSessionId": ws["id"],
            "title": "Step 1",
            "status": "bogus",
        },
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


# ---------- list via nested endpoint ----------


async def test_list_session_tasks_empty_initially(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    response = await workflow_client.get(
        f"/api/v1/workflow-sessions/{ws['id']}/workflow-tasks"
    )
    assert assert_ok(response) == []


async def test_list_session_tasks_returns_created_tasks(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    await _create_task(workflow_client, ws["id"], title="t1")
    await _create_task(workflow_client, ws["id"], title="t2", position=1)
    response = await workflow_client.get(
        f"/api/v1/workflow-sessions/{ws['id']}/workflow-tasks"
    )
    assert len(assert_ok(response)) == 2


async def test_list_session_tasks_ordered_by_position_then_created_at(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    # Insert out of order; the API must sort by position ASC then created_at ASC.
    await _create_task(workflow_client, ws["id"], title="b", position=2)
    await _create_task(workflow_client, ws["id"], title="a", position=1)
    await _create_task(workflow_client, ws["id"], title="c", position=2)
    response = await workflow_client.get(
        f"/api/v1/workflow-sessions/{ws['id']}/workflow-tasks"
    )
    titles = [t["title"] for t in assert_ok(response)]
    assert titles == ["a", "b", "c"]


async def test_list_session_tasks_only_returns_tasks_for_that_session(
    workflow_client: AsyncClient,
) -> None:
    ws1 = await _create_workflow_session(workflow_client)
    ws2 = await _create_workflow_session(workflow_client)
    await _create_task(workflow_client, ws1["id"], title="one")
    await _create_task(workflow_client, ws2["id"], title="two")
    response = await workflow_client.get(
        f"/api/v1/workflow-sessions/{ws1['id']}/workflow-tasks"
    )
    tasks = assert_ok(response)
    assert len(tasks) == 1
    assert tasks[0]["title"] == "one"


async def test_list_session_tasks_respects_limit_param(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    for i in range(3):
        await _create_task(workflow_client, ws["id"], title=f"t{i}", position=i)
    response = await workflow_client.get(
        f"/api/v1/workflow-sessions/{ws['id']}/workflow-tasks",
        params={"limit": 2},
    )
    assert len(assert_ok(response)) == 2


async def test_list_session_tasks_unknown_session_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get(
        "/api/v1/workflow-sessions/nonexistent/workflow-tasks"
    )
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- list sort & filter ----------


async def test_list_session_tasks_filter_by_status(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    await _create_task(workflow_client, ws["id"], title="done", status="completed")
    await _create_task(workflow_client, ws["id"], title="todo", status="pending")
    response = await workflow_client.get(
        f"/api/v1/workflow-sessions/{ws['id']}/workflow-tasks",
        params={"q": "status:eq:completed"},
    )
    titles = [t["title"] for t in assert_ok(response)]
    assert titles == ["done"]


async def test_list_session_tasks_filter_status_in(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    await _create_task(workflow_client, ws["id"], title="a", status="completed")
    await _create_task(workflow_client, ws["id"], title="b", status="pending")
    await _create_task(workflow_client, ws["id"], title="c", status="failed")
    response = await workflow_client.get(
        f"/api/v1/workflow-sessions/{ws['id']}/workflow-tasks",
        params={"q": "status:in:completed,pending"},
    )
    assert len(assert_ok(response)) == 2


async def test_list_session_tasks_sort_multi_field(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    # Same position so the tie is broken by the second sort field (title).
    await _create_task(workflow_client, ws["id"], title="b", position=1)
    await _create_task(workflow_client, ws["id"], title="a", position=1)
    await _create_task(workflow_client, ws["id"], title="c", position=2)
    response = await workflow_client.get(
        f"/api/v1/workflow-sessions/{ws['id']}/workflow-tasks",
        params={"s": "position,title"},
    )
    titles = [t["title"] for t in assert_ok(response)]
    assert titles == ["a", "b", "c"]


async def test_list_session_tasks_invalid_filter_value_returns_400(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    response = await workflow_client.get(
        f"/api/v1/workflow-sessions/{ws['id']}/workflow-tasks",
        params={"q": "position:eq:notanumber"},
    )
    assert_err(response, code="INVALID_QUERY", status=400)


# ---------- get ----------


async def test_get_task_returns_200(workflow_client: AsyncClient) -> None:
    ws = await _create_workflow_session(workflow_client)
    created = await _create_task(workflow_client, ws["id"])
    response = await workflow_client.get(f"/api/v1/workflow-tasks/{created['id']}")
    assert response.status_code == 200


async def test_get_task_returns_correct_data(workflow_client: AsyncClient) -> None:
    ws = await _create_workflow_session(workflow_client)
    created = await _create_task(workflow_client, ws["id"], title="my-task")
    response = await workflow_client.get(f"/api/v1/workflow-tasks/{created['id']}")
    assert assert_ok(response)["title"] == "my-task"


async def test_get_task_unknown_id_returns_404(workflow_client: AsyncClient) -> None:
    response = await workflow_client.get("/api/v1/workflow-tasks/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- patch ----------


async def test_update_task_returns_200(workflow_client: AsyncClient) -> None:
    ws = await _create_workflow_session(workflow_client)
    created = await _create_task(workflow_client, ws["id"])
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{created['id']}", json={"status": "in_progress"}
    )
    assert response.status_code == 200


async def test_update_task_partial_update_leaves_other_fields_unchanged(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    created = await _create_task(workflow_client, ws["id"], title="kept", position=3)
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{created['id']}", json={"status": "completed"}
    )
    body = assert_ok(response)
    assert body["title"] == "kept"
    assert body["position"] == 3
    assert body["status"] == "completed"


async def test_update_task_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.patch(
        "/api/v1/workflow-tasks/nonexistent", json={"status": "completed"}
    )
    assert_err(response, code="NOT_FOUND", status=404)


async def test_update_task_invalid_status_returns_422(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    created = await _create_task(workflow_client, ws["id"])
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{created['id']}", json={"status": "bogus"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_update_task_ignores_workflow_session_id_in_body(
    workflow_client: AsyncClient,
) -> None:
    """workflow_session_id is not in WorkflowTaskUpdate, so it must not be re-parented."""
    ws1 = await _create_workflow_session(workflow_client)
    ws2 = await _create_workflow_session(workflow_client)
    created = await _create_task(workflow_client, ws1["id"])
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{created['id']}",
        json={"title": "renamed", "workflowSessionId": ws2["id"]},
    )
    body = assert_ok(response)
    assert body["title"] == "renamed"
    assert body["workflowSessionId"] == ws1["id"]


# ---------- delete ----------


async def test_delete_task_returns_200(workflow_client: AsyncClient) -> None:
    ws = await _create_workflow_session(workflow_client)
    created = await _create_task(workflow_client, ws["id"])
    response = await workflow_client.delete(f"/api/v1/workflow-tasks/{created['id']}")
    assert assert_ok(response, status=200) is None


async def test_delete_task_removes_from_list(workflow_client: AsyncClient) -> None:
    ws = await _create_workflow_session(workflow_client)
    created = await _create_task(workflow_client, ws["id"])
    await workflow_client.delete(f"/api/v1/workflow-tasks/{created['id']}")
    response = await workflow_client.get(
        f"/api/v1/workflow-sessions/{ws['id']}/workflow-tasks"
    )
    assert assert_ok(response) == []


async def test_delete_task_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.delete("/api/v1/workflow-tasks/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- dependencies (DAG) ----------


async def test_create_task_defaults_to_no_dependencies(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    body = await _create_task(workflow_client, ws["id"])
    assert body["dependsOnIds"] == []


async def test_create_task_with_dependencies_returns_them(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    a = await _create_task(workflow_client, ws["id"], title="a")
    b = await _create_task(workflow_client, ws["id"], title="b")
    body = await _create_task(
        workflow_client, ws["id"], title="c", dependsOnIds=[a["id"], b["id"]]
    )
    assert sorted(body["dependsOnIds"]) == sorted([a["id"], b["id"]])


async def test_get_task_includes_resolved_dependencies(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    a = await _create_task(workflow_client, ws["id"], title="a")
    b = await _create_task(workflow_client, ws["id"], title="b", dependsOnIds=[a["id"]])
    response = await workflow_client.get(f"/api/v1/workflow-tasks/{b['id']}")
    assert assert_ok(response)["dependsOnIds"] == [a["id"]]


async def test_list_session_tasks_include_dependencies(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    a = await _create_task(workflow_client, ws["id"], title="a", position=0)
    await _create_task(
        workflow_client, ws["id"], title="b", position=1, dependsOnIds=[a["id"]]
    )
    response = await workflow_client.get(
        f"/api/v1/workflow-sessions/{ws['id']}/workflow-tasks"
    )
    tasks = {t["title"]: t for t in assert_ok(response)}
    assert tasks["a"]["dependsOnIds"] == []
    assert tasks["b"]["dependsOnIds"] == [a["id"]]


async def test_update_task_replaces_dependencies(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    a = await _create_task(workflow_client, ws["id"], title="a")
    b = await _create_task(workflow_client, ws["id"], title="b")
    c = await _create_task(workflow_client, ws["id"], title="c", dependsOnIds=[a["id"]])
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{c['id']}", json={"dependsOnIds": [b["id"]]}
    )
    assert assert_ok(response)["dependsOnIds"] == [b["id"]]


async def test_update_task_without_depends_on_ids_leaves_edges_unchanged(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    a = await _create_task(workflow_client, ws["id"], title="a")
    b = await _create_task(workflow_client, ws["id"], title="b", dependsOnIds=[a["id"]])
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{b['id']}", json={"status": "completed"}
    )
    body = assert_ok(response)
    assert body["status"] == "completed"
    assert body["dependsOnIds"] == [a["id"]]


async def test_update_task_clears_dependencies_with_empty_list(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    a = await _create_task(workflow_client, ws["id"], title="a")
    b = await _create_task(workflow_client, ws["id"], title="b", dependsOnIds=[a["id"]])
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{b['id']}", json={"dependsOnIds": []}
    )
    assert assert_ok(response)["dependsOnIds"] == []


async def test_dependency_on_unknown_task_returns_422(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflow-tasks",
        json={
            "workflowSessionId": ws["id"],
            "title": "t",
            "dependsOnIds": ["nonexistent"],
        },
    )
    assert_err(response, code="FOREIGN_KEY_VIOLATION", status=422)


async def test_dependency_on_task_in_other_session_returns_422(
    workflow_client: AsyncClient,
) -> None:
    ws1 = await _create_workflow_session(workflow_client)
    ws2 = await _create_workflow_session(workflow_client)
    other = await _create_task(workflow_client, ws2["id"], title="other")
    response = await workflow_client.post(
        "/api/v1/workflow-tasks",
        json={
            "workflowSessionId": ws1["id"],
            "title": "t",
            "dependsOnIds": [other["id"]],
        },
    )
    assert_err(response, code="FOREIGN_KEY_VIOLATION", status=422)


async def test_self_dependency_returns_409(workflow_client: AsyncClient) -> None:
    ws = await _create_workflow_session(workflow_client)
    a = await _create_task(workflow_client, ws["id"], title="a")
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{a['id']}", json={"dependsOnIds": [a["id"]]}
    )
    assert_err(response, code="DEPENDENCY_CYCLE", status=409)


async def test_cyclic_dependency_returns_409(workflow_client: AsyncClient) -> None:
    ws = await _create_workflow_session(workflow_client)
    a = await _create_task(workflow_client, ws["id"], title="a")
    b = await _create_task(workflow_client, ws["id"], title="b", dependsOnIds=[a["id"]])
    c = await _create_task(workflow_client, ws["id"], title="c", dependsOnIds=[b["id"]])
    # a -> c would close the loop a -> c -> b -> a.
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{a['id']}", json={"dependsOnIds": [c["id"]]}
    )
    assert_err(response, code="DEPENDENCY_CYCLE", status=409)


async def test_deleting_task_cascades_dependency_edges(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    a = await _create_task(workflow_client, ws["id"], title="a")
    b = await _create_task(workflow_client, ws["id"], title="b", dependsOnIds=[a["id"]])
    await workflow_client.delete(f"/api/v1/workflow-tasks/{a['id']}")
    response = await workflow_client.get(f"/api/v1/workflow-tasks/{b['id']}")
    assert assert_ok(response)["dependsOnIds"] == []


# ---------- created_by / updated_by ----------


async def test_create_task_populates_created_and_updated_by_from_header(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflow-tasks",
        json={"workflowSessionId": ws["id"], "title": "t"},
        headers={"X-User-Id": "alice"},
    )
    body = assert_ok(response, status=201)
    assert body["createdBy"] == "alice"
    assert body["updatedBy"] == "alice"


async def test_update_task_preserves_created_by_and_overwrites_updated_by(
    workflow_client: AsyncClient,
) -> None:
    ws = await _create_workflow_session(workflow_client)
    created = assert_ok(
        await workflow_client.post(
            "/api/v1/workflow-tasks",
            json={"workflowSessionId": ws["id"], "title": "t"},
            headers={"X-User-Id": "alice"},
        ),
        status=201,
    )
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{created['id']}",
        json={"status": "in_progress"},
        headers={"X-User-Id": "bob"},
    )
    body = assert_ok(response)
    assert body["createdBy"] == "alice"
    assert body["updatedBy"] == "bob"
