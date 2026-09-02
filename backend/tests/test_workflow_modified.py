"""How a ``modified`` workflow behaves, per role.

A ``modified`` workflow holds two designs at once: the snapshot taken when it
was published, and the live rows a developer has edited since. Who sees which
one is the whole subject of this file.

* A ``developer`` sees the live rows, and may run either — the published design
  as a real request, or the edits as a draft run (``designSource: "live"``).
* Everybody else sees only the published snapshot, reported as ``published``.
  The edits do not exist for them: not in the workflow, not in its task
  templates, not in what a name search matches.
"""

from typing import Any

import pytest
from httpx import AsyncClient

from tests._envelope import assert_err, assert_ok
from tests._workflow import (
    add_template,
    create_modified_workflow,
    create_published_workflow,
    create_skill,
    execute_workflow,
    execute_workflow_err,
    execution_task_titles,
    generate_workflow,
    publish_workflow,
)

#: Acts as a plain requester — the role that may run a workflow but never see
#: its unpublished design.
REQUESTER = {"X-User-Roles": "requester"}

#: Acts as a developer without the ``super_admin`` bypass the default test
#: caller carries, so the developer-only paths are exercised on their own merit.
DEVELOPER = {"X-User-Roles": "developer"}


async def _modified(client: AsyncClient, **overrides: str) -> Any:
    """Register a skill and leave one workflow of it in ``modified``."""
    skill = await create_skill(client)
    return await create_modified_workflow(client, skill["id"], **overrides)


async def _get(client: AsyncClient, workflow_id: str, headers: Any = None) -> Any:
    """Read one workflow as the given caller."""
    return assert_ok(
        await client.get(f"/api/v1/workflows/{workflow_id}", headers=headers)
    )


async def _templates(
    client: AsyncClient, workflow_id: str, headers: Any = None, **params: str
) -> list[Any]:
    """List a workflow's task templates as the given caller."""
    items = assert_ok(
        await client.get(
            f"/api/v1/workflows/{workflow_id}/task-templates",
            headers=headers,
            params=params or None,
        )
    )
    return list(items)


async def _tool_mock(client: AsyncClient) -> Any:
    """Register a mock of the built-in approval tool."""
    return assert_ok(
        await client.post(
            "/api/v1/mcp-tool-mocks",
            json={
                "name": "approve-everything",
                "toolName": "request_approval",
                "responses": [{"kind": "structured", "value": {"status": "approved"}}],
            },
        ),
        status=201,
    )


# ---------- choosing which design runs ----------


async def test_the_default_run_still_uses_the_published_design(
    workflow_client: AsyncClient,
) -> None:
    """A body-less execute is unchanged: the approved design runs, as a real run."""
    wf = await _modified(workflow_client)
    execution = await execute_workflow(workflow_client, wf["id"])
    assert await execution_task_titles(workflow_client, execution["id"]) == [
        "Published step"
    ]
    assert execution["isDraft"] is False


async def test_a_developer_can_run_the_unpublished_design(
    workflow_client: AsyncClient,
) -> None:
    """``designSource: live`` runs the edits, including a step added since publish."""
    wf = await _modified(workflow_client)
    execution = await execute_workflow(
        workflow_client, wf["id"], designSource="live", headers=DEVELOPER
    )
    assert sorted(await execution_task_titles(workflow_client, execution["id"])) == [
        "Brand new step",
        "Edited step",
    ]


async def test_a_live_run_is_recorded_as_a_draft_run(
    workflow_client: AsyncClient,
) -> None:
    """It executes an unapproved design, so it is a test run and stays one."""
    wf = await _modified(workflow_client)
    execution = await execute_workflow(
        workflow_client, wf["id"], designSource="live", headers=DEVELOPER
    )
    assert execution["isDraft"] is True


async def test_a_live_run_takes_the_published_name_from_the_edits(
    workflow_client: AsyncClient,
) -> None:
    """The run is named after the edited workflow, not the published snapshot."""
    wf = await _modified(workflow_client, edited_name="Renamed")
    execution = await execute_workflow(
        workflow_client, wf["id"], designSource="live", headers=DEVELOPER
    )
    assert execution["name"].startswith("Renamed-")


