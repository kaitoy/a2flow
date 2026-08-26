"""Tests for tenant resolution (``get_current_tenant_id``) and its end-to-end effect.

``get_current_tenant_id`` is a plain function once FastAPI's ``Depends()``
wiring is stripped away, so its platform-scoped-caller behavior is tested
directly. The actual enforcement -- cross-tenant access reading as 404 rather
than 403, and a platform-scoped caller being rejected outright -- is tested
end-to-end through the API, since that is what a client actually observes.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.requests import Request

from dependencies.auth import (
    ALL_TENANTS_SENTINEL,
    TENANT_HEADER_NAME,
    get_current_tenant_id,
    get_current_tenant_scope,
)
from models.user import SYSTEM_USER_ID, User
from repositories.exceptions import ForbiddenError
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID
from tests._workflow import create_published_workflow


def _user(tenant_id: str | None) -> User:
    return User(
        id="u1",
        username="u1",
        first_name="Test",
        last_name="User",
        password="pw",
        email="u1@test.local",
        roles=[],
        tenant_id=tenant_id,
        created_by=SYSTEM_USER_ID,
        updated_by=SYSTEM_USER_ID,
    )


def _request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request(scope={"type": "http", "headers": raw_headers})


def test_get_current_tenant_id_returns_the_users_tenant() -> None:
    assert get_current_tenant_id(_user("tenant-x"), _request()) == "tenant-x"


def test_get_current_tenant_id_rejects_platform_scoped_caller() -> None:
    """``tenant_id is None`` means platform-scoped (system user, or a super_admin
    with no tenant selected) -- tenant-scoped routes stay closed to it without a
    ``X-Tenant-Id`` header.
    """
    with pytest.raises(ForbiddenError):
        get_current_tenant_id(_user(None), _request())


def test_get_current_tenant_id_resolves_super_admin_tenant_from_header() -> None:
    """A platform-scoped caller selects a tenant via ``X-Tenant-Id``."""
    request = _request({TENANT_HEADER_NAME: "tenant-x"})
    assert get_current_tenant_id(_user(None), request) == "tenant-x"


def test_get_current_tenant_id_rejects_super_admin_with_blank_header() -> None:
    """A present-but-blank ``X-Tenant-Id`` is treated the same as a missing one."""
    request = _request({TENANT_HEADER_NAME: "  "})
    with pytest.raises(ForbiddenError):
        get_current_tenant_id(_user(None), request)


def test_get_current_tenant_id_ignores_header_for_tenant_scoped_caller() -> None:
    """A tenant-scoped caller can never escalate into another tenant via the header."""
    request = _request({TENANT_HEADER_NAME: "tenant-y"})
    assert get_current_tenant_id(_user("tenant-x"), request) == "tenant-x"


def test_get_current_tenant_id_rejects_all_tenants_sentinel() -> None:
    """The strict resolver (write routes) never allows "all tenants"."""
    request = _request({TENANT_HEADER_NAME: ALL_TENANTS_SENTINEL})
    with pytest.raises(ForbiddenError):
        get_current_tenant_id(_user(None), request)


def test_get_current_tenant_id_ignores_sentinel_for_tenant_scoped_caller() -> None:
    """A tenant-scoped caller sending the sentinel still just gets their own tenant."""
    request = _request({TENANT_HEADER_NAME: ALL_TENANTS_SENTINEL})
    assert get_current_tenant_id(_user("tenant-x"), request) == "tenant-x"


def test_get_current_tenant_scope_returns_the_users_tenant() -> None:
    assert get_current_tenant_scope(_user("tenant-x"), _request()) == "tenant-x"


def test_get_current_tenant_scope_rejects_platform_scoped_caller_with_blank_header() -> (
    None
):
    """ "No tenant selected yet" still 403s on the permissive resolver too."""
    with pytest.raises(ForbiddenError):
        get_current_tenant_scope(_user(None), _request())


def test_get_current_tenant_scope_resolves_super_admin_tenant_from_header() -> None:
    request = _request({TENANT_HEADER_NAME: "tenant-x"})
    assert get_current_tenant_scope(_user(None), request) == "tenant-x"


def test_get_current_tenant_scope_returns_none_for_all_tenants_sentinel() -> None:
    """The sentinel means "every tenant", signaled as ``None``."""
    request = _request({TENANT_HEADER_NAME: ALL_TENANTS_SENTINEL})
    assert get_current_tenant_scope(_user(None), request) is None


def test_get_current_tenant_scope_ignores_sentinel_for_tenant_scoped_caller() -> None:
    """A tenant-scoped caller can never trigger all-tenants mode."""
    request = _request({TENANT_HEADER_NAME: ALL_TENANTS_SENTINEL})
    assert get_current_tenant_scope(_user("tenant-x"), request) == "tenant-x"


async def test_cross_tenant_workflow_access_is_404(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A caller in a different tenant gets 404, not 403, fetching another tenant's workflow.

    404 (not 403) matches the existing cross-user convention for notifications:
    the tenant boundary should not even reveal that the resource exists.
    """
    client, _eng = workflow_client_with_engine
    skill = assert_ok(
        await client.post(
            "/api/v1/agent-skills",
            json={"name": "tenant-skill", "repo_url": "https://github.com/x/y"},
        ),
        status=201,
    )
    workflow = await create_published_workflow(
        client, skill["id"], name="tenant-wf", prompt="do it"
    )

    res = await client.get(
        f"/api/v1/workflows/{workflow['id']}",
        headers={"X-User-Tenant-Id": "tenant-cross"},
    )
    assert_err(res, "NOT_FOUND", 404)

    # The same-tenant caller (no override -- the default test tenant) still can.
    assert_ok(await client.get(f"/api/v1/workflows/{workflow['id']}"))


