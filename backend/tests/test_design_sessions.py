"""Integration tests for the DesignSession endpoints."""

from typing import Any
from unittest.mock import MagicMock

from httpx import AsyncClient

from infrastructure.agent import AgentKind
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID
from tests._workflow import create_skill, generate_workflow
from tests.conftest import FAKE_COMMIT_SHA


async def _design_session(client: AsyncClient) -> tuple[Any, Any, Any]:
    """Generate a workflow and return (skill, workflow, design_session)."""
    skill = await create_skill(client)
    wf = await generate_workflow(client, skill["id"])
    ds = assert_ok(await client.get(f"/api/v1/workflows/{wf['id']}/design-session"))
    return skill, wf, ds


def _make_run_agent_input() -> dict[str, Any]:
    return {
        "threadId": "thread-001",
        "runId": "run-001",
        "state": {},
        "messages": [],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }


# ---------- GET /workflows/{id}/design-session ----------


async def test_workflow_design_session_lookup(workflow_client: AsyncClient) -> None:
    skill, wf, ds = await _design_session(workflow_client)
    assert ds["workflowId"] == wf["id"]
    assert ds["agentSkillId"] == skill["id"]
    assert ds["agentSkillCommitSha"] == FAKE_COMMIT_SHA


async def test_workflow_design_session_unknown_workflow_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get("/api/v1/workflows/nonexistent/design-session")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- GET /design-sessions/{id} ----------


async def test_get_design_session_returns_200(workflow_client: AsyncClient) -> None:
    _skill, _wf, ds = await _design_session(workflow_client)
    response = await workflow_client.get(f"/api/v1/design-sessions/{ds['id']}")
    assert assert_ok(response)["id"] == ds["id"]


async def test_get_design_session_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get("/api/v1/design-sessions/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


async def test_get_design_session_forbidden_for_non_owner(
    workflow_client: AsyncClient,
) -> None:
    """Design has no approver sharing: only the owner (or super admin) may enter."""
    _skill, _wf, ds = await _design_session(workflow_client)
    response = await workflow_client.get(
        f"/api/v1/design-sessions/{ds['id']}",
        headers={"X-User-Id": "alice", "X-User-Roles": "developer"},
    )
    assert_err(response, code="FORBIDDEN", status=403)


async def test_get_design_session_allowed_for_super_admin(
    workflow_client: AsyncClient,
) -> None:
    _skill, _wf, ds = await _design_session(workflow_client)
    response = await workflow_client.get(
        f"/api/v1/design-sessions/{ds['id']}",
        headers={"X-User-Id": "alice", "X-User-Roles": "super_admin"},
    )
    assert_ok(response)


# ---------- GET /design-sessions/{id}/messages ----------


async def test_design_session_messages_empty_before_first_run(
    workflow_client: AsyncClient,
) -> None:
    _skill, _wf, ds = await _design_session(workflow_client)
    response = await workflow_client.get(f"/api/v1/design-sessions/{ds['id']}/messages")
    assert assert_ok(response) == []


async def test_design_session_messages_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get("/api/v1/design-sessions/nonexistent/messages")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- POST /design-sessions/{id}/agent ----------


async def test_design_session_agent_returns_200(
    workflow_client: AsyncClient,
    mock_agent_registry: MagicMock,
) -> None:
    _skill, _wf, ds = await _design_session(workflow_client)
    response = await workflow_client.post(
        f"/api/v1/design-sessions/{ds['id']}/agent",
        json=_make_run_agent_input(),
    )
    assert response.status_code == 200


async def test_design_session_agent_uses_design_kind(
    workflow_client: AsyncClient,
    mock_agent_registry: MagicMock,
) -> None:
    """The chat runs the interactive design agent pinned to the session's revision."""
    skill, _wf, ds = await _design_session(workflow_client)
    await workflow_client.post(
        f"/api/v1/design-sessions/{ds['id']}/agent",
        json=_make_run_agent_input(),
    )
    mock_agent_registry.get.assert_called_with(
        skill["id"],
        FAKE_COMMIT_SHA,
        mock_agent_registry.get.call_args.args[2],
        tenant_id=DEFAULT_TEST_TENANT_ID,
        kind=AgentKind.design,
    )


async def test_design_session_agent_forbidden_for_non_owner(
    workflow_client: AsyncClient,
    mock_agent_registry: MagicMock,
) -> None:
    _skill, _wf, ds = await _design_session(workflow_client)
    response = await workflow_client.post(
        f"/api/v1/design-sessions/{ds['id']}/agent",
        json=_make_run_agent_input(),
        headers={"X-User-Id": "alice", "X-User-Roles": "developer"},
    )
    assert_err(response, code="FORBIDDEN", status=403)


async def test_design_session_agent_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.post(
        "/api/v1/design-sessions/nonexistent/agent",
        json=_make_run_agent_input(),
    )
    assert response.status_code == 404


# ---------- lifecycle ----------


async def test_design_session_cascades_with_workflow(
    workflow_client: AsyncClient,
) -> None:
    _skill, wf, ds = await _design_session(workflow_client)
    assert_ok(await workflow_client.delete(f"/api/v1/workflows/{wf['id']}"))
    response = await workflow_client.get(f"/api/v1/design-sessions/{ds['id']}")
    assert_err(response, code="NOT_FOUND", status=404)
