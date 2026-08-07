"""Integration tests for a workflow's design-session endpoints.

A design session has no record of its own: it is the ADK session named by
``Workflow.session_id``, owned by the workflow's ``created_by``, and served
from ``/workflows/{id}/messages`` and ``/workflows/{id}/agent``.
"""

from typing import Any
from unittest.mock import MagicMock

from httpx import AsyncClient

from infrastructure.agent import AgentKind
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID
from tests._workflow import create_skill, generate_workflow
from tests.conftest import FAKE_COMMIT_SHA


async def _design_session(client: AsyncClient) -> tuple[Any, Any]:
    """Generate a workflow and return ``(skill, workflow)``."""
    skill = await create_skill(client)
    wf = await generate_workflow(client, skill["id"])
    return skill, wf


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


# ---------- the design session's fields on the workflow ----------


async def test_workflow_carries_its_design_session(
    workflow_client: AsyncClient,
) -> None:
    """The generated workflow names the chat it is designed in and its pinned revision."""
    skill, wf = await _design_session(workflow_client)
    assert wf["agentSkillId"] == skill["id"]
    assert wf["agentSkillCommitSha"] == FAKE_COMMIT_SHA
    assert wf["sessionId"]

    fetched = assert_ok(await workflow_client.get(f"/api/v1/workflows/{wf['id']}"))
    assert fetched["sessionId"] == wf["sessionId"]
    assert fetched["agentSkillCommitSha"] == FAKE_COMMIT_SHA


# ---------- GET /workflows/{id}/messages ----------


async def test_design_session_messages_empty_before_first_run(
    workflow_client: AsyncClient,
) -> None:
    _skill, wf = await _design_session(workflow_client)
    response = await workflow_client.get(f"/api/v1/workflows/{wf['id']}/messages")
    assert assert_ok(response) == []


async def test_design_session_messages_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get("/api/v1/workflows/nonexistent/messages")
    assert_err(response, code="NOT_FOUND", status=404)


async def test_design_session_messages_forbidden_for_non_owner(
    workflow_client: AsyncClient,
) -> None:
    """Design has no approver sharing: only the owner (or super admin) may enter."""
    _skill, wf = await _design_session(workflow_client)
    response = await workflow_client.get(
        f"/api/v1/workflows/{wf['id']}/messages",
        headers={"X-User-Id": "alice", "X-User-Roles": "developer"},
    )
    assert_err(response, code="FORBIDDEN", status=403)


async def test_design_session_messages_allowed_for_super_admin(
    workflow_client: AsyncClient,
) -> None:
    _skill, wf = await _design_session(workflow_client)
    response = await workflow_client.get(
        f"/api/v1/workflows/{wf['id']}/messages",
        headers={"X-User-Id": "alice", "X-User-Roles": "super_admin"},
    )
    assert_ok(response)


# ---------- POST /workflows/{id}/agent ----------


async def test_design_session_agent_returns_200(
    workflow_client: AsyncClient,
    mock_agent_registry: MagicMock,
) -> None:
    _skill, wf = await _design_session(workflow_client)
    response = await workflow_client.post(
        f"/api/v1/workflows/{wf['id']}/agent",
        json=_make_run_agent_input(),
    )
    assert response.status_code == 200


async def test_design_session_agent_uses_design_kind(
    workflow_client: AsyncClient,
    mock_agent_registry: MagicMock,
) -> None:
    """The chat runs the interactive design agent pinned to the workflow's revision."""
    skill, wf = await _design_session(workflow_client)
    await workflow_client.post(
        f"/api/v1/workflows/{wf['id']}/agent",
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
    _skill, wf = await _design_session(workflow_client)
    response = await workflow_client.post(
        f"/api/v1/workflows/{wf['id']}/agent",
        json=_make_run_agent_input(),
        headers={"X-User-Id": "alice", "X-User-Roles": "developer"},
    )
    assert_err(response, code="FORBIDDEN", status=403)


async def test_design_session_agent_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.post(
        "/api/v1/workflows/nonexistent/agent",
        json=_make_run_agent_input(),
    )
    assert response.status_code == 404
