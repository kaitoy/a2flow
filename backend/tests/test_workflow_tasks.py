"""Integration tests for the WorkflowTask CRUD endpoints."""

import itertools
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from models.approval import Approval, ApprovalStatus
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID
from tests._workflow import create_published_workflow, create_skill


async def _insert_approval(
    eng: AsyncEngine,
    *,
    workflow_execution_id: str,
    workflow_task_id: str | None = None,
    approver: str,
    user_id: str = "owner",
) -> str:
    """Insert an Approval row directly (no POST endpoint exists for creation)."""
    async with AsyncSession(eng) as db:
        approval = Approval(
            workflow_execution_id=workflow_execution_id,
            workflow_task_id=workflow_task_id,
            title="Approve me",
            status=ApprovalStatus.pending,
            approver=approver,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        return approval.id


_WF_PROMPT = "Do the thing"
_uniq = itertools.count()


def _next_suffix() -> int:
    """Return a per-process monotonic int used to keep names unique across helper calls."""
    return next(_uniq)


async def _create_workflow_execution(client: AsyncClient) -> Any:
    """Create a published workflow and execute it to produce a WorkflowExecution.

    Runs the full lifecycle (skill → generate → template → publish → execute),
    then deletes the task copied from the template so tests start from a
    session with no tasks, as they did when the design happened inside the run.

    A monotonic suffix is appended to the skill and workflow names so callers can
    invoke this multiple times within a single test (e.g., to verify per-session
    filtering) without tripping UNIQUE constraints on ``agent_skills.name`` or
    ``workflows.name``.
    """
    n = _next_suffix()
    skill = await create_skill(
        client, name=f"skill-{n}", repo_url=f"https://github.com/x/y{n}"
    )
    wf = await create_published_workflow(
        client, skill["id"], name=f"workflow-{n}", prompt=_WF_PROMPT
    )
    execution = assert_ok(
        await client.post(f"/api/v1/workflows/{wf['id']}/execute"), status=201
    )
    seeded = assert_ok(
        await client.get(
            f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks"
        )
    )
    for task in seeded:
        assert_ok(await client.delete(f"/api/v1/workflow-tasks/{task['id']}"))
    return execution


async def _create_task(
    client: AsyncClient,
    execution_id: str,
    *,
    title: str = "Step",
    headers: dict[str, str] | None = None,
    **extra: object,
) -> Any:
    body = {
        "workflowExecutionId": execution_id,
        "title": title,
        **extra,
    }
    return assert_ok(
        await client.post("/api/v1/workflow-tasks", json=body, headers=headers or {}),
        status=201,
    )


# ---------- create ----------


async def test_create_task_returns_201(workflow_client: AsyncClient) -> None:
    execution = await _create_workflow_execution(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflow-tasks",
        json={"workflowExecutionId": execution["id"], "title": "Step 1"},
    )
    assert response.status_code == 201


async def test_create_task_response_contains_expected_fields(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflow-tasks",
        json={
            "workflowExecutionId": execution["id"],
            "title": "Step 1",
            "description": "Outline the doc",
        },
    )
    body = assert_ok(response, status=201)
    assert body["id"]
    assert body["workflowExecutionId"] == execution["id"]
    assert body["title"] == "Step 1"
    assert body["description"] == "Outline the doc"
    assert body["status"] == "pending"


async def test_create_task_defaults_status_to_pending(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    body = await _create_task(workflow_client, execution["id"])
    assert body["status"] == "pending"


async def test_create_task_missing_title_returns_422(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflow-tasks",
        json={"workflowExecutionId": execution["id"]},
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
        json={"workflowExecutionId": "nonexistent", "title": "Step 1"},
    )
    assert_err(response, code="FOREIGN_KEY_VIOLATION", status=422)


async def test_create_task_invalid_status_returns_422(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflow-tasks",
        json={
            "workflowExecutionId": execution["id"],
            "title": "Step 1",
            "status": "bogus",
        },
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


# ---------- list via nested endpoint ----------


async def test_list_session_tasks_empty_initially(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks"
    )
    assert assert_ok(response) == []


async def test_list_session_tasks_returns_created_tasks(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    await _create_task(workflow_client, execution["id"], title="t1")
    await _create_task(workflow_client, execution["id"], title="t2")
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks"
    )
    assert len(assert_ok(response)) == 2


async def test_list_session_tasks_ordered_by_created_at(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    # The API must sort by created_at ASC by default, i.e. creation order.
    await _create_task(workflow_client, execution["id"], title="a")
    await _create_task(workflow_client, execution["id"], title="b")
    await _create_task(workflow_client, execution["id"], title="c")
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks"
    )
    titles = [t["title"] for t in assert_ok(response)]
    assert titles == ["a", "b", "c"]


async def test_list_session_tasks_only_returns_tasks_for_that_session(
    workflow_client: AsyncClient,
) -> None:
    execution1 = await _create_workflow_execution(workflow_client)
    execution2 = await _create_workflow_execution(workflow_client)
    await _create_task(workflow_client, execution1["id"], title="one")
    await _create_task(workflow_client, execution2["id"], title="two")
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution1['id']}/workflow-tasks"
    )
    tasks = assert_ok(response)
    assert len(tasks) == 1
    assert tasks[0]["title"] == "one"


async def test_list_session_tasks_respects_limit_param(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    for i in range(3):
        await _create_task(workflow_client, execution["id"], title=f"t{i}")
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks",
        params={"limit": 2},
    )
    assert len(assert_ok(response)) == 2


async def test_list_session_tasks_unknown_session_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get(
        "/api/v1/workflow-executions/nonexistent/workflow-tasks"
    )
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- list sort & filter ----------


async def test_list_session_tasks_filter_by_status(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    await _create_task(
        workflow_client, execution["id"], title="done", status="completed"
    )
    await _create_task(workflow_client, execution["id"], title="todo", status="pending")
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks",
        params={"q": "status:eq:completed"},
    )
    titles = [t["title"] for t in assert_ok(response)]
    assert titles == ["done"]


async def test_list_session_tasks_filter_status_in(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    await _create_task(workflow_client, execution["id"], title="a", status="completed")
    await _create_task(workflow_client, execution["id"], title="b", status="pending")
    await _create_task(workflow_client, execution["id"], title="c", status="failed")
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks",
        params={"q": "status:in:completed,pending"},
    )
    assert len(assert_ok(response)) == 2


async def test_list_session_tasks_sort_multi_field(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    # Same status so the tie between "a" and "b" is broken by the second sort
    # field (title); "c" sorts first since "failed" < "pending".
    await _create_task(workflow_client, execution["id"], title="b", status="pending")
    await _create_task(workflow_client, execution["id"], title="a", status="pending")
    await _create_task(workflow_client, execution["id"], title="c", status="failed")
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks",
        params={"s": "status,title"},
    )
    titles = [t["title"] for t in assert_ok(response)]
    assert titles == ["c", "a", "b"]


async def test_list_session_tasks_invalid_filter_value_returns_400(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks",
        params={"q": "status:eq:notarealstatus"},
    )
    assert_err(response, code="INVALID_QUERY", status=400)


# ---------- get ----------


async def test_get_task_returns_200(workflow_client: AsyncClient) -> None:
    execution = await _create_workflow_execution(workflow_client)
    created = await _create_task(workflow_client, execution["id"])
    response = await workflow_client.get(f"/api/v1/workflow-tasks/{created['id']}")
    assert response.status_code == 200


async def test_get_task_returns_correct_data(workflow_client: AsyncClient) -> None:
    execution = await _create_workflow_execution(workflow_client)
    created = await _create_task(workflow_client, execution["id"], title="my-task")
    response = await workflow_client.get(f"/api/v1/workflow-tasks/{created['id']}")
    assert assert_ok(response)["title"] == "my-task"


async def test_get_task_unknown_id_returns_404(workflow_client: AsyncClient) -> None:
    response = await workflow_client.get("/api/v1/workflow-tasks/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- patch ----------


async def test_update_task_returns_200(workflow_client: AsyncClient) -> None:
    execution = await _create_workflow_execution(workflow_client)
    created = await _create_task(workflow_client, execution["id"])
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{created['id']}", json={"status": "in_progress"}
    )
    assert response.status_code == 200


async def test_update_task_partial_update_leaves_other_fields_unchanged(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    created = await _create_task(
        workflow_client, execution["id"], title="kept", description="kept-desc"
    )
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{created['id']}", json={"status": "completed"}
    )
    body = assert_ok(response)
    assert body["title"] == "kept"
    assert body["description"] == "kept-desc"
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
    execution = await _create_workflow_execution(workflow_client)
    created = await _create_task(workflow_client, execution["id"])
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{created['id']}", json={"status": "bogus"}
    )
    assert_err(response, code="VALIDATION_ERROR", status=422)


