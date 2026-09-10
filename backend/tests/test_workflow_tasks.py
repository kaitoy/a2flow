"""Integration tests for the WorkflowTask read and status-update endpoints.

A run's task list is fixed at execute time (copied from the workflow's
published task templates), so there is no REST create or delete endpoint and
``PATCH`` only touches ``status`` / ``error_kind`` / ``error_message``. Tests
that need an ad-hoc task on an execution seed it straight into the database
through :func:`tests._workflow.insert_workflow_task`.
"""

import itertools
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from models.approval import Approval, ApprovalStatus
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID
from tests._workflow import (
    clear_execution_tasks,
    create_published_workflow,
    create_skill,
    insert_workflow_task,
)


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
    then clears the task copied from the template so tests start from a session
    with no tasks and add exactly the ones they need through
    :func:`_create_task`.

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
    await clear_execution_tasks(execution["id"])
    return execution


async def _create_task(
    client: AsyncClient,
    execution_id: str,
    *,
    title: str = "Step",
    status: str = "pending",
    description: str | None = None,
    dependsOnIds: list[str] | None = None,  # noqa: N803 - mirrors the JSON field name
    toolBindings: list[dict[str, Any]] | None = None,  # noqa: N803
    user_id: str = "owner",
) -> Any:
    """Seed one WorkflowTask on ``execution_id`` and return it as the API reads it.

    There is no create endpoint any more, so the row is inserted straight into
    the database (see :func:`tests._workflow.insert_workflow_task`) and then
    fetched back through ``GET /workflow-tasks/{id}`` so callers still get the
    envelope-shaped dict they did when this posted.
    """
    task_id = await insert_workflow_task(
        workflow_execution_id=execution_id,
        title=title,
        description=description,
        status=status,
        depends_on_ids=dependsOnIds or [],
        tool_bindings=[
            {
                "mcp_server_id": b["mcpServerId"],
                "tool_name": b["toolName"],
                **(
                    {"requires_input_approval": b["requiresInputApproval"]}
                    if "requiresInputApproval" in b
                    else {}
                ),
            }
            for b in (toolBindings or [])
        ],
        user_id=user_id,
    )
    return assert_ok(await client.get(f"/api/v1/workflow-tasks/{task_id}"))


# ---------- create / delete are not exposed ----------


async def test_create_task_endpoint_is_gone(workflow_client: AsyncClient) -> None:
    """A run's task list is fixed at execute time; there is no POST to add one."""
    execution = await _create_workflow_execution(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflow-tasks",
        json={"workflowExecutionId": execution["id"], "title": "Step 1"},
    )
    assert response.status_code in (404, 405)


async def test_delete_task_endpoint_is_gone(workflow_client: AsyncClient) -> None:
    """Tasks cannot be removed from a run through the API either."""
    execution = await _create_workflow_execution(workflow_client)
    task = await _create_task(workflow_client, execution["id"])
    response = await workflow_client.delete(f"/api/v1/workflow-tasks/{task['id']}")
    assert response.status_code in (404, 405)
    assert_ok(await workflow_client.get(f"/api/v1/workflow-tasks/{task['id']}"))


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
    # field (title); "c" sorts last because a status orders by its position in
    # the lifecycle, and ``failed`` comes after ``pending`` there.
    await _create_task(workflow_client, execution["id"], title="b", status="pending")
    await _create_task(workflow_client, execution["id"], title="a", status="pending")
    await _create_task(workflow_client, execution["id"], title="c", status="failed")
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks",
        params={"s": "status,title"},
    )
    titles = [t["title"] for t in assert_ok(response)]
    assert titles == ["a", "b", "c"]


async def test_list_session_tasks_sort_by_status_follows_the_lifecycle(
    workflow_client: AsyncClient,
) -> None:
    """A status sorts by its position in the lifecycle, not by its spelling.

    Alphabetically these five would come back ``completed, failed, in_progress,
    pending, skipped``, which tells a reader nothing. This is also what keeps
    the two dialects agreeing: PostgreSQL stores the column as a native enum and
    orders it this way already, while SQLite would sort the text.
    """
    execution = await _create_workflow_execution(workflow_client)
    lifecycle = ["pending", "in_progress", "completed", "failed", "skipped"]
    for status in reversed(lifecycle):
        await _create_task(
            workflow_client, execution["id"], title=status, status=status
        )

    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks",
        params={"s": "status"},
    )
    assert [t["status"] for t in assert_ok(response)] == lifecycle

    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks",
        params={"s": "-status"},
    )
    assert [t["status"] for t in assert_ok(response)] == list(reversed(lifecycle))