async def test_a_live_run_accepts_tool_mocks(workflow_client: AsyncClient) -> None:
    """Being a draft run, it may stub its tools like any pre-publish test."""
    wf = await _modified(workflow_client)
    mock = await _tool_mock(workflow_client)
    execution = await execute_workflow(
        workflow_client,
        wf["id"],
        designSource="live",
        toolMockIds=[mock["id"]],
        headers=DEVELOPER,
    )
    assert [m["toolName"] for m in execution["toolMocks"]] == ["request_approval"]


async def test_a_published_run_of_a_modified_workflow_still_refuses_mocks(
    workflow_client: AsyncClient,
) -> None:
    """Mocking the design people rely on would produce a run that did nothing."""
    wf = await _modified(workflow_client)
    mock = await _tool_mock(workflow_client)
    error = await execute_workflow_err(
        workflow_client,
        wf["id"],
        toolMockIds=[mock["id"]],
        code="WORKFLOW_NOT_RUNNABLE",
        status=409,
        headers=DEVELOPER,
    )
    assert "draft" in error["details"]["reason"]


async def test_a_requester_cannot_run_the_unpublished_design(
    workflow_client: AsyncClient,
) -> None:
    """The edits do not exist for a requester, so neither does this option."""
    wf = await _modified(workflow_client)
    await execute_workflow_err(
        workflow_client,
        wf["id"],
        designSource="live",
        code="FORBIDDEN",
        status=403,
        headers=REQUESTER,
    )


async def test_a_developer_inheriting_the_role_from_a_group_can_run_the_edits(
    workflow_client: AsyncClient,
) -> None:
    """The rule lives in the service, so it must see group-inherited roles too."""
    wf = await _modified(workflow_client)
    execution = await execute_workflow(
        workflow_client,
        wf["id"],
        designSource="live",
        headers={"X-User-Roles": "requester", "X-User-Group-Roles": "developer"},
    )
    assert execution["isDraft"] is True


async def test_a_published_workflow_has_no_unpublished_design_to_run(
    workflow_client: AsyncClient,
) -> None:
    """Nothing has drifted, so there is no second design to choose."""
    skill = await create_skill(workflow_client)
    wf = await create_published_workflow(workflow_client, skill["id"])
    error = await execute_workflow_err(
        workflow_client,
        wf["id"],
        designSource="live",
        code="WORKFLOW_NOT_RUNNABLE",
        status=409,
        headers=DEVELOPER,
    )
    assert "modified" in error["details"]["reason"]


async def test_a_draft_workflow_has_no_unpublished_design_to_run(
    workflow_client: AsyncClient,
) -> None:
    """A draft workflow is already running its live rows; asking is a mistake."""
    skill = await create_skill(workflow_client)
    wf = await generate_workflow(workflow_client, skill["id"])
    await add_template(workflow_client, wf["id"])
    await execute_workflow_err(
        workflow_client,
        wf["id"],
        designSource="live",
        code="WORKFLOW_NOT_RUNNABLE",
        status=409,
        headers=DEVELOPER,
    )


# ---------- reading one workflow ----------


async def test_a_developer_sees_the_unpublished_edits(
    workflow_client: AsyncClient,
) -> None:
    """The audience for the live rows is the role that can edit and publish them."""
    wf = await _modified(workflow_client)
    body = await _get(workflow_client, wf["id"], DEVELOPER)
    assert body["status"] == "modified"
    assert body["name"] == "Renamed"


async def test_a_requester_sees_the_published_workflow_instead(
    workflow_client: AsyncClient,
) -> None:
    """Name, description, and status all come from the last publish."""
    wf = await _modified(workflow_client)
    body = await _get(workflow_client, wf["id"], REQUESTER)
    assert body["status"] == "published"
    assert body["name"] == "my-workflow"


async def test_a_requester_is_not_shown_the_generated_description(
    workflow_client: AsyncClient,
) -> None:
    """The snapshot resolved the two descriptions into one at publish time."""
    wf = await _modified(workflow_client)
    body = await _get(workflow_client, wf["id"], REQUESTER)
    assert body["generatedDescription"] is None


async def test_a_user_without_roles_still_reads_the_workflow(
    workflow_client: AsyncClient,
) -> None:
    """Reads stay open to every authenticated user — masked, never refused."""
    wf = await _modified(workflow_client)
    body = await _get(workflow_client, wf["id"], {"X-User-Roles": ""})
    assert body["status"] == "published"
    assert body["name"] == "my-workflow"


