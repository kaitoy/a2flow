"""A workflow's internal notes.

Notes are for the people who run a workflow -- why a version was restored, say
-- so only an ``admin``, ``developer``, or ``reviewer`` may read or write them,
including through a list filter. They are not part of the design: writing them
never marks a published workflow ``modified``, and publishing, restoring a
version, or discarding changes leaves them as they are.
"""

from typing import Any

from httpx import AsyncClient

from tests._envelope import assert_err, assert_ok
from tests._workflow import (
    add_template,
    create_skill,
    discard_workflow_changes,
    generate_workflow,
    publish_workflow,
)

REQUESTER = {"X-User-Roles": "requester"}
DEVELOPER = {"X-User-Roles": "developer"}
REVIEWER = {"X-User-Roles": "reviewer"}
ADMIN = {"X-User-Roles": "admin"}

NOTES = "Rolled back to v1: v2 mailed the wrong team"


async def _published(client: AsyncClient) -> Any:
    """Return a freshly published workflow."""
    skill = await create_skill(client)
    wf = await generate_workflow(client, skill["id"])
    await add_template(client, wf["id"])
    return await publish_workflow(client, wf["id"])


async def _put_notes(
    client: AsyncClient, workflow_id: str, notes: str | None, headers: Any = None
) -> Any:
    return await client.put(
        f"/api/v1/workflows/{workflow_id}/internal-notes",
        json={"internalNotes": notes},
        headers=headers,
    )


async def _get(client: AsyncClient, workflow_id: str, headers: Any = None) -> Any:
    return assert_ok(
        await client.get(f"/api/v1/workflows/{workflow_id}", headers=headers)
    )


async def test_admin_developer_and_reviewer_can_write_notes(
    workflow_client: AsyncClient,
) -> None:
    wf = await _published(workflow_client)
    for headers in (ADMIN, DEVELOPER, REVIEWER):
        body = assert_ok(await _put_notes(workflow_client, wf["id"], NOTES, headers))
        assert body["internalNotes"] == NOTES
        assert (await _get(workflow_client, wf["id"], headers))[
            "internalNotes"
        ] == NOTES


async def test_a_requester_can_neither_write_nor_read_notes(
    workflow_client: AsyncClient,
) -> None:
    wf = await _published(workflow_client)
    assert_err(
        await _put_notes(workflow_client, wf["id"], "x", REQUESTER), "FORBIDDEN", 403
    )
    assert_ok(await _put_notes(workflow_client, wf["id"], NOTES))
    assert (await _get(workflow_client, wf["id"], REQUESTER))["internalNotes"] is None


async def test_a_requester_cannot_filter_on_the_notes(
    workflow_client: AsyncClient,
) -> None:
    """Filtering would otherwise read the hidden notes back one guess at a time."""
    wf = await _published(workflow_client)
    assert_ok(await _put_notes(workflow_client, wf["id"], NOTES))
    params = {"q": "internalNotes:like:Rolled"}
    hidden = assert_ok(
        await workflow_client.get("/api/v1/workflows", headers=REQUESTER, params=params)
    )
    shown = assert_ok(
        await workflow_client.get("/api/v1/workflows", headers=DEVELOPER, params=params)
    )
    assert hidden == []
    assert [w["id"] for w in shown] == [wf["id"]]


async def test_writing_notes_keeps_a_published_workflow_published(
    workflow_client: AsyncClient,
) -> None:
    wf = await _published(workflow_client)
    body = assert_ok(await _put_notes(workflow_client, wf["id"], NOTES, REVIEWER))
    assert body["status"] == "published"


async def test_an_empty_string_clears_the_notes(workflow_client: AsyncClient) -> None:
    wf = await _published(workflow_client)
    assert_ok(await _put_notes(workflow_client, wf["id"], NOTES))
    body = assert_ok(await _put_notes(workflow_client, wf["id"], ""))
    assert body["internalNotes"] is None


async def test_patch_ignores_notes(workflow_client: AsyncClient) -> None:
    """The design PATCH cannot write notes, so it cannot bypass the notes route."""
    wf = await _published(workflow_client)
    body = assert_ok(
        await workflow_client.patch(
            f"/api/v1/workflows/{wf['id']}", json={"internalNotes": NOTES}
        )
    )
    assert body["internalNotes"] is None


async def test_notes_survive_discard_publish_and_restore(
    workflow_client: AsyncClient,
) -> None:
    wf = await _published(workflow_client)
    assert_ok(await _put_notes(workflow_client, wf["id"], NOTES))

    assert_ok(
        await workflow_client.patch(f"/api/v1/workflows/{wf['id']}", json={"name": "B"})
    )
    assert (await discard_workflow_changes(workflow_client, wf["id"]))[
        "internalNotes"
    ] == NOTES

    assert_ok(
        await workflow_client.patch(f"/api/v1/workflows/{wf['id']}", json={"name": "C"})
    )
    assert (await publish_workflow(workflow_client, wf["id"]))["internalNotes"] == NOTES

    restored = assert_ok(
        await workflow_client.post(f"/api/v1/workflows/{wf['id']}/versions/1/restore")
    )
    assert restored["internalNotes"] == NOTES