async def test_list_session_tasks_status_range_filter_follows_the_lifecycle(
    workflow_client: AsyncClient,
) -> None:
    """An ordered comparison on a status means the order the sort means.

    ``gte:completed`` takes the tail of the lifecycle. Compared as text it would
    instead take ``failed``, ``in_progress``, ``pending`` and ``skipped`` — a
    different set, and a different one again per dialect.
    """
    execution = await _create_workflow_execution(workflow_client)
    for status in ("pending", "in_progress", "completed", "failed", "skipped"):
        await _create_task(
            workflow_client, execution["id"], title=status, status=status
        )

    async def _statuses(query: str) -> list[str]:
        response = await workflow_client.get(
            f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks",
            params={"q": query, "s": "status"},
        )
        return [t["status"] for t in assert_ok(response)]

    assert await _statuses("status:gte:completed") == [
        "completed",
        "failed",
        "skipped",
    ]
    assert await _statuses("status:lt:completed") == ["pending", "in_progress"]
    # Equality is unaffected by the rewrite and still selects the one value.
    assert await _statuses("status:eq:failed") == ["failed"]


async def test_list_session_tasks_status_substring_filter_matches(
    workflow_client: AsyncClient,
) -> None:
    """A substring filter reaches a status like it reaches any other string.

    PostgreSQL keeps the column as a native enum, and an enum has no ``ILIKE``
    operator of its own, so without the text cast this is a 500 there while
    passing on SQLite — which stores the same column as text.
    """
    execution = await _create_workflow_execution(workflow_client)
    for status in ("pending", "in_progress", "completed"):
        await _create_task(
            workflow_client, execution["id"], title=status, status=status
        )

    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks",
        # Upper case on purpose: the match is case-insensitive on both dialects.
        params={"q": "status:like:PEND"},
    )
    assert [t["status"] for t in assert_ok(response)] == ["pending"]


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


async def test_update_task_ignores_immutable_fields(
    workflow_client: AsyncClient,
) -> None:
    """A run's task list is fixed at execute time.

    ``PATCH`` accepts only ``status`` / ``error_kind`` / ``error_message``;
    ``title``, ``description``, ``dependsOnIds``, ``toolBindings`` and
    ``workflowExecutionId`` in the body are silently ignored.
    """
    execution1 = await _create_workflow_execution(workflow_client)
    execution2 = await _create_workflow_execution(workflow_client)
    a = await _create_task(workflow_client, execution1["id"], title="a")
    created = await _create_task(
        workflow_client,
        execution1["id"],
        title="kept",
        description="kept-desc",
        dependsOnIds=[a["id"]],
    )
    body = assert_ok(
        await workflow_client.patch(
            f"/api/v1/workflow-tasks/{created['id']}",
            json={
                "status": "completed",
                "title": "renamed",
                "description": "rewritten",
                "dependsOnIds": [],
                "toolBindings": [],
                "workflowExecutionId": execution2["id"],
            },
        )
    )
    assert body["status"] == "completed"
    assert body["title"] == "kept"
    assert body["description"] == "kept-desc"
    assert body["dependsOnIds"] == [a["id"]]
    assert body["workflowExecutionId"] == execution1["id"]


# ---------- dependencies (DAG) ----------