async def test_a_published_workflow_reads_the_same_for_everyone(
    workflow_client: AsyncClient,
) -> None:
    """Nothing has drifted, so the published view changes nothing."""
    skill = await create_skill(workflow_client)
    wf = await create_published_workflow(workflow_client, skill["id"])
    assert await _get(workflow_client, wf["id"], REQUESTER) == await _get(
        workflow_client, wf["id"], DEVELOPER
    )


async def test_discarding_the_changes_reunites_the_two_views(
    workflow_client: AsyncClient,
) -> None:
    """Once the edits are dropped there is only one design again."""
    wf = await _modified(workflow_client)
    assert_ok(
        await workflow_client.post(f"/api/v1/workflows/{wf['id']}/discard-changes")
    )
    assert await _get(workflow_client, wf["id"], REQUESTER) == await _get(
        workflow_client, wf["id"], DEVELOPER
    )


async def test_republishing_reveals_the_edits_to_everyone(
    workflow_client: AsyncClient,
) -> None:
    """Publishing is what promotes an edit into the design everyone else sees."""
    wf = await _modified(workflow_client)
    await publish_workflow(workflow_client, wf["id"])
    body = await _get(workflow_client, wf["id"], REQUESTER)
    assert body["name"] == "Renamed"
    assert [
        t["title"] for t in await _templates(workflow_client, wf["id"], REQUESTER)
    ] == [
        "Edited step",
        "Brand new step",
    ]


# ---------- listing and searching workflows ----------


async def test_the_list_shows_a_requester_the_published_name(
    workflow_client: AsyncClient,
) -> None:
    wf = await _modified(workflow_client)
    items = assert_ok(await workflow_client.get("/api/v1/workflows", headers=REQUESTER))
    row = next(x for x in items if x["id"] == wf["id"])
    assert row["name"] == "my-workflow"
    assert row["status"] == "published"


async def test_a_requester_searching_matches_the_published_name(
    workflow_client: AsyncClient,
) -> None:
    """Searching has to agree with what is displayed, or the page looks wrong."""
    wf = await _modified(workflow_client)
    found = assert_ok(
        await workflow_client.get(
            "/api/v1/workflows",
            headers=REQUESTER,
            params={"q": "name:like:my-workflow"},
        )
    )
    assert [x["id"] for x in found] == [wf["id"]]


async def test_a_requester_searching_never_matches_the_edited_name(
    workflow_client: AsyncClient,
) -> None:
    """Otherwise the unpublished name leaks through a yes/no answer."""
    await _modified(workflow_client)
    found = assert_ok(
        await workflow_client.get(
            "/api/v1/workflows", headers=REQUESTER, params={"q": "name:like:Renamed"}
        )
    )
    assert found == []


async def test_a_developer_searching_matches_the_edited_name(
    workflow_client: AsyncClient,
) -> None:
    wf = await _modified(workflow_client)
    found = assert_ok(
        await workflow_client.get(
            "/api/v1/workflows", headers=DEVELOPER, params={"q": "name:like:Renamed"}
        )
    )
    assert [x["id"] for x in found] == [wf["id"]]


async def test_a_requester_filtering_for_published_finds_a_modified_workflow(
    workflow_client: AsyncClient,
) -> None:
    """It reads as ``published``, so the status filter must agree."""
    wf = await _modified(workflow_client)
    found = assert_ok(
        await workflow_client.get(
            "/api/v1/workflows", headers=REQUESTER, params={"q": "status:eq:published"}
        )
    )
    assert wf["id"] in [x["id"] for x in found]


async def test_a_requester_filtering_for_modified_finds_nothing(
    workflow_client: AsyncClient,
) -> None:
    """That status does not exist from where they are standing."""
    await _modified(workflow_client)
    found = assert_ok(
        await workflow_client.get(
            "/api/v1/workflows", headers=REQUESTER, params={"q": "status:eq:modified"}
        )
    )
    assert found == []


async def test_a_requester_sorts_by_the_published_name(
    workflow_client: AsyncClient,
) -> None:
    """Ordering follows the displayed name, not the one hidden behind it."""
    skill = await create_skill(workflow_client)
    # Published "aaa", edited to "zzz": sorting by the live row would put it last.
    await create_modified_workflow(
        workflow_client, skill["id"], name="aaa-workflow", edited_name="zzz-workflow"
    )
    await create_published_workflow(workflow_client, skill["id"], name="mmm-workflow")
    items = assert_ok(
        await workflow_client.get(
            "/api/v1/workflows", headers=REQUESTER, params={"s": "name"}
        )
    )
    assert [x["name"] for x in items] == ["aaa-workflow", "mmm-workflow"]


