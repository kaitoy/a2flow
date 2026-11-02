"""API tests for a workflow's version history and restoring an older version.

Every publish adds a numbered snapshot (``GET /workflows/{id}/versions``), and
``POST /workflows/{id}/versions/{version}/restore`` writes one back into the
live design without publishing it. Runs record the version they started from.
"""

from typing import Any

from httpx import AsyncClient

from models.workflow import Workflow, WorkflowStatus
from tests._envelope import assert_err, assert_ok
from tests._workflow import (
    add_template,
    app_db_session,
    create_skill,
    execute_workflow,
    generate_workflow,
    publish_workflow,
)

DEVELOPER_ONLY = {"X-User-Roles": "developer"}
REQUESTER = {"X-User-Roles": "requester"}


async def _two_versions(client: AsyncClient) -> tuple[Any, Any]:
    """Publish a workflow twice: v1 runs "First", v2 renames it to "Second".

    Returns:
        The workflow as returned by the second publish, and its one template.
    """
    skill = await create_skill(client)
    wf = await generate_workflow(client, skill["id"])
    template = await add_template(client, wf["id"], title="First")
    await publish_workflow(client, wf["id"])
    assert_ok(
        await client.patch(
            f"/api/v1/workflow-task-templates/{template['id']}",
            json={"title": "Second"},
        )
    )
    assert_ok(
        await client.patch(f"/api/v1/workflows/{wf['id']}", json={"name": "Renamed"})
    )
    return await publish_workflow(client, wf["id"]), template


async def _titles(client: AsyncClient, workflow_id: str) -> list[str]:
    """Return the titles of the workflow's live task templates."""
    templates = assert_ok(
        await client.get(f"/api/v1/workflows/{workflow_id}/task-templates")
    )
    return [t["title"] for t in templates]


async def _restore(
    client: AsyncClient, workflow_id: str, version: int, **kwargs: Any
) -> Any:
    """POST a restore request and return the raw response."""
    return await client.post(
        f"/api/v1/workflows/{workflow_id}/versions/{version}/restore", **kwargs
    )


async def test_each_publish_is_listed_newest_first(
    workflow_client: AsyncClient,
) -> None:
    wf, _ = await _two_versions(workflow_client)
    versions = assert_ok(
        await workflow_client.get(f"/api/v1/workflows/{wf['id']}/versions")
    )
    assert [(v["version"], v["name"]) for v in versions] == [
        (2, "Renamed"),
        (1, "my-workflow"),
    ]
    assert "templates" not in versions[0]


async def test_restoring_an_older_version_leaves_it_modified(
    workflow_client: AsyncClient,
) -> None:
    """The old design comes back live, but is not published until republished."""
    wf, template = await _two_versions(workflow_client)

    body = assert_ok(await _restore(workflow_client, wf["id"], 1))

    assert body["status"] == "modified"
    assert body["name"] == "my-workflow"
    assert await _titles(workflow_client, wf["id"]) == ["First"]
    # Runs keep using v2 until the restored design is published as v3.
    run = await execute_workflow(workflow_client, wf["id"])
    assert run["workflowVersion"] == 2
    await publish_workflow(workflow_client, wf["id"])
    versions = assert_ok(
        await workflow_client.get(f"/api/v1/workflows/{wf['id']}/versions")
    )
    assert [v["version"] for v in versions] == [3, 2, 1]


async def test_restoring_the_latest_version_is_published(
    workflow_client: AsyncClient,
) -> None:
    """Restoring the current version leaves nothing unpublished."""
    wf, template = await _two_versions(workflow_client)
    assert_ok(
        await workflow_client.patch(
            f"/api/v1/workflow-task-templates/{template['id']}",
            json={"title": "Draft edit"},
        )
    )

    body = assert_ok(await _restore(workflow_client, wf["id"], 2))

    assert body["status"] == "published"
    assert await _titles(workflow_client, wf["id"]) == ["Second"]


async def test_restoring_into_a_draft_keeps_it_draft(
    workflow_client: AsyncClient,
) -> None:
    wf, _ = await _two_versions(workflow_client)
    assert_ok(await workflow_client.post(f"/api/v1/workflows/{wf['id']}/deactivate"))

    body = assert_ok(await _restore(workflow_client, wf["id"], 1))

    assert body["status"] == "draft"
    assert await _titles(workflow_client, wf["id"]) == ["First"]


async def test_restoring_while_generating_returns_409(
    workflow_client: AsyncClient,
) -> None:
    wf, _ = await _two_versions(workflow_client)
    async with app_db_session() as db:
        row = await db.get(Workflow, wf["id"])
        assert row is not None
        row.status = WorkflowStatus.generating
        db.add(row)
        await db.commit()

    assert_err(
        await _restore(workflow_client, wf["id"], 1), "WORKFLOW_NOT_RUNNABLE", 409
    )


async def test_restoring_an_unknown_version_returns_404(
    workflow_client: AsyncClient,
) -> None:
    wf, _ = await _two_versions(workflow_client)
    assert_err(await _restore(workflow_client, wf["id"], 9), "NOT_FOUND", 404)
    assert_err(await _restore(workflow_client, "nonexistent", 1), "NOT_FOUND", 404)


async def test_restoring_requires_the_developer_role(
    workflow_client: AsyncClient,
) -> None:
    wf, _ = await _two_versions(workflow_client)
    assert_err(
        await _restore(workflow_client, wf["id"], 1, headers=REQUESTER),
        "FORBIDDEN",
        403,
    )
    assert_ok(await _restore(workflow_client, wf["id"], 1, headers=DEVELOPER_ONLY))


async def test_only_staff_may_list_the_history(
    workflow_client: AsyncClient,
) -> None:
    """A requester or approver is refused; a developer or reviewer is served."""
    wf, _ = await _two_versions(workflow_client)
    url = f"/api/v1/workflows/{wf['id']}/versions"
    for role in ("requester", "approver"):
        assert_err(
            await workflow_client.get(url, headers={"X-User-Roles": role}),
            "FORBIDDEN",
            403,
        )
    for role in ("developer", "reviewer", "admin"):
        versions = assert_ok(
            await workflow_client.get(url, headers={"X-User-Roles": role})
        )
        assert len(versions) == 2


async def test_runs_record_the_version_they_started_from(
    workflow_client: AsyncClient,
) -> None:
    """A published run names its version; a draft run names none."""
    wf, _ = await _two_versions(workflow_client)
    assert (await execute_workflow(workflow_client, wf["id"]))["workflowVersion"] == 2

    skill = await create_skill(workflow_client, name="skill-b")
    draft = await generate_workflow(workflow_client, skill["id"])
    await add_template(workflow_client, draft["id"])
    run = await execute_workflow(workflow_client, draft["id"])
    assert run["workflowVersion"] is None


async def test_a_requester_sees_only_the_latest_version_once(
    workflow_client: AsyncClient,
) -> None:
    """The published view joins the latest snapshot only, so no row repeats."""
    wf, _ = await _two_versions(workflow_client)
    assert_ok(
        await workflow_client.patch(f"/api/v1/workflows/{wf['id']}", json={"name": "X"})
    )
    listed = assert_ok(
        await workflow_client.get("/api/v1/workflows", headers=REQUESTER)
    )
    mine = [w for w in listed if w["id"] == wf["id"]]
    assert [(w["name"], w["status"]) for w in mine] == [("Renamed", "published")]
