"""Tests for the ``/tags`` endpoints and for attaching tags to records.

Covers the tag CRUD surface, its tenant boundary, the ``PUT /{resource}/{id}/tags``
sub-resource on the taggable resources, the conjunctive ``?tag=`` list filter,
the two invariants the whole feature rests on -- renaming a tag keeps every
attachment, and deleting one detaches it everywhere rather than being blocked by
the records carrying it -- and the access-control predicate an ``accessControl``
tag adds on top (see :mod:`models.tag`). Also covers the derived case: a
WorkflowExecution copies its workflow's tags at execute time, and an Approval
carries no tags of its own but is gated by its execution's -- so losing the
group that holds an access-control tag hides both, even from a run's own
initiator or a designated approver.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.bootstrap import seed_system_user
from models.agent_skill import AgentSkill, AgentSkillRead
from models.approval import Approval
from models.mcp_server import MCPServer, McpServerRead
from models.mcp_tool_mock import MCPToolMock, McpToolMockRead
from models.secret import Secret, SecretRead
from models.tag import MAX_RECORD_TAGS
from models.user import SYSTEM_USER_ID
from models.user_group import UserGroup, UserGroupRead
from models.workflow import Workflow, WorkflowRead
from tests._engine import make_test_engine
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users
from tests._workflow import create_published_workflow, create_skill, execute_workflow
from tests.conftest import _install_auth_overrides

#: A second tenant used by the isolation tests.
OTHER_TENANT_ID = "tenant-other"

#: Headers selecting a plain (non-super-admin) admin of the default tenant.
ADMIN: dict[str, str] = {"X-User-Id": "alice", "X-User-Roles": "admin"}

#: Headers selecting a developer of the default tenant.
DEVELOPER: dict[str, str] = {"X-User-Id": "bob", "X-User-Roles": "developer"}

#: Headers selecting a role-less user of the default tenant.
NOBODY: dict[str, str] = {"X-User-Id": "carol", "X-User-Roles": ""}

#: Headers selecting an admin belonging to the *other* tenant.
OUTSIDER: dict[str, str] = {
    "X-User-Id": "outsider",
    "X-User-Roles": "admin",
    "X-User-Tenant-Id": OTHER_TENANT_ID,
}


@pytest_asyncio.fixture()
async def tag_env() -> AsyncGenerator[tuple[AsyncClient, AsyncEngine], None]:
    """Yield an API client plus the throwaway engine backing it."""
    from infrastructure.database import get_session
    from main import app

    mem_engine = await make_test_engine()
    async with AsyncSession(mem_engine) as session:
        await seed_system_user(session)
    await seed_tenant(mem_engine, DEFAULT_TEST_TENANT_ID)
    await seed_tenant(mem_engine, OTHER_TENANT_ID)
    await seed_users(mem_engine, ("alice", "bob", "carol"), roles=())
    await seed_users(mem_engine, ("outsider",), roles=(), tenant_id=OTHER_TENANT_ID)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    _install_auth_overrides(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-Id": SYSTEM_USER_ID},
        ) as ac:
            yield ac, mem_engine
    finally:
        app.dependency_overrides.clear()
        await mem_engine.dispose()


async def _create_tag(
    client: AsyncClient, name: str = "production", **overrides: Any
) -> dict[str, Any]:
    """Create a tag through the API and return it."""
    body: dict[str, Any] = {"name": name}
    body.update(overrides)
    response = await client.post("/api/v1/tags", json=body, headers=ADMIN)
    return dict(assert_ok(response, 201))


async def _create_secret(client: AsyncClient, name: str = "creds") -> dict[str, Any]:
    """Create a local secret through the API and return it."""
    response = await client.post(
        "/api/v1/secrets",
        json={"name": name, "type": "local", "entries": {"token": "t"}},
        headers=ADMIN,
    )
    return dict(assert_ok(response, 201))


async def _set_secret_tags(
    client: AsyncClient, secret_id: str, tag_ids: list[str]
) -> dict[str, Any]:
    """Attach ``tag_ids`` to a secret and return the updated read model."""
    response = await client.put(
        f"/api/v1/secrets/{secret_id}/tags", json={"tagIds": tag_ids}, headers=ADMIN
    )
    return dict(assert_ok(response))


async def _create_tool_mock(
    client: AsyncClient, name: str = "approve-mock"
) -> dict[str, Any]:
    """Create a built-in-tool mock through the API and return it."""
    response = await client.post(
        "/api/v1/mcp-tool-mocks",
        json={
            "name": name,
            "toolName": "request_approval",
            "responses": [{"kind": "text", "value": "ok"}],
        },
        headers=DEVELOPER,
    )
    return dict(assert_ok(response, 201))


async def _set_tool_mock_tags(
    client: AsyncClient, mock_id: str, tag_ids: list[str]
) -> dict[str, Any]:
    """Attach ``tag_ids`` to a tool mock and return the updated read model."""
    response = await client.put(
        f"/api/v1/mcp-tool-mocks/{mock_id}/tags",
        json={"tagIds": tag_ids},
        headers=DEVELOPER,
    )
    return dict(assert_ok(response))


async def _create_user_group(
    client: AsyncClient, name: str = "developers"
) -> dict[str, Any]:
    """Create an empty user group through the API and return it."""
    response = await client.post(
        "/api/v1/user-groups", json={"name": name}, headers=ADMIN
    )
    return dict(assert_ok(response, 201))


async def _set_user_group_tags(
    client: AsyncClient, group_id: str, tag_ids: list[str]
) -> dict[str, Any]:
    """Attach ``tag_ids`` to a user group and return the updated read model."""
    response = await client.put(
        f"/api/v1/user-groups/{group_id}/tags", json={"tagIds": tag_ids}, headers=ADMIN
    )
    return dict(assert_ok(response))


# ---------- CRUD ----------


async def test_create_returns_the_tag_with_its_defaults(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    tag = await _create_tag(client)
    assert tag["name"] == "production"
    assert tag["color"] == "slate"
    assert tag["tenantId"] == DEFAULT_TEST_TENANT_ID
    assert tag["description"] is None


async def test_create_accepts_a_palette_slot(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    tag = await _create_tag(client, color="violet")
    assert tag["color"] == "violet"


async def test_create_accepts_a_description(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    tag = await _create_tag(client, description="Live customer-facing environment.")
    assert tag["description"] == "Live customer-facing environment."
    fetched = assert_ok(await client.get(f"/api/v1/tags/{tag['id']}", headers=NOBODY))
    assert fetched["description"] == "Live customer-facing environment."


async def test_create_rejects_a_color_outside_the_palette(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    response = await client.post(
        "/api/v1/tags", json={"name": "x", "color": "#ff0000"}, headers=ADMIN
    )
    assert_err(response, "VALIDATION_ERROR", 422)


async def test_create_rejects_a_duplicate_name_within_the_tenant(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    await _create_tag(client)
    response = await client.post(
        "/api/v1/tags", json={"name": "production"}, headers=ADMIN
    )
    assert_err(response, "CONFLICT_UNIQUE", 409)


async def test_list_orders_tags_by_name(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    await _create_tag(client, "zulu")
    await _create_tag(client, "alpha")
    tags = assert_ok(await client.get("/api/v1/tags", headers=NOBODY))
    assert [t["name"] for t in tags] == ["alpha", "zulu"]


async def test_get_returns_the_tag(tag_env: tuple[AsyncClient, AsyncEngine]) -> None:
    client, _ = tag_env
    tag = await _create_tag(client)
    fetched = assert_ok(await client.get(f"/api/v1/tags/{tag['id']}", headers=NOBODY))
    assert fetched["id"] == tag["id"]


async def test_get_of_an_unknown_tag_is_404(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    assert_err(await client.get("/api/v1/tags/nope", headers=NOBODY), "NOT_FOUND", 404)


# ---------- role gates ----------


async def test_a_developer_may_create_a_tag(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    response = await client.post(
        "/api/v1/tags", json={"name": "aws"}, headers=DEVELOPER
    )
    assert_ok(response, 201)


async def test_a_role_less_user_may_not_create_a_tag(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    response = await client.post("/api/v1/tags", json={"name": "aws"}, headers=NOBODY)
    assert_err(response, "FORBIDDEN", 403)


async def test_a_role_less_user_may_still_read_tags(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    await _create_tag(client)
    assert len(assert_ok(await client.get("/api/v1/tags", headers=NOBODY))) == 1


async def test_a_role_less_user_may_not_delete_a_tag(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    tag = await _create_tag(client)
    response = await client.delete(f"/api/v1/tags/{tag['id']}", headers=NOBODY)
    assert_err(response, "FORBIDDEN", 403)


# ---------- tenant isolation ----------


async def test_another_tenants_tag_is_invisible(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    tag = await _create_tag(client)
    response = await client.get(f"/api/v1/tags/{tag['id']}", headers=OUTSIDER)
    assert_err(response, "NOT_FOUND", 404)


async def test_the_same_tag_name_may_exist_in_two_tenants(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    await _create_tag(client)
    response = await client.post(
        "/api/v1/tags", json={"name": "production"}, headers=OUTSIDER
    )
    assert_ok(response, 201)


async def test_attaching_another_tenants_tag_is_rejected(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    foreign = dict(
        assert_ok(
            await client.post(
                "/api/v1/tags", json={"name": "foreign"}, headers=OUTSIDER
            ),
            201,
        )
    )
    secret = await _create_secret(client)
    response = await client.put(
        f"/api/v1/secrets/{secret['id']}/tags",
        json={"tagIds": [foreign["id"]]},
        headers=ADMIN,
    )
    assert_err(response, "FOREIGN_KEY_VIOLATION", 422)


# ---------- attaching ----------


async def test_setting_tags_returns_them_sorted(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    first = await _create_tag(client, "a")
    second = await _create_tag(client, "b")
    secret = await _create_secret(client)
    updated = await _set_secret_tags(client, secret["id"], [second["id"], first["id"]])
    assert updated["tagIds"] == sorted([first["id"], second["id"]])


async def test_setting_tags_replaces_the_previous_selection(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    first = await _create_tag(client, "a")
    second = await _create_tag(client, "b")
    secret = await _create_secret(client)
    await _set_secret_tags(client, secret["id"], [first["id"]])
    updated = await _set_secret_tags(client, secret["id"], [second["id"]])
    assert updated["tagIds"] == [second["id"]]


async def test_setting_an_empty_list_detaches_every_tag(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    tag = await _create_tag(client)
    secret = await _create_secret(client)
    await _set_secret_tags(client, secret["id"], [tag["id"]])
    assert await _set_secret_tags(client, secret["id"], []) == {
        **await _set_secret_tags(client, secret["id"], []),
        "tagIds": [],
    }


async def test_setting_the_same_tag_twice_is_deduplicated(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    tag = await _create_tag(client)
    secret = await _create_secret(client)
    updated = await _set_secret_tags(client, secret["id"], [tag["id"], tag["id"]])
    assert updated["tagIds"] == [tag["id"]]


async def test_setting_more_tags_than_allowed_is_rejected(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    secret = await _create_secret(client)
    response = await client.put(
        f"/api/v1/secrets/{secret['id']}/tags",
        json={"tagIds": [f"tag-{i}" for i in range(MAX_RECORD_TAGS + 1)]},
        headers=ADMIN,
    )
    assert_err(response, "VALIDATION_ERROR", 422)


async def test_setting_tags_on_an_unknown_record_is_404(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    response = await client.put(
        "/api/v1/secrets/nope/tags", json={"tagIds": []}, headers=ADMIN
    )
    assert_err(response, "NOT_FOUND", 404)


async def test_setting_tags_requires_the_records_own_write_role(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    secret = await _create_secret(client)
    # Attaching tags is gated by the target record's own write role, not by
    # tag-mint eligibility — a role-less caller fails here for the same reason
    # it would fail POST /secrets, regardless of what mints a tag.
    response = await client.put(
        f"/api/v1/secrets/{secret['id']}/tags", json={"tagIds": []}, headers=NOBODY
    )
    assert_err(response, "FORBIDDEN", 403)


# ---------- rename and delete ----------


async def test_renaming_a_tag_keeps_every_attachment(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    tag = await _create_tag(client)
    secret = await _create_secret(client)
    await _set_secret_tags(client, secret["id"], [tag["id"]])

    renamed = assert_ok(
        await client.patch(
            f"/api/v1/tags/{tag['id']}", json={"name": "prod"}, headers=ADMIN
        )
    )
    assert renamed["name"] == "prod"

    fetched = assert_ok(
        await client.get(f"/api/v1/secrets/{secret['id']}", headers=ADMIN)
    )
    assert fetched["tagIds"] == [tag["id"]]


async def test_updating_a_tag_sets_its_description(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    tag = await _create_tag(client)
    updated = assert_ok(
        await client.patch(
            f"/api/v1/tags/{tag['id']}",
            json={"description": "Live customer-facing environment."},
            headers=ADMIN,
        )
    )
    assert updated["description"] == "Live customer-facing environment."


async def test_updating_a_tag_clears_its_description(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    tag = await _create_tag(client, description="Live customer-facing environment.")
    updated = assert_ok(
        await client.patch(
            f"/api/v1/tags/{tag['id']}", json={"description": None}, headers=ADMIN
        )
    )
    assert updated["description"] is None


async def test_deleting_a_tag_detaches_it_everywhere(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    doomed = await _create_tag(client, "doomed")
    kept = await _create_tag(client, "kept")
    secret = await _create_secret(client)
    await _set_secret_tags(client, secret["id"], [doomed["id"], kept["id"]])

    assert_ok(await client.delete(f"/api/v1/tags/{doomed['id']}", headers=ADMIN))

    fetched = assert_ok(
        await client.get(f"/api/v1/secrets/{secret['id']}", headers=ADMIN)
    )
    assert fetched["tagIds"] == [kept["id"]]


async def test_deleting_a_record_removes_its_attachments(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, mem_engine = tag_env
    tag = await _create_tag(client)
    secret = await _create_secret(client)
    await _set_secret_tags(client, secret["id"], [tag["id"]])

    assert_ok(await client.delete(f"/api/v1/secrets/{secret['id']}", headers=ADMIN))

    from sqlmodel import select

    from models.tag import SecretTag

    async with AsyncSession(mem_engine) as session:
        rows = (await session.exec(select(SecretTag))).all()
    assert rows == []


# ---------- filtering ----------


async def test_tag_filter_is_conjunctive(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    aws = await _create_tag(client, "aws")
    prod = await _create_tag(client, "prod")
    both = await _create_secret(client, "both")
    only_aws = await _create_secret(client, "only-aws")
    await _set_secret_tags(client, both["id"], [aws["id"], prod["id"]])
    await _set_secret_tags(client, only_aws["id"], [aws["id"]])

    one = assert_ok(await client.get(f"/api/v1/secrets?tag={aws['id']}", headers=ADMIN))
    assert {s["name"] for s in one} == {"both", "only-aws"}

    two = assert_ok(
        await client.get(
            f"/api/v1/secrets?tag={aws['id']}&tag={prod['id']}", headers=ADMIN
        )
    )
    assert {s["name"] for s in two} == {"both"}


async def test_tag_filter_applies_before_paging(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    tag = await _create_tag(client)
    tagged = await _create_secret(client, "tagged")
    await _create_secret(client, "untagged")
    await _set_secret_tags(client, tagged["id"], [tag["id"]])

    page = assert_ok(
        await client.get(f"/api/v1/secrets?tag={tag['id']}&limit=1", headers=ADMIN)
    )
    assert [s["name"] for s in page] == ["tagged"]


async def test_an_unknown_tag_id_matches_nothing(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    await _create_secret(client)
    assert assert_ok(await client.get("/api/v1/secrets?tag=nope", headers=ADMIN)) == []


async def test_too_many_tag_filters_are_rejected(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    query = "&".join(f"tag=t{i}" for i in range(MAX_RECORD_TAGS + 1))
    response = await client.get(f"/api/v1/secrets?{query}", headers=ADMIN)
    assert_err(response, "INVALID_QUERY", 400)


async def test_tags_are_not_a_filterable_field(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """``tagIds`` is a separate axis, not a pseudo-column of the ``q`` grammar."""
    client, _ = tag_env
    response = await client.get("/api/v1/secrets?q=tagIds:eq:x", headers=ADMIN)
    assert_err(response, "INVALID_QUERY", 400)


async def test_tags_are_not_a_sortable_field(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    response = await client.get("/api/v1/secrets?s=tagIds", headers=ADMIN)
    assert_err(response, "INVALID_QUERY", 400)


# ---------- tool mocks ----------


async def test_tool_mock_tags_round_trip_sorted(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    first = await _create_tag(client, "a")
    second = await _create_tag(client, "b")
    mock = await _create_tool_mock(client)
    updated = await _set_tool_mock_tags(client, mock["id"], [second["id"], first["id"]])
    assert updated["tagIds"] == sorted([first["id"], second["id"]])

    fetched = assert_ok(
        await client.get(f"/api/v1/mcp-tool-mocks/{mock['id']}", headers=DEVELOPER)
    )
    assert fetched["tagIds"] == sorted([first["id"], second["id"]])


async def test_tool_mock_tag_filter_is_conjunctive(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    aws = await _create_tag(client, "aws")
    prod = await _create_tag(client, "prod")
    both = await _create_tool_mock(client, "both")
    only_aws = await _create_tool_mock(client, "only-aws")
    await _set_tool_mock_tags(client, both["id"], [aws["id"], prod["id"]])
    await _set_tool_mock_tags(client, only_aws["id"], [aws["id"]])

    one = assert_ok(
        await client.get(f"/api/v1/mcp-tool-mocks?tag={aws['id']}", headers=DEVELOPER)
    )
    assert {m["name"] for m in one} == {"both", "only-aws"}

    two = assert_ok(
        await client.get(
            f"/api/v1/mcp-tool-mocks?tag={aws['id']}&tag={prod['id']}",
            headers=DEVELOPER,
        )
    )
    assert {m["name"] for m in two} == {"both"}


async def test_tool_mock_tagging_requires_developer(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    mock = await _create_tool_mock(client)
    response = await client.put(
        f"/api/v1/mcp-tool-mocks/{mock['id']}/tags",
        json={"tagIds": []},
        headers=NOBODY,
    )
    assert_err(response, "FORBIDDEN", 403)


async def test_deleting_a_tool_mock_removes_its_attachments(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, mem_engine = tag_env
    tag = await _create_tag(client)
    mock = await _create_tool_mock(client)
    await _set_tool_mock_tags(client, mock["id"], [tag["id"]])

    assert_ok(
        await client.delete(f"/api/v1/mcp-tool-mocks/{mock['id']}", headers=DEVELOPER)
    )

    from sqlmodel import select

    from models.tag import McpToolMockTag

    async with AsyncSession(mem_engine) as session:
        rows = (await session.exec(select(McpToolMockTag))).all()
    assert rows == []


# ---------- user groups ----------


async def test_user_group_tags_round_trip_sorted(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    first = await _create_tag(client, "a")
    second = await _create_tag(client, "b")
    group = await _create_user_group(client)
    updated = await _set_user_group_tags(
        client, group["id"], [second["id"], first["id"]]
    )
    assert updated["tagIds"] == sorted([first["id"], second["id"]])

    fetched = assert_ok(
        await client.get(f"/api/v1/user-groups/{group['id']}", headers=ADMIN)
    )
    assert fetched["tagIds"] == sorted([first["id"], second["id"]])


async def test_user_group_tag_filter_is_conjunctive(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    aws = await _create_tag(client, "aws")
    prod = await _create_tag(client, "prod")
    both = await _create_user_group(client, "both")
    only_aws = await _create_user_group(client, "only-aws")
    await _set_user_group_tags(client, both["id"], [aws["id"], prod["id"]])
    await _set_user_group_tags(client, only_aws["id"], [aws["id"]])

    one = assert_ok(
        await client.get(f"/api/v1/user-groups?tag={aws['id']}", headers=ADMIN)
    )
    assert {g["name"] for g in one} == {"both", "only-aws"}

    two = assert_ok(
        await client.get(
            f"/api/v1/user-groups?tag={aws['id']}&tag={prod['id']}", headers=ADMIN
        )
    )
    assert {g["name"] for g in two} == {"both"}


async def test_user_group_tagging_requires_admin(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    group = await _create_user_group(client)
    response = await client.put(
        f"/api/v1/user-groups/{group['id']}/tags",
        json={"tagIds": []},
        headers=DEVELOPER,
    )
    assert_err(response, "FORBIDDEN", 403)


async def test_renaming_a_tag_keeps_a_user_group_attachment(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    tag = await _create_tag(client)
    group = await _create_user_group(client)
    await _set_user_group_tags(client, group["id"], [tag["id"]])

    assert_ok(
        await client.patch(
            f"/api/v1/tags/{tag['id']}", json={"name": "devs"}, headers=ADMIN
        )
    )

    fetched = assert_ok(
        await client.get(f"/api/v1/user-groups/{group['id']}", headers=ADMIN)
    )
    assert fetched["tagIds"] == [tag["id"]]


async def test_deleting_a_tag_detaches_it_from_a_user_group(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    doomed = await _create_tag(client, "doomed")
    kept = await _create_tag(client, "kept")
    group = await _create_user_group(client)
    await _set_user_group_tags(client, group["id"], [doomed["id"], kept["id"]])

    assert_ok(await client.delete(f"/api/v1/tags/{doomed['id']}", headers=ADMIN))

    fetched = assert_ok(
        await client.get(f"/api/v1/user-groups/{group['id']}", headers=ADMIN)
    )
    assert fetched["tagIds"] == [kept["id"]]


async def test_attaching_another_tenants_tag_to_a_user_group_is_rejected(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    foreign = dict(
        assert_ok(
            await client.post(
                "/api/v1/tags", json={"name": "foreign"}, headers=OUTSIDER
            ),
            201,
        )
    )
    group = await _create_user_group(client)
    response = await client.put(
        f"/api/v1/user-groups/{group['id']}/tags",
        json={"tagIds": [foreign["id"]]},
        headers=ADMIN,
    )
    assert_err(response, "FOREIGN_KEY_VIOLATION", 422)


# ---------- read-model parity ----------


@pytest.mark.parametrize(
    ("table", "read", "deliberately_hidden"),
    [
        # A secret's ciphertext is never serialized, and its tenant has never
        # been part of the read view either.
        (Secret, SecretRead, {"entries", "tenant_id"}),
        (Workflow, WorkflowRead, set[str]()),
        (AgentSkill, AgentSkillRead, set[str]()),
        (MCPServer, McpServerRead, set[str]()),
        (MCPToolMock, McpToolMockRead, set[str]()),
        (UserGroup, UserGroupRead, set[str]()),
    ],
)
def test_read_model_mirrors_every_filterable_column(
    table: type[SQLModel], read: type[SQLModel], deliberately_hidden: set[str]
) -> None:
    """Guard the ``readable=`` contract behind the list APIs.

    ``apply_filters`` / ``apply_sort`` only resolve a field present on both the
    table class and the response model, so a column dropped from a ``*Read``
    silently makes that column unfilterable and unsortable. Every column must
    therefore be mirrored — except the ones each read view deliberately hides,
    which are named here so removing one is a conscious edit rather than a
    regression.
    """
    missing = set(table.model_fields) - set(read.model_fields) - deliberately_hidden
    assert missing == set()
    assert "tag_ids" in read.model_fields


# ---------- access control ----------

#: Headers selecting a requester of the default tenant, for the workflow cases.
REQUESTER: dict[str, str] = {"X-User-Id": "carol", "X-User-Roles": "requester"}


async def _gate(
    client: AsyncClient, collection: str, record_id: str, tag_ids: list[str]
) -> None:
    """Attach ``tag_ids`` to a record as the super admin, who is never locked out."""
    response = await client.put(
        f"/api/v1/{collection}/{record_id}/tags", json={"tagIds": tag_ids}
    )
    assert_ok(response)


async def _create_member_group(
    client: AsyncClient, name: str, member_ids: list[str], tag_ids: list[str]
) -> dict[str, Any]:
    """Create a group holding ``member_ids`` and carrying ``tag_ids``."""
    response = await client.post(
        "/api/v1/user-groups",
        json={"name": name, "memberIds": member_ids},
        headers=ADMIN,
    )
    group = assert_ok(response, 201)
    return await _set_user_group_tags(client, group["id"], tag_ids)


async def _listed_ids(
    client: AsyncClient, collection: str, headers: dict[str, str]
) -> set[str]:
    """Return the ids of the records ``headers``' user sees in ``collection``."""
    response = await client.get(f"/api/v1/{collection}", headers=headers)
    return {record["id"] for record in assert_ok(response)}


