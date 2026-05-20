from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

from httpx import AsyncClient

from tests._envelope import assert_err, assert_ok

_SKILL_BODY = {"name": "Skill A", "repo_url": "https://github.com/x/y"}
_WF_BODY = {"name": "My Workflow", "prompt": "Do the thing"}


async def _create_skill(client: AsyncClient) -> Any:
    return assert_ok(await client.post("/agent-skills", json=_SKILL_BODY), status=201)


async def _execute_workflow(client: AsyncClient, skill_id: str) -> Any:
    body = {**_WF_BODY, "agent_skill_id": skill_id}
    wf = assert_ok(await client.post("/workflows", json=body), status=201)
    return assert_ok(await client.post(f"/workflows/{wf['id']}/execute"), status=201)


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


# ---------- GET /workflow-sessions/{id} ----------


async def test_get_workflow_session_returns_200(workflow_client: AsyncClient) -> None:
    skill = await _create_skill(workflow_client)
    ws = await _execute_workflow(workflow_client, skill["id"])
    response = await workflow_client.get(f"/workflow-sessions/{ws['id']}")
    assert response.status_code == 200


async def test_get_workflow_session_returns_correct_data(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    ws = await _execute_workflow(workflow_client, skill["id"])
    body = assert_ok(await workflow_client.get(f"/workflow-sessions/{ws['id']}"))
    assert body["id"] == ws["id"]
    assert body["workflowName"] == _WF_BODY["name"]
    assert body["workflowPrompt"] == _WF_BODY["prompt"]
    assert body["agentSkillId"] == skill["id"]
    assert body["sessionId"] == ws["sessionId"]


async def test_get_workflow_session_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get("/workflow-sessions/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- POST /workflow-sessions/{id}/agent ----------


async def test_workflow_session_agent_returns_200(
    workflow_client: AsyncClient,
    mock_agent_registry: MagicMock,
) -> None:
    skill = await _create_skill(workflow_client)
    ws = await _execute_workflow(workflow_client, skill["id"])
    response = await workflow_client.post(
        f"/workflow-sessions/{ws['id']}/agent",
        json=_make_run_agent_input(),
    )
    assert response.status_code == 200


async def test_workflow_session_agent_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.post(
        "/workflow-sessions/nonexistent/agent",
        json=_make_run_agent_input(),
    )
    assert response.status_code == 404


async def test_workflow_session_agent_delegates_to_agent_registry(
    workflow_client: AsyncClient,
    mock_agent_registry: MagicMock,
    mock_adk_agent: MagicMock,
) -> None:
    skill = await _create_skill(workflow_client)
    ws = await _execute_workflow(workflow_client, skill["id"])

    events_yielded: list[Any] = []

    async def _capturing_run(*args: Any, **kwargs: Any) -> AsyncGenerator[Any, None]:
        return
        yield

    mock_adk_agent.run = _capturing_run
    await workflow_client.post(
        f"/workflow-sessions/{ws['id']}/agent",
        json=_make_run_agent_input(),
    )
    mock_agent_registry.get.assert_called_with(
        skill["id"], mock_agent_registry.get.call_args.args[1]
    )


async def test_workflow_session_agent_strips_system_messages(
    workflow_client: AsyncClient,
    mock_adk_agent: MagicMock,
) -> None:
    skill = await _create_skill(workflow_client)
    ws = await _execute_workflow(workflow_client, skill["id"])

    received_inputs: list[Any] = []

    async def _capturing_run(
        input_data: Any, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[Any, None]:
        received_inputs.append(input_data)
        return
        yield

    mock_adk_agent.run = _capturing_run

    input_with_system = {
        **_make_run_agent_input(),
        "messages": [
            {"id": "m1", "role": "system", "content": "You are helpful."},
            {"id": "m2", "role": "user", "content": "Hello"},
        ],
    }
    await workflow_client.post(
        f"/workflow-sessions/{ws['id']}/agent",
        json=input_with_system,
    )
    assert len(received_inputs) == 1
    assert all(m.role != "system" for m in received_inputs[0].messages)
