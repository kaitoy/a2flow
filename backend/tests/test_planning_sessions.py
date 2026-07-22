"""Integration tests for the PlanningSession endpoints."""

from typing import Any
from unittest.mock import MagicMock

from httpx import AsyncClient

from infrastructure.agent import AgentKind
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID
from tests._workflow import create_skill, generate_workflow
from tests.conftest import FAKE_COMMIT_SHA


async def _planning_session(client: AsyncClient) -> tuple[Any, Any, Any]:
    """Generate a workflow and return (skill, workflow, planning_session)."""
    skill = await create_skill(client)
    wf = await generate_workflow(client, skill["id"])
    ps = assert_ok(await client.get(f"/api/v1/workflows/{wf['id']}/planning-session"))
    return skill, wf, ps


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


# ---------- GET /workflows/{id}/planning-session ----------


async def test_workflow_planning_session_lookup(workflow_client: AsyncClient) -> None:
    skill, wf, ps = await _planning_session(workflow_client)
    assert ps["workflowId"] == wf["id"]
    assert ps["agentSkillId"] == skill["id"]
    assert ps["agentSkillCommitSha"] == FAKE_COMMIT_SHA


async def test_workflow_planning_session_unknown_workflow_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get(
        "/api/v1/workflows/nonexistent/planning-session"
    )
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- GET /planning-sessions/{id} ----------


async def test_get_planning_session_returns_200(workflow_client: AsyncClient) -> None:
    _skill, _wf, ps = await _planning_session(workflow_client)
    response = await workflow_client.get(f"/api/v1/planning-sessions/{ps['id']}")
    assert assert_ok(response)["id"] == ps["id"]


async def test_get_planning_session_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get("/api/v1/planning-sessions/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


async def test_get_planning_session_forbidden_for_non_owner(
    workflow_client: AsyncClient,
) -> None:
    """Planning has no approver sharing: only the owner (or super admin) may enter."""
    _skill, _wf, ps = await _planning_session(workflow_client)
    response = await workflow_client.get(
        f"/api/v1/planning-sessions/{ps['id']}",
        headers={"X-User-Id": "alice", "X-User-Roles": "developer"},
    )
    assert_err(response, code="FORBIDDEN", status=403)


async def test_get_planning_session_allowed_for_super_admin(
    workflow_client: AsyncClient,
) -> None:
    _skill, _wf, ps = await _planning_session(workflow_client)
    response = await workflow_client.get(
        f"/api/v1/planning-sessions/{ps['id']}",
        headers={"X-User-Id": "alice", "X-User-Roles": "super_admin"},
    )
    assert_ok(response)


# ---------- GET /planning-sessions/{id}/messages ----------


async def test_planning_session_messages_empty_before_first_run(
    workflow_client: AsyncClient,
) -> None:
    _skill, _wf, ps = await _planning_session(workflow_client)
    response = await workflow_client.get(
        f"/api/v1/planning-sessions/{ps['id']}/messages"
    )
    assert assert_ok(response) == []


async def test_planning_session_messages_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get(
        "/api/v1/planning-sessions/nonexistent/messages"
    )
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- POST /planning-sessions/{id}/agent ----------


async def test_planning_session_agent_returns_200(
    workflow_client: AsyncClient,
    mock_agent_registry: MagicMock,
) -> None:
    _skill, _wf, ps = await _planning_session(workflow_client)
    response = await workflow_client.post(
        f"/api/v1/planning-sessions/{ps['id']}/agent",
        json=_make_run_agent_input(),
    )
    assert response.status_code == 200


async def test_planning_session_agent_uses_planning_kind(
    workflow_client: AsyncClient,
    mock_agent_registry: MagicMock,
) -> None:
    """The chat runs the interactive planning agent pinned to the session's revision."""
    skill, _wf, ps = await _planning_session(workflow_client)
    await workflow_client.post(
        f"/api/v1/planning-sessions/{ps['id']}/agent",
        json=_make_run_agent_input(),
    )
    mock_agent_registry.get.assert_called_with(
        skill["id"],
        FAKE_COMMIT_SHA,
        mock_agent_registry.get.call_args.args[2],
        tenant_id=DEFAULT_TEST_TENANT_ID,
        kind=AgentKind.planning,
    )


async def test_planning_session_agent_forbidden_for_non_owner(
    workflow_client: AsyncClient,
    mock_agent_registry: MagicMock,
) -> None:
    _skill, _wf, ps = await _planning_session(workflow_client)
    response = await workflow_client.post(
        f"/api/v1/planning-sessions/{ps['id']}/agent",
        json=_make_run_agent_input(),
        headers={"X-User-Id": "alice", "X-User-Roles": "developer"},
    )
    assert_err(response, code="FORBIDDEN", status=403)


async def test_planning_session_agent_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.post(
        "/api/v1/planning-sessions/nonexistent/agent",
        json=_make_run_agent_input(),
    )
    assert response.status_code == 404


# ---------- lifecycle ----------


async def test_planning_session_cascades_with_workflow(
    workflow_client: AsyncClient,
) -> None:
    _skill, wf, ps = await _planning_session(workflow_client)
    assert_ok(await workflow_client.delete(f"/api/v1/workflows/{wf['id']}"))
    response = await workflow_client.get(f"/api/v1/planning-sessions/{ps['id']}")
    assert_err(response, code="NOT_FOUND", status=404)
