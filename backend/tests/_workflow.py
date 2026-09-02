"""Shared helpers for driving the workflow lifecycle in API tests.

The lifecycle under test is: register a skill (the mocked sync job publishes a
revision) → "Generate workflow" from it (the mocked generation job flips it to
``draft``) → add task templates through the API → publish → execute. These
helpers keep that chain out of individual test bodies.
"""

from typing import Any

from google.adk.events.event import Event
from google.adk.sessions import BaseSessionService
from google.genai import types
from httpx import AsyncClient

from dependencies import APP_NAME
from infrastructure.agent import tenant_app_name
from tests._envelope import assert_err, assert_ok

SKILL_BODY = {"name": "skill-a", "repo_url": "https://github.com/x/y"}
GENERATE_BODY = {"name": "my-workflow", "prompt": "Do the thing"}


async def create_skill(client: AsyncClient, **overrides: object) -> Any:
    """Register an AgentSkill; the mocked sync job publishes its revision."""
    return assert_ok(
        await client.post("/api/v1/agent-skills", json={**SKILL_BODY, **overrides}),
        status=201,
    )


async def generate_workflow(
    client: AsyncClient, skill_id: str, **overrides: object
) -> Any:
    """Generate a draft workflow from a skill (mocked background design)."""
    return assert_ok(
        await client.post(
            f"/api/v1/agent-skills/{skill_id}/workflows",
            json={**GENERATE_BODY, **overrides},
        ),
        status=201,
    )


async def add_template(
    client: AsyncClient, workflow_id: str, title: str = "Step 1", **overrides: object
) -> Any:
    """Add one task template to a workflow through the admin API."""
    body = {"workflow_id": workflow_id, "title": title, **overrides}
    return assert_ok(
        await client.post("/api/v1/workflow-task-templates", json=body), status=201
    )


async def publish_workflow(client: AsyncClient, workflow_id: str) -> Any:
    """Publish a workflow, making it executable."""
    return assert_ok(await client.post(f"/api/v1/workflows/{workflow_id}/publish"))


async def discard_workflow_changes(client: AsyncClient, workflow_id: str) -> Any:
    """Drop a modified workflow's edits, restoring its last published version."""
    return assert_ok(
        await client.post(f"/api/v1/workflows/{workflow_id}/discard-changes")
    )


async def deactivate_workflow(client: AsyncClient, workflow_id: str) -> Any:
    """Deactivate a published/modified workflow, returning it to draft."""
    return assert_ok(await client.post(f"/api/v1/workflows/{workflow_id}/deactivate"))


async def seed_design_transcript(
    client: AsyncClient,
    session_service: BaseSessionService,
    workflow_id: str,
    text: str = "Build me a report",
) -> None:
    """Give a workflow's design session a one-turn ADK conversation.

    The mocked generation job never opens an ADK session, so a workflow created
    through these helpers has an empty transcript. Tests that need one — the
    description summarizer reads it — seed it here.
    """
    workflow = assert_ok(await client.get(f"/api/v1/workflows/{workflow_id}"))
    session = await session_service.create_session(
        app_name=tenant_app_name(APP_NAME, workflow["tenantId"]),
        user_id=workflow["createdBy"],
        session_id=workflow["sessionId"],
    )
    await session_service.append_event(
        session,
        Event(
            author="user",
            content=types.Content(role="user", parts=[types.Part(text=text)]),
        ),
    )


async def create_published_workflow(
    client: AsyncClient, skill_id: str, **overrides: object
) -> Any:
    """Generate a workflow, give it one template, and publish it."""
    workflow = await generate_workflow(client, skill_id, **overrides)
    await add_template(client, workflow["id"])
    return await publish_workflow(client, workflow["id"])


async def create_modified_workflow(
    client: AsyncClient,
    skill_id: str,
    *,
    published_title: str = "Published step",
    edited_title: str = "Edited step",
    edited_name: str = "Renamed",
    **overrides: object,
) -> Any:
    """Publish a workflow, then edit it so it lands in ``modified``.

    The published design has exactly one template titled ``published_title``;
    the unpublished edits rename that template to ``edited_title``, rename the
    workflow to ``edited_name``, and add a second template. That gives every
    caller-visibility test a case where the live rows and the snapshot differ
    in name, in title, and in count.

    Args:
        client: The API client to drive.
        skill_id: The skill to generate the workflow from.
        published_title: Title of the one template captured at publish time.
        edited_title: Title that template is renamed to afterwards.
        edited_name: Name the workflow is renamed to afterwards.
        **overrides: Extra fields for the generation request.

    Returns:
        The workflow as it reads *to a developer* after the edits.
    """
    workflow = await generate_workflow(client, skill_id, **overrides)
    template = await add_template(client, workflow["id"], title=published_title)
    await publish_workflow(client, workflow["id"])
    assert_ok(
        await client.patch(
            f"/api/v1/workflow-task-templates/{template['id']}",
            json={"title": edited_title},
        )
    )
    await add_template(client, workflow["id"], title="Brand new step")
    return assert_ok(
        await client.patch(
            f"/api/v1/workflows/{workflow['id']}", json={"name": edited_name}
        )
    )


async def execute_workflow(
    client: AsyncClient,
    workflow_id: str,
    *,
    headers: dict[str, str] | None = None,
    **body: object,
) -> Any:
    """Execute a workflow, asserting it started.

    Args:
        client: The API client to drive.
        workflow_id: The workflow to run.
        headers: Extra request headers, e.g. to act as another role.
        **body: Fields of the execute request, such as ``designSource``.

    Returns:
        The created execution.
    """
    return assert_ok(
        await client.post(
            f"/api/v1/workflows/{workflow_id}/execute",
            json=body or None,
            headers=headers,
        ),
        status=201,
    )


async def execute_workflow_err(
    client: AsyncClient,
    workflow_id: str,
    *,
    code: str,
    status: int,
    headers: dict[str, str] | None = None,
    **body: object,
) -> dict[str, Any]:
    """Execute a workflow, asserting it was refused with the given error.

    Args:
        client: The API client to drive.
        workflow_id: The workflow to run.
        code: Expected error code in the envelope.
        status: Expected HTTP status.
        headers: Extra request headers, e.g. to act as another role.
        **body: Fields of the execute request, such as ``designSource``.

    Returns:
        The error body, so callers can assert on its ``details``.
    """
    return assert_err(
        await client.post(
            f"/api/v1/workflows/{workflow_id}/execute",
            json=body or None,
            headers=headers,
        ),
        code,
        status,
    )


async def execution_task_titles(client: AsyncClient, execution_id: str) -> list[str]:
    """Return the titles of the tasks copied into a run, in list order."""
    tasks = assert_ok(
        await client.get(f"/api/v1/workflow-executions/{execution_id}/workflow-tasks")
    )
    return [t["title"] for t in tasks]