async def test_platform_scoped_caller_is_forbidden_on_tenant_scoped_route(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """An explicit empty ``X-User-Tenant-Id`` opts into a platform-scoped caller."""
    client, _eng = workflow_client_with_engine
    res = await client.get("/api/v1/workflows", headers={"X-User-Tenant-Id": ""})
    assert_err(res, "FORBIDDEN", 403)


async def test_platform_scoped_caller_with_tenant_header_can_list_and_create(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A ``X-Tenant-Id`` header lets a platform-scoped caller act as that tenant.

    Covers both the read path (``list``) and the write path (``create``, which
    stamps the header's tenant onto the new row). Uses MCPServer -- a plain
    synchronous CRUD with no background job -- rather than AgentSkill, whose
    registration kicks off a background sync job that the test fixture's mock
    (``tests/conftest.py``'s ``fake_sync``) hardcodes to ``DEFAULT_TEST_TENANT_ID``.
    """
    client, _eng = workflow_client_with_engine
    headers = {"X-User-Tenant-Id": "", TENANT_HEADER_NAME: DEFAULT_TEST_TENANT_ID}

    server = assert_ok(
        await client.post(
            "/api/v1/mcp-servers",
            json={"name": "super-admin-server", "url": "https://mcp.example.com"},
            headers=headers,
        ),
        status=201,
    )
    assert server["tenantId"] == DEFAULT_TEST_TENANT_ID

    listed = assert_ok(await client.get("/api/v1/mcp-servers", headers=headers))
    assert any(s["id"] == server["id"] for s in listed)


async def test_super_admin_switching_tenant_header_switches_visible_data(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Switching ``X-Tenant-Id`` acts as a different tenant, seeing only its rows."""
    client, _eng = workflow_client_with_engine
    tenant_b = assert_ok(
        await client.post(
            "/api/v1/tenants",
            json={"displayName": "Tenant Switch B", "name": "tenant-switch-b"},
        ),
        status=201,
    )["id"]

    def _headers(tenant_id: str) -> dict[str, str]:
        return {"X-User-Tenant-Id": "", TENANT_HEADER_NAME: tenant_id}

    server_a = assert_ok(
        await client.post(
            "/api/v1/mcp-servers",
            json={"name": "server-in-a", "url": "https://mcp.example.com/a"},
            headers=_headers(DEFAULT_TEST_TENANT_ID),
        ),
        status=201,
    )
    server_b = assert_ok(
        await client.post(
            "/api/v1/mcp-servers",
            json={"name": "server-in-b", "url": "https://mcp.example.com/b"},
            headers=_headers(tenant_b),
        ),
        status=201,
    )
    assert server_b["tenantId"] == tenant_b

    listed_a = assert_ok(
        await client.get(
            "/api/v1/mcp-servers", headers=_headers(DEFAULT_TEST_TENANT_ID)
        )
    )
    ids_a = {s["id"] for s in listed_a}
    assert server_a["id"] in ids_a
    assert server_b["id"] not in ids_a

    listed_b = assert_ok(
        await client.get("/api/v1/mcp-servers", headers=_headers(tenant_b))
    )
    ids_b = {s["id"] for s in listed_b}
    assert server_b["id"] in ids_b
    assert server_a["id"] not in ids_b


async def test_tenant_scoped_caller_cannot_escalate_via_tenant_header(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A tenant-scoped caller's own tenant always wins; the header is ignored."""
    client, _eng = workflow_client_with_engine
    other_tenant = assert_ok(
        await client.post(
            "/api/v1/tenants",
            json={"displayName": "Tenant Escalation", "name": "tenant-escalation"},
        ),
        status=201,
    )["id"]

    server = assert_ok(
        await client.post(
            "/api/v1/mcp-servers",
            json={"name": "own-tenant-server", "url": "https://mcp.example.com"},
            headers={TENANT_HEADER_NAME: other_tenant},
        ),
        status=201,
    )
    assert server["tenantId"] == DEFAULT_TEST_TENANT_ID


def _all_tenants_headers() -> dict[str, str]:
    return {"X-User-Tenant-Id": "", TENANT_HEADER_NAME: ALL_TENANTS_SENTINEL}


async def test_super_admin_all_tenants_lists_across_every_tenant(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Selecting "all tenants" lists rows from every tenant, not just one."""
    client, _eng = workflow_client_with_engine
    tenant_b = assert_ok(
        await client.post(
            "/api/v1/tenants",
            json={"displayName": "Tenant All A", "name": "tenant-all-a"},
        ),
        status=201,
    )["id"]

    server_a = assert_ok(
        await client.post(
            "/api/v1/mcp-servers",
            json={"name": "all-tenants-a", "url": "https://mcp.example.com/a"},
            headers={
                "X-User-Tenant-Id": "",
                TENANT_HEADER_NAME: DEFAULT_TEST_TENANT_ID,
            },
        ),
        status=201,
    )
    server_b = assert_ok(
        await client.post(
            "/api/v1/mcp-servers",
            json={"name": "all-tenants-b", "url": "https://mcp.example.com/b"},
            headers={"X-User-Tenant-Id": "", TENANT_HEADER_NAME: tenant_b},
        ),
        status=201,
    )

    listed = assert_ok(
        await client.get("/api/v1/mcp-servers", headers=_all_tenants_headers())
    )
    ids = {s["id"] for s in listed}
    assert server_a["id"] in ids
    assert server_b["id"] in ids


async def test_super_admin_all_tenants_get_reaches_any_tenants_record(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Fetching a single record by id works across tenants in "all tenants" mode."""
    client, _eng = workflow_client_with_engine
    tenant_b = assert_ok(
        await client.post(
            "/api/v1/tenants",
            json={"displayName": "Tenant All B", "name": "tenant-all-b"},
        ),
        status=201,
    )["id"]
    server = assert_ok(
        await client.post(
            "/api/v1/mcp-servers",
            json={"name": "cross-tenant-get", "url": "https://mcp.example.com"},
            headers={"X-User-Tenant-Id": "", TENANT_HEADER_NAME: tenant_b},
        ),
        status=201,
    )

    got = assert_ok(
        await client.get(
            f"/api/v1/mcp-servers/{server['id']}", headers=_all_tenants_headers()
        )
    )
    assert got["id"] == server["id"]


async def test_super_admin_all_tenants_rejects_create(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """A write route stays on the strict resolver, so "all tenants" 403s it."""
    client, _eng = workflow_client_with_engine
    res = await client.post(
        "/api/v1/mcp-servers",
        json={"name": "should-not-exist", "url": "https://mcp.example.com"},
        headers=_all_tenants_headers(),
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_super_admin_all_tenants_rejects_update_and_delete(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Update/delete stay unreachable in "all tenants" mode, same as create."""
    client, _eng = workflow_client_with_engine
    server = assert_ok(
        await client.post(
            "/api/v1/mcp-servers",
            json={"name": "update-delete-target", "url": "https://mcp.example.com"},
            headers={
                "X-User-Tenant-Id": "",
                TENANT_HEADER_NAME: DEFAULT_TEST_TENANT_ID,
            },
        ),
        status=201,
    )

    update_res = await client.patch(
        f"/api/v1/mcp-servers/{server['id']}",
        json={"name": "renamed"},
        headers=_all_tenants_headers(),
    )
    assert_err(update_res, "FORBIDDEN", 403)

    delete_res = await client.delete(
        f"/api/v1/mcp-servers/{server['id']}", headers=_all_tenants_headers()
    )
    assert_err(delete_res, "FORBIDDEN", 403)


async def test_super_admin_all_tenants_resolves_workflows_deep_collaborator_graph(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """ "All tenants" also works through Workflow's much deeper collaborator graph.

    ``WorkflowService`` composes many tenant-scoped collaborators (AgentSkill,
    WorkflowExecution, WorkflowTaskTemplate, WorkflowTask,
    WorkflowPublishedVersion, MessageMeta repositories), most of which
    ``list``/``get`` never touch -- this exercises that the whole read-side DI
    graph actually resolves at runtime, not just under mypy. (A genuine
    cross-tenant fixture here would need an AgentSkill registered outside
    ``DEFAULT_TEST_TENANT_ID``, which the test suite's mocked background sync
    job does not support -- see ``test_platform_scoped_caller_with_tenant_header_can_list_and_create``
    above; cross-tenant visibility itself is already covered there via MCPServer.)
    """
    client, _eng = workflow_client_with_engine
    skill = assert_ok(
        await client.post(
            "/api/v1/agent-skills",
            json={"name": "skill-a-wf", "repo_url": "https://github.com/x/y"},
        ),
        status=201,
    )
    workflow = await create_published_workflow(client, skill["id"])

    listed = assert_ok(
        await client.get("/api/v1/workflows", headers=_all_tenants_headers())
    )
    assert workflow["id"] in {w["id"] for w in listed}

    got = assert_ok(
        await client.get(
            f"/api/v1/workflows/{workflow['id']}", headers=_all_tenants_headers()
        )
    )
    assert got["id"] == workflow["id"]

    templates = assert_ok(
        await client.get(
            f"/api/v1/workflows/{workflow['id']}/task-templates",
            headers=_all_tenants_headers(),
        )
    )
    assert len(templates) == 1


async def test_super_admin_all_tenants_resolves_workflow_task_access_policy_graph(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """ "All tenants" also works through ``get_workflow_task``'s access-policy graph.

    ``WorkflowExecutionAccessPolicy`` (and, through it, ``ApproverGroupResolver``
    and ``NotificationDispatcher``) are collaborators of ``WorkflowTaskService``
    that ``get`` never calls -- this proves that whole chain, several layers
    deeper than a plain repository, still resolves at runtime under
    ``tenant_id=None``.
    """
    client, _eng = workflow_client_with_engine
    skill = assert_ok(
        await client.post(
            "/api/v1/agent-skills",
            json={"name": "skill-task-graph", "repo_url": "https://github.com/x/y"},
        ),
        status=201,
    )
    workflow = await create_published_workflow(client, skill["id"])
    execution = assert_ok(
        await client.post(f"/api/v1/workflows/{workflow['id']}/execute"), status=201
    )
    seeded = assert_ok(
        await client.get(
            f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks"
        )
    )

    got = assert_ok(
        await client.get(
            f"/api/v1/workflow-tasks/{seeded[0]['id']}",
            headers=_all_tenants_headers(),
        )
    )
    assert got["id"] == seeded[0]["id"]
