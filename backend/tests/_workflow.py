"""Shared helpers for driving the workflow lifecycle in API tests.

The lifecycle under test is: register a skill (the mocked sync job publishes a
revision) → "Generate workflow" from it (the mocked generation job flips it to
``draft``) → add task templates through the API → publish → execute. These
helpers keep that chain out of individual test bodies.
"""

from typing import Any

from httpx import AsyncClient

from tests._envelope import assert_ok

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
    """Generate a draft workflow from a skill (mocked background planning)."""
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


async def create_published_workflow(
    client: AsyncClient, skill_id: str, **overrides: object
) -> Any:
    """Generate a workflow, give it one template, and publish it."""
    workflow = await generate_workflow(client, skill_id, **overrides)
    await add_template(client, workflow["id"])
    return await publish_workflow(client, workflow["id"])