async def test_task_defaults_to_no_dependencies(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    body = await _create_task(workflow_client, execution["id"])
    assert body["dependsOnIds"] == []


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


async def test_update_task_never_touches_dependencies(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    a = await _create_task(workflow_client, execution["id"], title="a")
    b = await _create_task(workflow_client, execution["id"], title="b")
    c = await _create_task(
        workflow_client, execution["id"], title="c", dependsOnIds=[a["id"]]
    )
    # A status change leaves the edges alone...
    body = assert_ok(
        await workflow_client.patch(
            f"/api/v1/workflow-tasks/{c['id']}", json={"status": "completed"}
        )
    )
    assert body["status"] == "completed"
    assert body["dependsOnIds"] == [a["id"]]
    # ...and so does a body that tries to rewrite or clear them.
    assert assert_ok(
        await workflow_client.patch(
            f"/api/v1/workflow-tasks/{c['id']}", json={"dependsOnIds": [b["id"]]}
        )
    )["dependsOnIds"] == [a["id"]]
    assert assert_ok(
        await workflow_client.patch(
            f"/api/v1/workflow-tasks/{c['id']}", json={"dependsOnIds": []}
        )
    )["dependsOnIds"] == [a["id"]]


# ---------- created_by / updated_by ----------


async def test_update_task_preserves_created_by_and_overwrites_updated_by(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    created = await _create_task(workflow_client, execution["id"], user_id="alice")
    assert created["createdBy"] == "alice"
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


async def test_task_tool_bindings_round_trip(
    workflow_client: AsyncClient,
) -> None:
    """Bindings copied onto a task at execute time read back on GET."""
    execution = await _create_workflow_execution(workflow_client)
    server = await _create_mcp_server(workflow_client)
    body = await _create_task(
        workflow_client,
        execution["id"],
        toolBindings=[{"mcpServerId": server["id"], "toolName": "search"}],
    )
    expected = [
        {
            "mcpServerId": server["id"],
            "toolName": "search",
            "requiresInputApproval": True,
        }
    ]
    assert body["toolBindings"] == expected
    fetched = assert_ok(
        await workflow_client.get(f"/api/v1/workflow-tasks/{body['id']}")
    )
    assert fetched["toolBindings"] == expected


async def test_task_defaults_tool_bindings_to_empty(
    workflow_client: AsyncClient,
) -> None:
    execution = await _create_workflow_execution(workflow_client)
    body = await _create_task(workflow_client, execution["id"])
    assert body["toolBindings"] == []


async def test_update_task_never_touches_tool_bindings(
    workflow_client: AsyncClient,
) -> None:
    """``toolBindings`` in a PATCH body is ignored, whatever it says."""
    execution = await _create_workflow_execution(workflow_client)
    server = await _create_mcp_server(workflow_client)
    created = await _create_task(
        workflow_client,
        execution["id"],
        toolBindings=[{"mcpServerId": server["id"], "toolName": "search"}],
    )
    original = created["toolBindings"]
    bodies: list[dict[str, Any]] = [
        {"status": "in_progress"},
        {"toolBindings": [{"mcpServerId": server["id"], "toolName": "fetch"}]},
        {"toolBindings": []},
    ]
    for body in bodies:
        assert (
            assert_ok(
                await workflow_client.patch(
                    f"/api/v1/workflow-tasks/{created['id']}", json=body
                )
            )["toolBindings"]
            == original
        )


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


async def test_update_status_forbidden_for_session_approver_when_no_linked_approval(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A task no approval governs is the initiator's to advance, not an approver's."""
    client, eng = workflow_client_with_engine
    execution = await _create_workflow_execution(client)
    task = await _create_task(client, execution["id"])
    # alice is an approver of an unrelated approval in the session, so she is a
    # participant -- but nothing addresses this task to her, so she may not
    # advance it.
    await _insert_approval(eng, workflow_execution_id=execution["id"], approver="alice")

    response = await client.patch(
        f"/api/v1/workflow-tasks/{task['id']}",
        json={"status": "completed"},
        headers={"X-User-Id": "alice", "X-User-Roles": "approver"},
    )
    assert_err(response, "FORBIDDEN", 403)

    unchanged = await client.get(f"/api/v1/workflow-tasks/{task['id']}")
    assert assert_ok(unchanged)["status"] == "pending"


async def test_update_status_allowed_for_approver_on_downstream_covered_task(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """An approval covers the steps downstream of the task it names, so its approver
    may advance those too -- this is what lets a decision resume the run."""
    client, eng = workflow_client_with_engine
    execution = await _create_workflow_execution(client)
    gate = await _create_task(client, execution["id"], title="gate")
    downstream = await _create_task(
        client, execution["id"], title="downstream", dependsOnIds=[gate["id"]]
    )
    # The approval takes effect from ``gate``; nothing links it to ``downstream``
    # directly, but the scope rule carries it down the dependency edge.
    await _insert_approval(
        eng,
        workflow_execution_id=execution["id"],
        workflow_task_id=gate["id"],
        approver="bob",
    )

    response = await client.patch(
        f"/api/v1/workflow-tasks/{downstream['id']}",
        json={"status": "completed"},
        headers={"X-User-Id": "bob", "X-User-Roles": "approver"},
    )
    assert assert_ok(response)["status"] == "completed"


async def test_update_without_a_status_change_skips_the_linked_approval_guard(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A PATCH that attempts no status transition only meets the write-access gate.

    A session participant who is *not* the linked approval's approver still
    passes it, so the request succeeds -- the ignored ``title`` simply has no
    effect and the linked-approval status guard never runs.
    """
    client, eng = workflow_client_with_engine
    execution = await _create_workflow_execution(client)
    task = await _create_task(client, execution["id"], title="kept")
    await _insert_approval(
        eng,
        workflow_execution_id=execution["id"],
        workflow_task_id=task["id"],
        approver="bob",
    )
    await _insert_approval(eng, workflow_execution_id=execution["id"], approver="alice")

    response = await client.patch(
        f"/api/v1/workflow-tasks/{task['id']}",
        json={"title": "renamed", "errorMessage": "noted"},
        headers={"X-User-Id": "alice", "X-User-Roles": "approver"},
    )
    body = assert_ok(response)
    assert body["title"] == "kept"
    assert body["errorMessage"] == "noted"


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
        json={"status": "pending", "errorMessage": "noted"},
        headers={"X-User-Id": "alice", "X-User-Roles": "approver"},
    )
    body = assert_ok(response)
    assert body["status"] == "pending"
    assert body["errorMessage"] == "noted"


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
            f"/api/v1/workflow-tasks/{task['id']}",
            json={"status": "completed", "errorMessage": "late note"},
        )
    )

    assert await _execution_state(workflow_client, execution["id"]) == (
        "completed",
        first_finished_at,
    )


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


async def _task_status(client: AsyncClient, task_id: str) -> Any:
    """Fetch a single task's ``status`` field."""
    return assert_ok(await client.get(f"/api/v1/workflow-tasks/{task_id}"))["status"]


async def test_failing_a_task_skips_blocked_dependents_and_fails_the_run(
    workflow_client: AsyncClient,
) -> None:
    """A failed task's transitive dependents can never run, so they are skipped
    and the run settles ``failed`` instead of hanging on them forever."""
    execution = await _create_workflow_execution(workflow_client)
    a = await _create_task(workflow_client, execution["id"], title="A")
    b = await _create_task(
        workflow_client, execution["id"], title="B", dependsOnIds=[a["id"]]
    )
    c = await _create_task(
        workflow_client, execution["id"], title="C", dependsOnIds=[b["id"]]
    )

    assert_ok(
        await workflow_client.patch(
            f"/api/v1/workflow-tasks/{a['id']}",
            json={
                "status": "failed",
                "errorKind": "api_error",
                "errorMessage": "billing API returned 503",
            },
        )
    )

    assert await _task_status(workflow_client, b["id"]) == "skipped"
    assert await _task_status(workflow_client, c["id"]) == "skipped"
    status, finished_at = await _execution_state(workflow_client, execution["id"])
    assert status == "failed"
    assert finished_at is not None


async def test_an_independent_pending_task_keeps_a_failed_run_running(
    workflow_client: AsyncClient,
) -> None:
    """Only the failed task's own dependents are skipped: an unrelated pending
    task still holds the run ``running`` until it too reaches a terminal state."""
    execution = await _create_workflow_execution(workflow_client)
    a = await _create_task(workflow_client, execution["id"], title="A")
    d = await _create_task(workflow_client, execution["id"], title="D")

    assert_ok(
        await workflow_client.patch(
            f"/api/v1/workflow-tasks/{a['id']}",
            json={
                "status": "failed",
                "errorKind": "api_error",
                "errorMessage": "billing API returned 503",
            },
        )
    )
    assert await _execution_state(workflow_client, execution["id"]) == ("running", None)

    assert_ok(
        await workflow_client.patch(
            f"/api/v1/workflow-tasks/{d['id']}", json={"status": "completed"}
        )
    )
    status, finished_at = await _execution_state(workflow_client, execution["id"])
    assert status == "failed"
    assert finished_at is not None
