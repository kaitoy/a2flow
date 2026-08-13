"""Tests for the ``/tags`` endpoints and for attaching tags to records.

Covers the tag CRUD surface, its tenant boundary, the ``PUT /{resource}/{id}/tags``
sub-resource on all four taggable resources, the conjunctive ``?tag=`` list
filter, and the two invariants the whole feature rests on: renaming a tag keeps
every attachment, and deleting one detaches it everywhere rather than being
blocked by the records carrying it.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.bootstrap import seed_system_user
from models.agent_skill import AgentSkill, AgentSkillRead
from models.mcp_server import MCPServer, McpServerRead
from models.secret import Secret, SecretRead
from models.tag import MAX_RECORD_TAGS
from models.user import SYSTEM_USER_ID
from models.workflow import Workflow, WorkflowRead
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_tenant, seed_users
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
    """Yield an API client plus the in-memory engine backing it."""
    from infrastructure.database import get_session
    from main import app

    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # CASCADE on the join tables is a database-level guarantee, and SQLite only
    # honours it with foreign keys switched on. Without this the delete tests
    # would pass for the wrong reason.
    @sa_event.listens_for(mem_engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
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


# ---------- CRUD ----------


async def test_create_returns_the_tag_with_its_defaults(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    tag = await _create_tag(client)
    assert tag["name"] == "production"
    assert tag["color"] == "slate"
    assert tag["tenantId"] == DEFAULT_TEST_TENANT_ID


async def test_create_accepts_a_palette_slot(
    tag_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = tag_env
    tag = await _create_tag(client, color="violet")
    assert tag["color"] == "violet"


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
    # A developer may mint tags but may not write a secret, which is admin's.
    response = await client.put(
        f"/api/v1/secrets/{secret['id']}/tags", json={"tagIds": []}, headers=DEVELOPER
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
