"""A workflow's prompt versus its description.

``prompt`` / ``generated_prompt`` are what a run is told to do, so only an
``admin``, ``developer``, or ``reviewer`` may read them -- on the workflow,
in its version history, and on the runs copied from it, including through a
list filter. ``description`` is plain prose for people: readable by anyone who
can read the workflow, and versioned with it like its name.
"""

from typing import Any

from httpx import AsyncClient

from tests._envelope import assert_err, assert_ok
from tests._workflow import (
    add_template,
    create_skill,
    discard_workflow_changes,
    execute_workflow,
    generate_workflow,
    publish_workflow,
)

REQUESTER = {"X-User-Roles": "requester"}
DEVELOPER = {"X-User-Roles": "developer"}
REVIEWER = {"X-User-Roles": "reviewer"}
ADMIN = {"X-User-Roles": "admin"}

PROMPT = "Secret run instructions"


async def _published(client: AsyncClient) -> Any:
    """Publish a workflow carrying both a prompt and a description."""
    skill = await create_skill(client)
    wf = await generate_workflow(client, skill["id"])
    assert_ok(
        await client.patch(
            f"/api/v1/workflows/{wf['id']}",
            json={"prompt": PROMPT, "description": "What it is for"},
        )
    )
    await add_template(client, wf["id"])
    return await publish_workflow(client, wf["id"])


async def _get(client: AsyncClient, workflow_id: str, headers: Any) -> Any:
    return assert_ok(
        await client.get(f"/api/v1/workflows/{workflow_id}", headers=headers)
    )


async def test_prompt_is_shown_to_admin_developer_and_reviewer(
    workflow_client: AsyncClient,
) -> None:
    wf = await _published(workflow_client)
    for headers in (ADMIN, DEVELOPER, REVIEWER):
        assert (await _get(workflow_client, wf["id"], headers))["prompt"] == PROMPT


async def test_prompt_is_hidden_from_a_requester_but_description_is_not(
    workflow_client: AsyncClient,
) -> None:
    wf = await _published(workflow_client)
    body = await _get(workflow_client, wf["id"], REQUESTER)
    assert body["prompt"] is None
    assert body["generatedPrompt"] is None
    assert body["description"] == "What it is for"


async def test_a_requester_cannot_filter_on_the_prompt(
    workflow_client: AsyncClient,
) -> None:
    """Filtering would otherwise read the hidden prompt back one guess at a time."""
    await _published(workflow_client)
    params = {"q": "prompt:like:Secret"}
    hidden = assert_ok(
        await workflow_client.get("/api/v1/workflows", headers=REQUESTER, params=params)
    )
    shown = assert_ok(
        await workflow_client.get("/api/v1/workflows", headers=DEVELOPER, params=params)
    )
    assert hidden == []
    assert len(shown) == 1


async def test_a_run_hides_its_prompt_from_its_requester(
    workflow_client: AsyncClient,
) -> None:
    wf = await _published(workflow_client)
    execution = await execute_workflow(workflow_client, wf["id"], headers=REQUESTER)
    assert execution["prompt"] is None
    path = f"/api/v1/workflow-executions/{execution['id']}"
    assert (
        assert_ok(await workflow_client.get(path, headers=REQUESTER))["prompt"] is None
    )
    assert assert_ok(await workflow_client.get(path, headers=ADMIN))["prompt"] == PROMPT
    params = {"q": "prompt:like:Secret"}
    assert (
        assert_ok(
            await workflow_client.get(
                "/api/v1/workflow-executions", headers=REQUESTER, params=params
            )
        )
        == []
    )


async def test_version_history_shows_the_prompt_to_whoever_may_open_it(
    workflow_client: AsyncClient,
) -> None:
    """The history is closed to a requester outright, so its readers see the prompt."""
    wf = await _published(workflow_client)
    path = f"/api/v1/workflows/{wf['id']}/versions"
    assert_err(await workflow_client.get(path, headers=REQUESTER), "FORBIDDEN", 403)
    for headers in (DEVELOPER, REVIEWER, ADMIN):
        [shown] = assert_ok(await workflow_client.get(path, headers=headers))
        assert shown["prompt"] == PROMPT
        assert shown["description"] == "What it is for"


async def test_editing_the_description_is_a_change_to_publish(
    workflow_client: AsyncClient,
) -> None:
    """The description is versioned like the name, and discarding restores it."""
    wf = await _published(workflow_client)
    edited = assert_ok(
        await workflow_client.patch(
            f"/api/v1/workflows/{wf['id']}", json={"description": "Edited"}
        )
    )
    assert edited["status"] == "modified"
    assert (await _get(workflow_client, wf["id"], REQUESTER))["description"] == (
        "What it is for"
    )
    restored = await discard_workflow_changes(workflow_client, wf["id"])
    assert restored["description"] == "What it is for"
    assert restored["prompt"] == PROMPT