async def test_access_control_flag_defaults_off_and_round_trips(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    plain = await _create_tag(client, "plain")
    assert plain["accessControl"] is False
    gated = await _create_tag(client, "gated", accessControl=True)
    assert gated["accessControl"] is True
    fetched = assert_ok(await client.get(f"/api/v1/tags/{gated['id']}", headers=NOBODY))
    assert fetched["accessControl"] is True
    updated = assert_ok(
        await client.patch(
            f"/api/v1/tags/{gated['id']}", json={"accessControl": False}, headers=ADMIN
        )
    )
    assert updated["accessControl"] is False


async def test_a_developer_may_not_create_an_access_control_tag(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Only an admin may turn a tag into a gate; a developer's create is 403."""
    client, _ = tag_env
    response = await client.post(
        "/api/v1/tags",
        json={"name": "gated", "accessControl": True},
        headers=DEVELOPER,
    )
    assert_err(response, "FORBIDDEN", 403)


async def test_a_developer_may_not_flip_the_access_control_flag(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    plain = await _create_tag(client, "plain")
    gated = await _create_tag(client, "gated", accessControl=True)
    for tag, flag in ((plain, True), (gated, False)):
        response = await client.patch(
            f"/api/v1/tags/{tag['id']}", json={"accessControl": flag}, headers=DEVELOPER
        )
        assert_err(response, "FORBIDDEN", 403)


async def test_a_developer_may_not_edit_an_access_control_tag_at_all(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Editing a gated tag is admin-only for every field, not just the flag."""
    client, _ = tag_env
    gated = await _create_tag(client, "gated", accessControl=True)
    response = await client.patch(
        f"/api/v1/tags/{gated['id']}",
        json={"name": "renamed", "accessControl": True},
        headers=DEVELOPER,
    )
    assert_err(response, "FORBIDDEN", 403)


async def test_an_admin_may_edit_an_access_control_tags_other_fields(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    gated = await _create_tag(client, "gated", accessControl=True)
    updated = assert_ok(
        await client.patch(
            f"/api/v1/tags/{gated['id']}", json={"name": "renamed"}, headers=ADMIN
        )
    )
    assert updated["name"] == "renamed"
    assert updated["accessControl"] is True


async def test_a_developer_may_not_delete_an_access_control_tag(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    gated = await _create_tag(client, "gated", accessControl=True)
    response = await client.delete(f"/api/v1/tags/{gated['id']}", headers=DEVELOPER)
    assert_err(response, "FORBIDDEN", 403)


async def test_a_developer_may_delete_a_plain_tag(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    plain = await _create_tag(client, "plain")
    assert_ok(await client.delete(f"/api/v1/tags/{plain['id']}", headers=DEVELOPER))


async def test_an_admin_may_delete_an_access_control_tag(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    gated = await _create_tag(client, "gated", accessControl=True)
    assert_ok(await client.delete(f"/api/v1/tags/{gated['id']}", headers=ADMIN))


async def test_access_controlled_secret_is_hidden_from_a_non_member(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Every caller-facing route reads as 404, so existence is never confirmed."""
    client, _ = tag_env
    gated = await _create_tag(client, "gated", accessControl=True)
    secret_id = (await _create_secret(client))["id"]
    await _gate(client, "secrets", secret_id, [gated["id"]])

    assert secret_id not in await _listed_ids(client, "secrets", DEVELOPER)
    base = f"/api/v1/secrets/{secret_id}"
    assert_err(await client.get(base, headers=DEVELOPER), "NOT_FOUND", 404)
    assert_err(await client.get(f"{base}/keys", headers=DEVELOPER), "NOT_FOUND", 404)
    assert_err(
        await client.patch(base, json={"name": "renamed"}, headers=DEVELOPER),
        "NOT_FOUND",
        404,
    )
    assert_err(
        await client.put(f"{base}/tags", json={"tagIds": []}, headers=DEVELOPER),
        "NOT_FOUND",
        404,
    )
    assert_err(await client.delete(base, headers=DEVELOPER), "NOT_FOUND", 404)
    # Nothing above was applied.
    assert assert_ok(await client.get(base))["name"] == "creds"


async def test_member_whose_groups_cover_every_access_tag_sees_the_record(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Conjunctive over the record's tags; the caller's groups are taken together."""
    client, _ = tag_env
    finance = await _create_tag(client, "finance", accessControl=True)
    audit = await _create_tag(client, "audit", accessControl=True)
    secret_id = (await _create_secret(client))["id"]
    await _gate(client, "secrets", secret_id, [finance["id"], audit["id"]])
    base = f"/api/v1/secrets/{secret_id}"

    # One of the two tags is not enough.
    await _create_member_group(client, "finance-team", ["bob"], [finance["id"]])
    assert secret_id not in await _listed_ids(client, "secrets", DEVELOPER)
    assert_err(await client.get(base, headers=DEVELOPER), "NOT_FOUND", 404)

    # A second group supplying the other tag completes the set.
    await _create_member_group(client, "auditors", ["bob"], [audit["id"]])
    assert secret_id in await _listed_ids(client, "secrets", DEVELOPER)
    assert assert_ok(await client.get(base, headers=DEVELOPER))["id"] == secret_id


async def test_plain_tags_never_restrict_and_admin_and_super_admin_bypass(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    plain = await _create_tag(client, "plain")
    gated = await _create_tag(client, "gated", accessControl=True)
    open_id = (await _create_secret(client, "open"))["id"]
    gated_id = (await _create_secret(client, "gated"))["id"]
    await _gate(client, "secrets", open_id, [plain["id"]])
    await _gate(client, "secrets", gated_id, [plain["id"], gated["id"]])

    # A plain tag on its own hides nothing, even from a role-less user.
    assert open_id in await _listed_ids(client, "secrets", NOBODY)
    assert gated_id not in await _listed_ids(client, "secrets", NOBODY)
    # The super admin (the client's default identity) is never a group member
    # and is exempt instead.
    assert {open_id, gated_id} <= await _listed_ids(client, "secrets", {})
    assert_ok(await client.get(f"/api/v1/secrets/{gated_id}"))
    # An admin is exempt too, despite holding no group membership either.
    assert {open_id, gated_id} <= await _listed_ids(client, "secrets", ADMIN)
    assert_ok(await client.get(f"/api/v1/secrets/{gated_id}", headers=ADMIN))


async def test_attaching_an_unheld_access_tag_is_forbidden(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A caller cannot hide a record from themselves; membership unlocks the tag."""
    client, _ = tag_env
    plain = await _create_tag(client, "plain")
    gated = await _create_tag(client, "gated", accessControl=True)
    secret_id = (await _create_secret(client))["id"]
    tags_url = f"/api/v1/secrets/{secret_id}/tags"

    response = await client.put(
        tags_url, json={"tagIds": [plain["id"], gated["id"]]}, headers=DEVELOPER
    )
    assert_err(response, "FORBIDDEN", 403)
    # Refused as a whole: the plain tag was not attached either.
    secret = assert_ok(
        await client.get(f"/api/v1/secrets/{secret_id}", headers=DEVELOPER)
    )
    assert secret["tagIds"] == []

    await _create_member_group(client, "holders", ["bob"], [gated["id"]])
    updated = assert_ok(
        await client.put(
            tags_url, json={"tagIds": [plain["id"], gated["id"]]}, headers=DEVELOPER
        )
    )
    assert set(updated["tagIds"]) == {plain["id"], gated["id"]}


async def test_a_group_may_carry_an_access_tag_its_editor_does_not_hold(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Tagging a group is how an admin grants access, so it is never locked out."""
    client, _ = tag_env
    gated = await _create_tag(client, "gated", accessControl=True)
    group = await _create_user_group(client)
    # ``ADMIN`` is alice, who is not a member of the group and holds no tags.
    updated = await _set_user_group_tags(client, group["id"], [gated["id"]])
    assert updated["tagIds"] == [gated["id"]]


@pytest.mark.parametrize(
    ("collection", "body"),
    [
        ("mcp-servers", {"name": "srv", "url": "https://mcp.example.com/mcp"}),
        ("agent-skills", {"name": "skill", "repoUrl": "https://github.com/x/y"}),
        (
            "mcp-tool-mocks",
            {
                "name": "mock",
                "toolName": "request_approval",
                "responses": [{"kind": "text", "value": "ok"}],
            },
        ),
    ],
)
async def test_access_control_gates_every_taggable_collection(
    workflow_client: AsyncClient, collection: str, body: dict[str, Any]
) -> None:
    """The same predicate guards each taggable repository, not just secrets."""
    client = workflow_client
    gated = await _create_tag(client, "gated", accessControl=True)
    created = assert_ok(await client.post(f"/api/v1/{collection}", json=body), 201)
    record_id = created["id"]
    await _gate(client, collection, record_id, [gated["id"]])

    assert record_id not in await _listed_ids(client, collection, DEVELOPER)
    assert_err(
        await client.get(f"/api/v1/{collection}/{record_id}", headers=DEVELOPER),
        "NOT_FOUND",
        404,
    )

    await _create_member_group(client, "holders", ["bob"], [gated["id"]])
    assert record_id in await _listed_ids(client, collection, DEVELOPER)
    assert_ok(await client.get(f"/api/v1/{collection}/{record_id}", headers=DEVELOPER))


async def test_a_hidden_workflow_cannot_be_listed_read_or_executed(
    workflow_client: AsyncClient,
) -> None:
    client = workflow_client
    gated = await _create_tag(client, "gated", accessControl=True)
    skill = await create_skill(client)
    workflow_id = (await create_published_workflow(client, skill["id"]))["id"]
    await _gate(client, "workflows", workflow_id, [gated["id"]])
    execute_url = f"/api/v1/workflows/{workflow_id}/execute"

    assert workflow_id not in await _listed_ids(client, "workflows", REQUESTER)
    assert_err(
        await client.get(f"/api/v1/workflows/{workflow_id}", headers=REQUESTER),
        "NOT_FOUND",
        404,
    )
    assert_err(await client.post(execute_url, headers=REQUESTER), "NOT_FOUND", 404)

    await _create_member_group(client, "holders", ["carol"], [gated["id"]])
    assert_ok(await client.post(execute_url, headers=REQUESTER), 201)


async def test_executing_a_visible_workflow_resolves_its_hidden_skill(
    workflow_client: AsyncClient,
) -> None:
    """Access control is a management-API rule: a run still uses the skill it came from."""
    client = workflow_client
    gated = await _create_tag(client, "gated", accessControl=True)
    skill = await create_skill(client)
    # Generate first: a new workflow copies its skill's tags, and this one must
    # stay open.
    workflow_id = (await create_published_workflow(client, skill["id"]))["id"]
    await _gate(client, "agent-skills", skill["id"], [gated["id"]])

    assert_err(
        await client.get(f"/api/v1/agent-skills/{skill['id']}", headers=REQUESTER),
        "NOT_FOUND",
        404,
    )
    assert_ok(
        await client.post(
            f"/api/v1/workflows/{workflow_id}/execute", headers=REQUESTER
        ),
        201,
    )


async def _insert_approval(
    eng: AsyncEngine, *, workflow_execution_id: str, approver: str = "carol"
) -> str:
    """Insert an Approval addressed to ``approver`` and return its id."""
    async with AsyncSession(eng) as db:
        approval = Approval(
            workflow_execution_id=workflow_execution_id,
            title="Approve me",
            approver=approver,
            tenant_id=DEFAULT_TEST_TENANT_ID,
            created_by="owner",
            updated_by="owner",
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        return approval.id


async def test_a_workflow_executions_copied_access_tag_hides_it_from_a_former_group_member(
    workflow_client: AsyncClient,
) -> None:
    """A run copies its workflow's tags at execute time, access-control ones

    included, so losing the group that holds one hides the run too -- even from
    the person who started it, and not just on the browsing pages: its tasks,
    its chat history, and driving its agent all 404 alike.
    """
    client = workflow_client
    gated = await _create_tag(client, "gated", accessControl=True)
    skill = await create_skill(client)
    workflow_id = (await create_published_workflow(client, skill["id"]))["id"]
    await _gate(client, "workflows", workflow_id, [gated["id"]])
    group = await _create_member_group(client, "holders", ["carol"], [gated["id"]])

    execution = await execute_workflow(client, workflow_id, headers=REQUESTER)
    execution_id = execution["id"]
    assert execution["tagIds"] == [gated["id"]]
    detail_url = f"/api/v1/workflow-executions/{execution_id}"
    tasks_url = f"{detail_url}/workflow-tasks"
    messages_url = f"{detail_url}/messages"
    agent_url = f"{detail_url}/agent"
    run_input = {
        "threadId": execution["sessionId"],
        "runId": "run-001",
        "state": {},
        "messages": [],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }

    # carol (REQUESTER) is the run's own initiator and still holds the tag.
    assert execution_id in await _listed_ids(client, "workflow-executions", REQUESTER)
    assert_ok(await client.get(detail_url, headers=REQUESTER))
    assert_ok(await client.get(tasks_url, headers=REQUESTER))
    agent_response = await client.post(agent_url, json=run_input, headers=REQUESTER)
    assert agent_response.status_code == 200

    # She leaves the only group holding the tag.
    assert_ok(
        await client.patch(
            f"/api/v1/user-groups/{group['id']}", json={"memberIds": []}, headers=ADMIN
        )
    )
    assert execution_id not in await _listed_ids(
        client, "workflow-executions", REQUESTER
    )
    assert_err(await client.get(detail_url, headers=REQUESTER), "NOT_FOUND", 404)
    assert_err(await client.get(tasks_url, headers=REQUESTER), "NOT_FOUND", 404)
    assert_err(await client.get(messages_url, headers=REQUESTER), "NOT_FOUND", 404)
    assert_err(
        await client.post(agent_url, json=run_input, headers=REQUESTER),
        "NOT_FOUND",
        404,
    )

    # An admin and the super admin (the client's default identity) still see it.
    assert_ok(await client.get(detail_url, headers=ADMIN))
    assert_ok(await client.get(detail_url))


async def test_an_approvals_execution_access_tag_hides_it_from_its_approver(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """An approval carries no tags of its own; it inherits its execution's gate.

    Losing the group that holds the tag hides the approval too, even from its
    own designated approver -- who can then no longer decide it either.
    """
    client, engine = workflow_client_with_engine
    gated = await _create_tag(client, "gated", accessControl=True)
    skill = await create_skill(client)
    workflow_id = (await create_published_workflow(client, skill["id"]))["id"]
    await _gate(client, "workflows", workflow_id, [gated["id"]])
    group = await _create_member_group(client, "holders", ["carol"], [gated["id"]])

    execution = await execute_workflow(client, workflow_id, headers=REQUESTER)
    approval_id = await _insert_approval(
        engine, workflow_execution_id=execution["id"], approver="carol"
    )
    detail_url = f"/api/v1/approvals/{approval_id}"

    assert approval_id in await _listed_ids(client, "approvals", REQUESTER)
    assert_ok(await client.get(detail_url, headers=REQUESTER))

    assert_ok(
        await client.patch(
            f"/api/v1/user-groups/{group['id']}", json={"memberIds": []}, headers=ADMIN
        )
    )
    assert approval_id not in await _listed_ids(client, "approvals", REQUESTER)
    assert_err(await client.get(detail_url, headers=REQUESTER), "NOT_FOUND", 404)
    # The tag gate fires before the designated-approver check would let her in.
    assert_err(
        await client.patch(detail_url, json={"status": "approved"}, headers=REQUESTER),
        "NOT_FOUND",
        404,
    )
    assert_ok(await client.get(detail_url, headers=ADMIN))


# ---------- users ----------


async def test_user_read_reports_group_inherited_tag_ids(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A user's ``groupTagIds`` is the union of its groups' tags, access-control
    tags included -- that filter gates *other* resources, not a user's own
    projection of its own group tags."""
    client, _ = tag_env
    plain = await _create_tag(client, "plain")
    gated = await _create_tag(client, "gated", accessControl=True)
    await _create_member_group(client, "devs", ["bob"], [plain["id"], gated["id"]])

    user = assert_ok(await client.get("/api/v1/users/bob", headers=ADMIN))
    assert sorted(user["groupTagIds"]) == sorted([plain["id"], gated["id"]])

    users = assert_ok(await client.get("/api/v1/users", headers=ADMIN))
    by_id = {u["id"]: u for u in users}
    assert sorted(by_id["bob"]["groupTagIds"]) == sorted([plain["id"], gated["id"]])
    assert by_id["carol"]["groupTagIds"] == []