async def test_update_task_ignores_workflow_execution_id_in_body(
    workflow_client: AsyncClient,
) -> None:
    """workflow_execution_id is not in WorkflowTaskUpdate, so it must not be re-parented."""
    execution1 = await _create_workflow_execution(workflow_client)
    execution2 = await _create_workflow_execution(workflow_client)
    created = await _create_task(workflow_client, execution1["id"])
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{created['id']}",
        json={"title": "renamed", "workflowExecutionId": execution2["id"]},
    )
    body = assert_ok(response)
    assert body["title"] == "renamed"
    assert body["workflowExecutionId"] == execution1["id"]


# ---------- delete ----------


async def test_delete_task_returns_200(workflow_client: AsyncClient) -> None:
    execution = await _create_workflow_execution(workflow_client)
    created = await _create_task(workflow_client, execution["id"])
    response = await workflow_client.delete(f"/api/v1/workflow-tasks/{created['id']}")
    assert assert_ok(response, status=200) is None


async def test_delete_task_removes_from_list(workflow_client: AsyncClient) -> None:
    execution = await _create_workflow_execution(workflow_client)
    created = await _create_task(workflow_client, execution["id"])
    await workflow_client.delete(f"/api/v1/workflow-tasks/{created['id']}")
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks"
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
    execution = await _create_workflow_execution(workflow_client)
    body = await _create_task(workflow_client, execution["id"])
    assert body["dependsOnIds"] == []


