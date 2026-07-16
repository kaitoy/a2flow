"""Integration tests for the WorkflowTaskTemplate endpoints.

Templates are the workflow's pre-planned task list, edited manually through
these endpoints (and by the planning agent through its tools). Listing lives on
the workflow router (``GET /workflows/{id}/task-templates``); single-template
operations live under ``/workflow-task-templates``.
"""

from httpx import AsyncClient

from tests._envelope import assert_err, assert_ok
from tests._workflow import add_template, create_skill, generate_workflow


async def _draft_workflow(client: AsyncClient) -> str:
    skill = await create_skill(client)
    wf = await generate_workflow(client, skill["id"])
    return str(wf["id"])


# ---------- create ----------


async def test_create_template_returns_201(workflow_client: AsyncClient) -> None:
    wf_id = await _draft_workflow(workflow_client)
    response = await workflow_client.post(
        "/api/v1/workflow-task-templates",
        json={"workflowId": wf_id, "title": "Step 1", "position": 0},
    )
    body = assert_ok(response, status=201)
    assert body["title"] == "Step 1"
    assert body["workflowId"] == wf_id
    assert "status" not in body


async def test_create_template_unknown_workflow_returns_422(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.post(
        "/api/v1/workflow-task-templates",
        json={"workflowId": "nonexistent", "title": "Step"},
    )
    assert_err(response, code="FOREIGN_KEY_VIOLATION", status=422)


async def test_create_template_with_dependency(workflow_client: AsyncClient) -> None:
    wf_id = await _draft_workflow(workflow_client)
    first = await add_template(workflow_client, wf_id, title="First")
    second = await add_template(
        workflow_client, wf_id, title="Second", depends_on_ids=[first["id"]]
    )
    assert second["dependsOnIds"] == [first["id"]]


async def test_create_template_dependency_cycle_rejected(
    workflow_client: AsyncClient,
) -> None:
    wf_id = await _draft_workflow(workflow_client)
    a = await add_template(workflow_client, wf_id, title="A")
    b = await add_template(workflow_client, wf_id, title="B", depends_on_ids=[a["id"]])
    response = await workflow_client.patch(
        f"/api/v1/workflow-task-templates/{a['id']}",
        json={"dependsOnIds": [b["id"]]},
    )
    assert_err(response, code="DEPENDENCY_CYCLE", status=409)


async def test_create_template_cross_workflow_dependency_rejected(
    workflow_client: AsyncClient,
) -> None:
    skill = await create_skill(workflow_client)
    wf1 = await generate_workflow(workflow_client, skill["id"], name="wf-one")
    wf2 = await generate_workflow(workflow_client, skill["id"], name="wf-two")
    other = await add_template(workflow_client, wf1["id"], title="Elsewhere")
    response = await workflow_client.post(
        "/api/v1/workflow-task-templates",
        json={
            "workflowId": wf2["id"],
            "title": "Bad",
            "dependsOnIds": [other["id"]],
        },
    )
    assert_err(response, code="FOREIGN_KEY_VIOLATION", status=422)


# ---------- list (on the workflow router) ----------


async def test_list_templates_empty_initially(workflow_client: AsyncClient) -> None:
    wf_id = await _draft_workflow(workflow_client)
    response = await workflow_client.get(f"/api/v1/workflows/{wf_id}/task-templates")
    assert assert_ok(response) == []


async def test_list_templates_orders_by_position(workflow_client: AsyncClient) -> None:
    wf_id = await _draft_workflow(workflow_client)
    await add_template(workflow_client, wf_id, title="Second", position=1)
    await add_template(workflow_client, wf_id, title="First", position=0)
    response = await workflow_client.get(f"/api/v1/workflows/{wf_id}/task-templates")
    assert [t["title"] for t in assert_ok(response)] == ["First", "Second"]


async def test_list_templates_unknown_workflow_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get("/api/v1/workflows/nonexistent/task-templates")
    assert_err(response, code="NOT_FOUND", status=404)


async def test_list_templates_scoped_to_workflow(workflow_client: AsyncClient) -> None:
    skill = await create_skill(workflow_client)
    wf1 = await generate_workflow(workflow_client, skill["id"], name="wf-one")
    wf2 = await generate_workflow(workflow_client, skill["id"], name="wf-two")
    await add_template(workflow_client, wf1["id"], title="In one")
    await add_template(workflow_client, wf2["id"], title="In two")
    response = await workflow_client.get(
        f"/api/v1/workflows/{wf1['id']}/task-templates"
    )
    assert [t["title"] for t in assert_ok(response)] == ["In one"]


# ---------- get / patch / delete ----------


async def test_get_template_returns_200(workflow_client: AsyncClient) -> None:
    wf_id = await _draft_workflow(workflow_client)
    created = await add_template(workflow_client, wf_id)
    response = await workflow_client.get(
        f"/api/v1/workflow-task-templates/{created['id']}"
    )
    assert assert_ok(response)["id"] == created["id"]


async def test_get_template_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get("/api/v1/workflow-task-templates/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


async def test_update_template_fields(workflow_client: AsyncClient) -> None:
    wf_id = await _draft_workflow(workflow_client)
    created = await add_template(workflow_client, wf_id, description="old")
    response = await workflow_client.patch(
        f"/api/v1/workflow-task-templates/{created['id']}",
        json={"title": "Renamed"},
    )
    body = assert_ok(response)
    assert body["title"] == "Renamed"
    assert body["description"] == "old"


async def test_update_template_replaces_dependencies(
    workflow_client: AsyncClient,
) -> None:
    wf_id = await _draft_workflow(workflow_client)
    a = await add_template(workflow_client, wf_id, title="A")
    b = await add_template(workflow_client, wf_id, title="B")
    response = await workflow_client.patch(
        f"/api/v1/workflow-task-templates/{b['id']}",
        json={"dependsOnIds": [a["id"]]},
    )
    assert assert_ok(response)["dependsOnIds"] == [a["id"]]


async def test_delete_template_returns_200(workflow_client: AsyncClient) -> None:
    wf_id = await _draft_workflow(workflow_client)
    created = await add_template(workflow_client, wf_id)
    response = await workflow_client.delete(
        f"/api/v1/workflow-task-templates/{created['id']}"
    )
    assert assert_ok(response, status=200) is None
    listed = assert_ok(
        await workflow_client.get(f"/api/v1/workflows/{wf_id}/task-templates")
    )
    assert listed == []


async def test_delete_template_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.delete(
        "/api/v1/workflow-task-templates/nonexistent"
    )
    assert_err(response, code="NOT_FOUND", status=404)


async def test_templates_cascade_with_workflow(workflow_client: AsyncClient) -> None:
    wf_id = await _draft_workflow(workflow_client)
    created = await add_template(workflow_client, wf_id)
    assert_ok(await workflow_client.delete(f"/api/v1/workflows/{wf_id}"))
    response = await workflow_client.get(
        f"/api/v1/workflow-task-templates/{created['id']}"
    )
    assert_err(response, code="NOT_FOUND", status=404)
