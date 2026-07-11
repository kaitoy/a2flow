"""Role-gating tests for the write/execute endpoints.

The auth test stub (see ``conftest._override_get_current_user``) reads roles
from the ``X-User-Roles`` header and defaults to ``super_admin``; these tests
set the header explicitly to exercise the ``require_roles`` route dependency:
the granting role passes, any other role set gets 403 ``FORBIDDEN``, and
``super_admin`` always passes. Reads stay open to authenticated users with no
roles at all.
"""

from typing import Any

from httpx import AsyncClient

from tests._envelope import assert_err, assert_ok

_SKILL_BODY = {"name": "authz-skill", "repo_url": "https://github.com/x/y"}
_SECRET_BODY = {"name": "authz-secret", "type": "local", "value": "s3cr3t"}
_MCP_BODY = {"name": "authz-mcp", "url": "https://mcp.example.com/mcp"}
_USER_BODY = {
    "username": "authzuser",
    "firstName": "Authz",
    "lastName": "User",
    "password": "secret123abc",
    "email": "authz@example.com",
}


def _roles(roles: str) -> dict[str, str]:
    """Build headers selecting the given comma-separated roles for the request."""
    return {"X-User-Roles": roles}


async def _create_workflow(client: AsyncClient) -> Any:
    """Create a skill and a workflow (as super admin) and return the workflow."""
    skill = assert_ok(
        await client.post("/api/v1/agent-skills", json=_SKILL_BODY), status=201
    )
    body = {"name": "authz-wf", "prompt": "do it", "agent_skill_id": skill["id"]}
    return assert_ok(await client.post("/api/v1/workflows", json=body), status=201)


# ---------- users: admin ----------


async def test_create_user_requires_admin_role(workflow_client: AsyncClient) -> None:
    res = await workflow_client.post(
        "/api/v1/users", json=_USER_BODY, headers=_roles("developer,requester")
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_create_user_allowed_for_admin(workflow_client: AsyncClient) -> None:
    res = await workflow_client.post(
        "/api/v1/users", json=_USER_BODY, headers=_roles("admin")
    )
    assert_ok(res, status=201)


async def test_delete_user_requires_admin_role(workflow_client: AsyncClient) -> None:
    created = assert_ok(
        await workflow_client.post(
            "/api/v1/users", json=_USER_BODY, headers=_roles("admin")
        ),
        status=201,
    )
    res = await workflow_client.delete(
        f"/api/v1/users/{created['id']}", headers=_roles("developer")
    )
    assert_err(res, "FORBIDDEN", 403)


# ---------- secrets: admin ----------


async def test_create_secret_requires_admin_role(workflow_client: AsyncClient) -> None:
    res = await workflow_client.post(
        "/api/v1/secrets", json=_SECRET_BODY, headers=_roles("developer")
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_create_secret_allowed_for_admin(workflow_client: AsyncClient) -> None:
    res = await workflow_client.post(
        "/api/v1/secrets", json=_SECRET_BODY, headers=_roles("admin")
    )
    assert_ok(res, status=201)


async def test_update_secret_requires_admin_role(workflow_client: AsyncClient) -> None:
    created = assert_ok(
        await workflow_client.post(
            "/api/v1/secrets", json=_SECRET_BODY, headers=_roles("admin")
        ),
        status=201,
    )
    res = await workflow_client.patch(
        f"/api/v1/secrets/{created['id']}",
        json={"value": "new"},
        headers=_roles("requester"),
    )
    assert_err(res, "FORBIDDEN", 403)


# ---------- mcp-servers / agent-skills / workflows: developer ----------


async def test_create_mcp_server_requires_developer_role(
    workflow_client: AsyncClient,
) -> None:
    res = await workflow_client.post(
        "/api/v1/mcp-servers", json=_MCP_BODY, headers=_roles("admin")
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_create_mcp_server_allowed_for_developer(
    workflow_client: AsyncClient,
) -> None:
    res = await workflow_client.post(
        "/api/v1/mcp-servers", json=_MCP_BODY, headers=_roles("developer")
    )
    assert_ok(res, status=201)


async def test_create_agent_skill_requires_developer_role(
    workflow_client: AsyncClient,
) -> None:
    res = await workflow_client.post(
        "/api/v1/agent-skills", json=_SKILL_BODY, headers=_roles("requester")
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_create_agent_skill_allowed_for_developer(
    workflow_client: AsyncClient,
) -> None:
    res = await workflow_client.post(
        "/api/v1/agent-skills", json=_SKILL_BODY, headers=_roles("developer")
    )
    assert_ok(res, status=201)


async def test_create_workflow_requires_developer_role(
    workflow_client: AsyncClient,
) -> None:
    skill = assert_ok(
        await workflow_client.post("/api/v1/agent-skills", json=_SKILL_BODY),
        status=201,
    )
    body = {"name": "authz-wf", "prompt": "do it", "agent_skill_id": skill["id"]}
    res = await workflow_client.post(
        "/api/v1/workflows", json=body, headers=_roles("requester")
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_delete_workflow_requires_developer_role(
    workflow_client: AsyncClient,
) -> None:
    wf = await _create_workflow(workflow_client)
    res = await workflow_client.delete(
        f"/api/v1/workflows/{wf['id']}", headers=_roles("admin,requester,approver")
    )
    assert_err(res, "FORBIDDEN", 403)


# ---------- workflow execution: requester ----------


async def test_execute_workflow_requires_requester_role(
    workflow_client: AsyncClient,
) -> None:
    wf = await _create_workflow(workflow_client)
    res = await workflow_client.post(
        f"/api/v1/workflows/{wf['id']}/execute", headers=_roles("developer")
    )
    assert_err(res, "FORBIDDEN", 403)


async def test_execute_workflow_allowed_for_requester(
    workflow_client: AsyncClient,
) -> None:
    wf = await _create_workflow(workflow_client)
    res = await workflow_client.post(
        f"/api/v1/workflows/{wf['id']}/execute", headers=_roles("requester")
    )
    assert_ok(res, status=201)


async def test_execute_workflow_allowed_for_super_admin(
    workflow_client: AsyncClient,
) -> None:
    wf = await _create_workflow(workflow_client)
    res = await workflow_client.post(
        f"/api/v1/workflows/{wf['id']}/execute", headers=_roles("super_admin")
    )
    assert_ok(res, status=201)


# ---------- reads stay open for role-less users ----------


async def test_reads_are_open_to_users_without_roles(
    workflow_client: AsyncClient,
) -> None:
    for path in (
        "/api/v1/users",
        "/api/v1/secrets",
        "/api/v1/mcp-servers",
        "/api/v1/agent-skills",
        "/api/v1/workflows",
        "/api/v1/workflow-sessions",
        "/api/v1/approvals",
    ):
        res = await workflow_client.get(path, headers=_roles(""))
        assert res.status_code == 200, path