async def test_create_task_with_dependencies_returns_them(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    a = await _create_task(workflow_client, execution["id"], title="a")
    b = await _create_task(workflow_client, execution["id"], title="b")
    body = await _create_task(
        workflow_client, execution["id"], title="c", dependsOnIds=[a["id"], b["id"]]
    )
    assert sorted(body["dependsOnIds"]) == sorted([a["id"], b["id"]])


async def test_get_task_includes_resolved_dependencies(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    a = await _create_task(workflow_client, execution["id"], title="a")
    b = await _create_task(
        workflow_client, execution["id"], title="b", dependsOnIds=[a["id"]]
    )
    response = await workflow_client.get(f"/api/v1/workflow-tasks/{b['id']}")
    assert assert_ok(response)["dependsOnIds"] == [a["id"]]


async def test_list_session_tasks_include_dependencies(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    a = await _create_task(workflow_client, execution["id"], title="a")
    await _create_task(
        workflow_client, execution["id"], title="b", dependsOnIds=[a["id"]]
    )
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks"
    )
    tasks = {t["title"]: t for t in assert_ok(response)}
    assert tasks["a"]["dependsOnIds"] == []
    assert tasks["b"]["dependsOnIds"] == [a["id"]]


async def test_update_task_replaces_dependencies(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    a = await _create_task(workflow_client, execution["id"], title="a")
    b = await _create_task(workflow_client, execution["id"], title="b")
    c = await _create_task(
        workflow_client, execution["id"], title="c", dependsOnIds=[a["id"]]
    )
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{c['id']}", json={"dependsOnIds": [b["id"]]}
    )
    assert assert_ok(response)["dependsOnIds"] == [b["id"]]


async def test_update_task_without_depends_on_ids_leaves_edges_unchanged(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    a = await _create_task(workflow_client, execution["id"], title="a")
    b = await _create_task(
        workflow_client, execution["id"], title="b", dependsOnIds=[a["id"]]
    )
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{b['id']}", json={"status": "completed"}
    )
    body = assert_ok(response)
    assert body["status"] == "completed"
    assert body["dependsOnIds"] == [a["id"]]


async def test_update_task_clears_dependencies_with_empty_list(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    a = await _create_task(workflow_client, execution["id"], title="a")
    b = await _create_task(
        workflow_client, execution["id"], title="b", dependsOnIds=[a["id"]]
    )
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{b['id']}", json={"dependsOnIds": []}
    )
    assert assert_ok(response)["dependsOnIds"] == []


async def test_dependency_on_unknown_task_returns_422(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflow-tasks",
        json={
            "workflowExecutionId": execution["id"],
            "title": "t",
            "dependsOnIds": ["nonexistent"],
        },
    )
    assert_err(response, code="FOREIGN_KEY_VIOLATION", status=422)


async def test_dependency_on_task_in_other_session_returns_422(
    workflow_client: AsyncClient,
) -> None:
    execution1 = await _create_workflow_execution(workflow_client)
    execution2 = await _create_workflow_execution(workflow_client)
    other = await _create_task(workflow_client, execution2["id"], title="other")
    response = await workflow_client.post(
        "/api/v1/workflow-tasks",
        json={
            "workflowExecutionId": execution1["id"],
            "title": "t",
            "dependsOnIds": [other["id"]],
        },
    )
    assert_err(response, code="FOREIGN_KEY_VIOLATION", status=422)


async def test_self_dependency_returns_409(workflow_client: AsyncClient) -> None:
    execution = await _create_workflow_execution(workflow_client)
    a = await _create_task(workflow_client, execution["id"], title="a")
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{a['id']}", json={"dependsOnIds": [a["id"]]}
    )
    assert_err(response, code="DEPENDENCY_CYCLE", status=409)


async def test_cyclic_dependency_returns_409(workflow_client: AsyncClient) -> None:
    execution = await _create_workflow_execution(workflow_client)
    a = await _create_task(workflow_client, execution["id"], title="a")
    b = await _create_task(
        workflow_client, execution["id"], title="b", dependsOnIds=[a["id"]]
    )
    c = await _create_task(
        workflow_client, execution["id"], title="c", dependsOnIds=[b["id"]]
    )
    # a -> c would close the loop a -> c -> b -> a.
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{a['id']}", json={"dependsOnIds": [c["id"]]}
    )
    assert_err(response, code="DEPENDENCY_CYCLE", status=409)