# ---------- reading task templates ----------


async def test_a_developer_lists_the_edited_task_templates(
    workflow_client: AsyncClient,
) -> None:
    wf = await _modified(workflow_client)
    titles = [
        t["title"] for t in await _templates(workflow_client, wf["id"], DEVELOPER)
    ]
    assert titles == ["Edited step", "Brand new step"]


async def test_a_requester_lists_the_published_task_templates(
    workflow_client: AsyncClient,
) -> None:
    """The design a run of theirs would actually execute, and only that."""
    wf = await _modified(workflow_client)
    titles = [
        t["title"] for t in await _templates(workflow_client, wf["id"], REQUESTER)
    ]
    assert titles == ["Published step"]


async def test_a_requester_can_sort_the_published_task_templates(
    workflow_client: AsyncClient,
) -> None:
    """Sorting means the same thing on the snapshot as on the live rows."""
    skill = await create_skill(workflow_client)
    wf = await generate_workflow(workflow_client, skill["id"])
    await add_template(workflow_client, wf["id"], title="Zebra")
    await add_template(workflow_client, wf["id"], title="Apple")
    await publish_workflow(workflow_client, wf["id"])
    await add_template(workflow_client, wf["id"], title="Mango")

    assert [
        t["title"] for t in await _templates(workflow_client, wf["id"], REQUESTER)
    ] == ["Zebra", "Apple"]
    assert [
        t["title"]
        for t in await _templates(workflow_client, wf["id"], REQUESTER, s="title")
    ] == ["Apple", "Zebra"]


async def test_a_requester_can_filter_the_published_task_templates(
    workflow_client: AsyncClient,
) -> None:
    wf = await _modified(workflow_client)
    assert [
        t["title"]
        for t in await _templates(
            workflow_client, wf["id"], REQUESTER, q="title:like:published"
        )
    ] == ["Published step"]
    assert (
        await _templates(workflow_client, wf["id"], REQUESTER, q="title:like:Edited")
        == []
    )


async def test_a_requester_reads_a_published_template_by_id(
    workflow_client: AsyncClient,
) -> None:
    """The id survives an edit, so the same id must resolve to the published copy."""
    wf = await _modified(workflow_client)
    (published,) = await _templates(workflow_client, wf["id"], REQUESTER)
    body = assert_ok(
        await workflow_client.get(
            f"/api/v1/workflow-task-templates/{published['id']}", headers=REQUESTER
        )
    )
    assert body["title"] == "Published step"


async def test_a_developer_reads_the_edited_template_by_the_same_id(
    workflow_client: AsyncClient,
) -> None:
    wf = await _modified(workflow_client)
    (published,) = await _templates(workflow_client, wf["id"], REQUESTER)
    body = assert_ok(
        await workflow_client.get(
            f"/api/v1/workflow-task-templates/{published['id']}", headers=DEVELOPER
        )
    )
    assert body["title"] == "Edited step"


async def test_a_requester_cannot_read_a_template_added_since_publishing(
    workflow_client: AsyncClient,
) -> None:
    """An unpublished step has no published copy, so it reads as missing."""
    wf = await _modified(workflow_client)
    added = next(
        t
        for t in await _templates(workflow_client, wf["id"], DEVELOPER)
        if t["title"] == "Brand new step"
    )
    assert_err(
        await workflow_client.get(
            f"/api/v1/workflow-task-templates/{added['id']}", headers=REQUESTER
        ),
        "NOT_FOUND",
        404,
    )


async def test_published_templates_carry_their_audit_columns(
    workflow_client: AsyncClient,
) -> None:
    """The snapshot records them, so the read model is fully populated."""
    wf = await _modified(workflow_client)
    (published,) = await _templates(workflow_client, wf["id"], REQUESTER)
    assert published["createdAt"]
    assert published["createdBy"]
    assert published["workflowId"] == wf["id"]


@pytest.mark.parametrize("headers", [REQUESTER, DEVELOPER])
async def test_listing_templates_of_an_unknown_workflow_is_404_for_everyone(
    workflow_client: AsyncClient, headers: dict[str, str]
) -> None:
    """The published view must not turn a missing workflow into an empty page."""
    assert_err(
        await workflow_client.get(
            "/api/v1/workflows/no-such-workflow/task-templates", headers=headers
        ),
        "NOT_FOUND",
        404,
    )