async def test_deleting_task_cascades_dependency_edges(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    a = await _create_task(workflow_client, execution["id"], title="a")
    b = await _create_task(
        workflow_client, execution["id"], title="b", dependsOnIds=[a["id"]]
    )
    await workflow_client.delete(f"/api/v1/workflow-tasks/{a['id']}")
    response = await workflow_client.get(f"/api/v1/workflow-tasks/{b['id']}")
    assert assert_ok(response)["dependsOnIds"] == []


# ---------- created_by / updated_by ----------


async def test_create_task_populates_created_and_updated_by_from_header(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflow-tasks",
        json={"workflowExecutionId": execution["id"], "title": "t"},
        headers={"X-User-Id": "alice"},
    )
    body = assert_ok(response, status=201)
    assert body["createdBy"] == "alice"
    assert body["updatedBy"] == "alice"


async def test_update_task_preserves_created_by_and_overwrites_updated_by(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    created = assert_ok(
        await workflow_client.post(
            "/api/v1/workflow-tasks",
            json={"workflowExecutionId": execution["id"], "title": "t"},
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


# ---------- tool bindings ----------


async def _create_mcp_server(client: AsyncClient) -> Any:
    """Create an MCPServer with a unique name and return its body."""
    n = _next_suffix()
    return assert_ok(
        await client.post(
            "/api/v1/mcp-servers",
            json={"name": f"mcp-{n}", "url": f"https://mcp{n}.example.com/mcp"},
        ),
        status=201,
    )


async def test_create_task_with_tool_bindings_round_trips(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    server = await _create_mcp_server(workflow_client)
    body = await _create_task(
        workflow_client,
        execution["id"],
        toolBindings=[{"mcpServerId": server["id"], "toolName": "search"}],
    )
    assert body["toolBindings"] == [{"mcpServerId": server["id"], "toolName": "search"}]
    fetched = assert_ok(
        await workflow_client.get(f"/api/v1/workflow-tasks/{body['id']}")
    )
    assert fetched["toolBindings"] == [
        {"mcpServerId": server["id"], "toolName": "search"}
    ]


async def test_create_task_defaults_tool_bindings_to_empty(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    body = await _create_task(workflow_client, execution["id"])
    assert body["toolBindings"] == []


async def test_create_task_with_unknown_server_returns_422(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflow-tasks",
        json={
            "workflowExecutionId": execution["id"],
            "title": "t",
            "toolBindings": [{"mcpServerId": "ghost", "toolName": "search"}],
        },
    )
    assert_err(response, code="FOREIGN_KEY_VIOLATION", status=422)


async def test_create_task_dedupes_tool_bindings(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    server = await _create_mcp_server(workflow_client)
    binding = {"mcpServerId": server["id"], "toolName": "search"}
    body = await _create_task(
        workflow_client, execution["id"], toolBindings=[binding, binding]
    )
    assert body["toolBindings"] == [binding]


async def test_update_task_replaces_tool_bindings(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    server = await _create_mcp_server(workflow_client)
    created = await _create_task(
        workflow_client,
        execution["id"],
        toolBindings=[{"mcpServerId": server["id"], "toolName": "search"}],
    )
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{created['id']}",
        json={"toolBindings": [{"mcpServerId": server["id"], "toolName": "fetch"}]},
    )
    assert assert_ok(response)["toolBindings"] == [
        {"mcpServerId": server["id"], "toolName": "fetch"}
    ]


async def test_update_task_without_tool_bindings_leaves_them_unchanged(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    server = await _create_mcp_server(workflow_client)
    created = await _create_task(
        workflow_client,
        execution["id"],
        toolBindings=[{"mcpServerId": server["id"], "toolName": "search"}],
    )
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{created['id']}", json={"title": "Renamed"}
    )
    assert assert_ok(response)["toolBindings"] == [
        {"mcpServerId": server["id"], "toolName": "search"}
    ]


async def test_update_task_can_clear_tool_bindings(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    server = await _create_mcp_server(workflow_client)
    created = await _create_task(
        workflow_client,
        execution["id"],
        toolBindings=[{"mcpServerId": server["id"], "toolName": "search"}],
    )
    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{created['id']}", json={"toolBindings": []}
    )
    assert assert_ok(response)["toolBindings"] == []


async def test_delete_task_cascades_tool_bindings(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    server = await _create_mcp_server(workflow_client)
    created = await _create_task(
        workflow_client,
        execution["id"],
        toolBindings=[{"mcpServerId": server["id"], "toolName": "search"}],
    )
    await workflow_client.delete(f"/api/v1/workflow-tasks/{created['id']}")
    # With the binding gone, the server is deletable (no CONFLICT_REFERENCED).
    response = await workflow_client.delete(f"/api/v1/mcp-servers/{server['id']}")
    assert assert_ok(response, status=200) is None


# ---------- status change authorization (linked approval) ----------


async def test_update_status_forbidden_for_unrelated_session_approver(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """An approver of a *different* approval in the session cannot resolve this one via status."""
    client, eng = workflow_client_with_engine
    execution = await _create_workflow_execution(client)
    task = await _create_task(client, execution["id"])
    await _insert_approval(
        eng,
        workflow_execution_id=execution["id"],
        workflow_task_id=task["id"],
        approver="bob",
    )
    # alice is a designated approver of a different, unlinked approval in the
    # same session, so she passes the general session-access check but must
    # still be rejected by the linked-approval check.
    await _insert_approval(eng, workflow_execution_id=execution["id"], approver="alice")

    response = await client.patch(
        f"/api/v1/workflow-tasks/{task['id']}",
        json={"status": "completed"},
        headers={"X-User-Id": "alice", "X-User-Roles": "approver"},
    )
    assert_err(response, "FORBIDDEN", 403)

    unchanged = await client.get(f"/api/v1/workflow-tasks/{task['id']}")
    assert assert_ok(unchanged)["status"] == "pending"


async def test_update_status_allowed_for_linked_approval_approver(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = workflow_client_with_engine
    execution = await _create_workflow_execution(client)
    task = await _create_task(client, execution["id"])
    await _insert_approval(
        eng,
        workflow_execution_id=execution["id"],
        workflow_task_id=task["id"],
        approver="bob",
    )

    response = await client.patch(
        f"/api/v1/workflow-tasks/{task['id']}",
        json={"status": "completed"},
        headers={"X-User-Id": "bob", "X-User-Roles": "approver"},
    )
    assert assert_ok(response)["status"] == "completed"


async def test_update_status_allowed_for_session_owner_despite_linked_approval(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, eng = workflow_client_with_engine
    execution = await _create_workflow_execution(client)
    task = await _create_task(client, execution["id"])
    await _insert_approval(
        eng,
        workflow_execution_id=execution["id"],
        workflow_task_id=task["id"],
        approver="bob",
    )

    # No header override: uses workflow_client_with_engine's default identity
    # (SYSTEM_USER_ID), which owns the session created above.
    response = await client.patch(
        f"/api/v1/workflow-tasks/{task['id']}", json={"status": "completed"}
    )
    assert assert_ok(response)["status"] == "completed"


async def test_update_status_allowed_when_no_linked_approval(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A task with no linked approval keeps the broader any-session-participant rule."""
    client, eng = workflow_client_with_engine
    execution = await _create_workflow_execution(client)
    task = await _create_task(client, execution["id"])
    # alice is an approver of an unrelated approval in the session; the task
    # itself has no linked approval, so there is nothing to protect.
    await _insert_approval(eng, workflow_execution_id=execution["id"], approver="alice")

    response = await client.patch(
        f"/api/v1/workflow-tasks/{task['id']}",
        json={"status": "completed"},
        headers={"X-User-Id": "alice", "X-User-Roles": "approver"},
    )
    assert assert_ok(response)["status"] == "completed"


async def test_update_non_status_field_allowed_despite_linked_approval(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Non-status edits stay open to any session participant even on a linked task."""
    client, eng = workflow_client_with_engine
    execution = await _create_workflow_execution(client)
    task = await _create_task(client, execution["id"])
    await _insert_approval(
        eng,
        workflow_execution_id=execution["id"],
        workflow_task_id=task["id"],
        approver="bob",
    )
    await _insert_approval(eng, workflow_execution_id=execution["id"], approver="alice")

    response = await client.patch(
        f"/api/v1/workflow-tasks/{task['id']}",
        json={"title": "renamed"},
        headers={"X-User-Id": "alice", "X-User-Roles": "approver"},
    )
    assert assert_ok(response)["title"] == "renamed"


async def test_update_status_unchanged_value_not_treated_as_a_transition(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Resubmitting the task's current status alongside another field is not a transition."""
    client, eng = workflow_client_with_engine
    execution = await _create_workflow_execution(client)
    task = await _create_task(client, execution["id"])
    assert task["status"] == "pending"
    await _insert_approval(
        eng,
        workflow_execution_id=execution["id"],
        workflow_task_id=task["id"],
        approver="bob",
    )
    await _insert_approval(eng, workflow_execution_id=execution["id"], approver="alice")

    response = await client.patch(
        f"/api/v1/workflow-tasks/{task['id']}",
        json={"status": "pending", "title": "renamed"},
        headers={"X-User-Id": "alice", "X-User-Roles": "approver"},
    )
    body = assert_ok(response)
    assert body["status"] == "pending"
    assert body["title"] == "renamed"


async def test_update_status_forbidden_for_super_admin_who_is_not_owner_or_approver(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A super_admin with no other claim is still forbidden — consistent with ApprovalService.resolve."""
    client, eng = workflow_client_with_engine
    execution = await _create_workflow_execution(client)
    task = await _create_task(client, execution["id"])
    await _insert_approval(
        eng,
        workflow_execution_id=execution["id"],
        workflow_task_id=task["id"],
        approver="bob",
    )

    response = await client.patch(
        f"/api/v1/workflow-tasks/{task['id']}",
        json={"status": "completed"},
        headers={"X-User-Id": "alice", "X-User-Roles": "super_admin"},
    )
    assert_err(response, "FORBIDDEN", 403)


async def test_update_status_forbidden_for_admin_who_is_not_owner_or_approver(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A plain admin cannot change a task's status either -- rejected even earlier, by
    the general execution-write-access gate, since a plain admin never passes
    that check (only the read-only variant admits it)."""
    client, eng = workflow_client_with_engine
    execution = await _create_workflow_execution(client)
    task = await _create_task(client, execution["id"])
    await _insert_approval(
        eng,
        workflow_execution_id=execution["id"],
        workflow_task_id=task["id"],
        approver="bob",
    )

    response = await client.patch(
        f"/api/v1/workflow-tasks/{task['id']}",
        json={"status": "completed"},
        headers={"X-User-Id": "dave", "X-User-Roles": "admin"},
    )
    assert_err(response, "FORBIDDEN", 403)


# ---------- run completion bookkeeping ----------


async def _execution_state(client: AsyncClient, execution_id: str) -> Any:
    """Fetch a run's lifecycle fields as ``(status, finishedAt)``."""
    body = assert_ok(await client.get(f"/api/v1/workflow-executions/{execution_id}"))
    return body["status"], body["finishedAt"]


async def test_run_stays_running_while_a_task_is_unfinished(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    first = await _create_task(workflow_client, execution["id"], title="One")
    await _create_task(workflow_client, execution["id"], title="Two")

    assert_ok(
        await workflow_client.patch(
            f"/api/v1/workflow-tasks/{first['id']}", json={"status": "completed"}
        )
    )

    assert await _execution_state(workflow_client, execution["id"]) == ("running", None)


async def test_run_with_no_tasks_stays_running(workflow_client: AsyncClient) -> None:
    """An empty task list means the agent has not registered its tasks yet, not that it finished."""
    execution = await _create_workflow_execution(workflow_client)

    assert await _execution_state(workflow_client, execution["id"]) == ("running", None)


async def test_run_completes_once_every_task_is_terminal(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    first = await _create_task(workflow_client, execution["id"], title="One")
    second = await _create_task(workflow_client, execution["id"], title="Two")

    for task in (first, second):
        assert_ok(
            await workflow_client.patch(
                f"/api/v1/workflow-tasks/{task['id']}", json={"status": "completed"}
            )
        )

    status, finished_at = await _execution_state(workflow_client, execution["id"])
    assert status == "completed"
    assert finished_at is not None


async def test_run_fails_when_any_task_failed(workflow_client: AsyncClient) -> None:
    execution = await _create_workflow_execution(workflow_client)
    first = await _create_task(workflow_client, execution["id"], title="One")
    second = await _create_task(workflow_client, execution["id"], title="Two")

    assert_ok(
        await workflow_client.patch(
            f"/api/v1/workflow-tasks/{first['id']}", json={"status": "completed"}
        )
    )
    assert_ok(
        await workflow_client.patch(
            f"/api/v1/workflow-tasks/{second['id']}",
            json={
                "status": "failed",
                "errorKind": "api_error",
                "errorMessage": "billing API returned 503",
            },
        )
    )

    status, finished_at = await _execution_state(workflow_client, execution["id"])
    assert status == "failed"
    assert finished_at is not None


async def test_a_skipped_task_alone_does_not_fail_the_run(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    task = await _create_task(workflow_client, execution["id"], title="One")

    assert_ok(
        await workflow_client.patch(
            f"/api/v1/workflow-tasks/{task['id']}", json={"status": "skipped"}
        )
    )

    assert (await _execution_state(workflow_client, execution["id"]))[0] == "completed"


async def test_finished_at_is_not_moved_by_a_later_task_write(
    workflow_client: AsyncClient,
) -> None:
    """The recorded completion time is the first one, so lead time stays honest."""
    execution = await _create_workflow_execution(workflow_client)
    task = await _create_task(workflow_client, execution["id"], title="One")
    assert_ok(
        await workflow_client.patch(
            f"/api/v1/workflow-tasks/{task['id']}", json={"status": "completed"}
        )
    )
    _, first_finished_at = await _execution_state(workflow_client, execution["id"])

    assert_ok(
        await workflow_client.patch(
            f"/api/v1/workflow-tasks/{task['id']}", json={"title": "renamed"}
        )
    )

    assert await _execution_state(workflow_client, execution["id"]) == (
        "completed",
        first_finished_at,
    )


async def test_deleting_the_last_unfinished_task_completes_the_run(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    done = await _create_task(workflow_client, execution["id"], title="One")
    pending = await _create_task(workflow_client, execution["id"], title="Two")
    assert_ok(
        await workflow_client.patch(
            f"/api/v1/workflow-tasks/{done['id']}", json={"status": "completed"}
        )
    )

    assert_ok(await workflow_client.delete(f"/api/v1/workflow-tasks/{pending['id']}"))

    assert (await _execution_state(workflow_client, execution["id"]))[0] == "completed"


async def test_failure_cause_round_trips_through_the_api(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    task = await _create_task(workflow_client, execution["id"])

    body = assert_ok(
        await workflow_client.patch(
            f"/api/v1/workflow-tasks/{task['id']}",
            json={
                "status": "failed",
                "errorKind": "timeout",
                "errorMessage": "no response after 30s",
            },
        )
    )

    assert body["errorKind"] == "timeout"
    assert body["errorMessage"] == "no response after 30s"


async def test_unknown_error_kind_is_rejected(workflow_client: AsyncClient) -> None:
    execution = await _create_workflow_execution(workflow_client)
    task = await _create_task(workflow_client, execution["id"])

    response = await workflow_client.patch(
        f"/api/v1/workflow-tasks/{task['id']}",
        json={"status": "failed", "errorKind": "disk_on_fire"},
    )

    assert_err(response, "VALIDATION_ERROR", 422)
