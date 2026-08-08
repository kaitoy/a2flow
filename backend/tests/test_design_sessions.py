"""Integration tests for a workflow's design-session endpoints.

A design session has no record of its own: it is the ADK session named by
``Workflow.session_id``, keyed by the workflow's ``created_by``, and served
from ``/workflows/{id}/messages`` and ``/workflows/{id}/agent``. It is shared
by every ``developer`` in the tenant, so these tests also cover who may enter
and how each message is attributed to its real sender.
"""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

from google.adk.events.event import Event
from google.adk.sessions import InMemorySessionService
from google.genai import types
from httpx import AsyncClient

from dependencies import APP_NAME
from infrastructure.agent import AgentKind, tenant_app_name
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID
from tests._workflow import create_skill, generate_workflow, seed_design_transcript
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


async def test_design_session_messages_shared_across_developers(
    workflow_client: AsyncClient,
    real_session_service: InMemorySessionService,
) -> None:
    """Another developer in the tenant reads the owner's conversation, not an empty one."""
    _skill, wf = await _design_session(workflow_client)
    await seed_design_transcript(
        workflow_client, real_session_service, wf["id"], text="hello from owner"
    )

    response = await workflow_client.get(
        f"/api/v1/workflows/{wf['id']}/messages",
        headers={"X-User-Id": "alice", "X-User-Roles": "developer"},
    )
    messages = assert_ok(response)
    assert [m["content"] for m in messages] == ["hello from owner"]
    # The background generation run writes no attribution row, so the UI falls
    # back to the workflow's creator.
    assert messages[0]["senderUserId"] is None
    # A design session edits task templates, never status-ful tasks, so this is
    # always null -- but it is emitted so the payload matches a workflow session.
    assert messages[0]["workflowTaskId"] is None


async def test_design_session_messages_forbidden_without_developer_role(
    workflow_client: AsyncClient,
) -> None:
    """Designing is developer work: a requester may not enter the chat."""
    _skill, wf = await _design_session(workflow_client)
    response = await workflow_client.get(
        f"/api/v1/workflows/{wf['id']}/messages",
        headers={"X-User-Id": "alice", "X-User-Roles": "requester"},
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


async def test_design_session_messages_allowed_for_creator_without_role(
    workflow_client: AsyncClient,
) -> None:
    """The creator keeps access to their own chat even if their role is revoked."""
    _skill, wf = await _design_session(workflow_client)
    response = await workflow_client.get(
        f"/api/v1/workflows/{wf['id']}/messages",
        headers={"X-User-Id": wf["createdBy"], "X-User-Roles": ""},
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


async def test_design_session_agent_stamps_acting_user_in_state(
    workflow_client: AsyncClient,
    mock_adk_agent: MagicMock,
) -> None:
    """The actual driver of this turn (impersonation-aware) reaches the tools.

    ``forwarded_props['userId']`` stays pinned to the workflow's ``created_by``
    (the design session's owner, shared by every developer), but the
    ``ACTING_USER_STATE_KEY`` state entry must carry whoever is really driving
    this turn, so tool-call writes attribute to them instead of always to the
    session's owner.
    """
    from infrastructure.workflow_task_tools import ACTING_USER_STATE_KEY

    _skill, wf = await _design_session(workflow_client)

    received_inputs: list[Any] = []

    async def _capturing_run(
        input_data: Any, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[Any, None]:
        received_inputs.append(input_data)
        return
        yield

    mock_adk_agent.run = _capturing_run

    await workflow_client.post(
        f"/api/v1/workflows/{wf['id']}/agent",
        json=_make_run_agent_input(),
        headers={"X-User-Id": "alice", "X-User-Roles": "developer"},
    )
    assert received_inputs[0].state[ACTING_USER_STATE_KEY] == "alice"
    assert received_inputs[0].forwarded_props["userId"] == wf["createdBy"]
    assert wf["createdBy"] != "alice"


async def test_design_session_agent_allowed_for_other_developer(
    workflow_client: AsyncClient,
    mock_agent_registry: MagicMock,
) -> None:
    """Any developer in the tenant may drive the shared design chat."""
    _skill, wf = await _design_session(workflow_client)
    response = await workflow_client.post(
        f"/api/v1/workflows/{wf['id']}/agent",
        json=_make_run_agent_input(),
        headers={"X-User-Id": "alice", "X-User-Roles": "developer"},
    )
    assert response.status_code == 200


async def test_design_session_agent_forbidden_without_developer_role(
    workflow_client: AsyncClient,
    mock_agent_registry: MagicMock,
) -> None:
    _skill, wf = await _design_session(workflow_client)
    response = await workflow_client.post(
        f"/api/v1/workflows/{wf['id']}/agent",
        json=_make_run_agent_input(),
        headers={"X-User-Id": "alice", "X-User-Roles": "requester"},
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


async def test_design_session_messages_record_sender_after_run(
    workflow_client: AsyncClient,
    mock_adk_agent: MagicMock,
    real_session_service: InMemorySessionService,
) -> None:
    """A run by a non-owner developer attributes its message to that developer."""
    _skill, wf = await _design_session(workflow_client)

    async def _appending_run(
        input_data: Any, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[Any, None]:
        # Simulate ag_ui_adk appending the sender's user message to the shared,
        # owner-keyed ADK session during the run.
        session = await real_session_service.create_session(
            app_name=tenant_app_name(APP_NAME, DEFAULT_TEST_TENANT_ID),
            user_id=wf["createdBy"],
            session_id=wf["sessionId"],
        )
        await real_session_service.append_event(
            session,
            Event(
                author="user",
                content=types.Content(
                    role="user", parts=[types.Part(text="hi from alice")]
                ),
            ),
        )
        return
        yield

    mock_adk_agent.run = _appending_run

    await workflow_client.post(
        f"/api/v1/workflows/{wf['id']}/agent",
        json=_make_run_agent_input(),
        headers={"X-User-Id": "alice", "X-User-Roles": "developer"},
    )

    response = await workflow_client.get(f"/api/v1/workflows/{wf['id']}/messages")
    messages = assert_ok(response)
    assert [m["content"] for m in messages] == ["hi from alice"]
    # Attributed to the actual sender, not the session owner it is keyed by.
    assert messages[0]["senderUserId"] == "alice"


async def test_design_session_leaves_prior_messages_unattributed(
    workflow_client: AsyncClient,
    mock_adk_agent: MagicMock,
    real_session_service: InMemorySessionService,
) -> None:
    """A run attributes only what it appended, not the history it found."""
    _skill, wf = await _design_session(workflow_client)
    await seed_design_transcript(
        workflow_client, real_session_service, wf["id"], text="from the generation run"
    )

    async def _appending_run(
        input_data: Any, *args: Any, **kwargs: Any
    ) -> AsyncGenerator[Any, None]:
        session = await real_session_service.get_session(
            app_name=tenant_app_name(APP_NAME, DEFAULT_TEST_TENANT_ID),
            user_id=wf["createdBy"],
            session_id=wf["sessionId"],
        )
        assert session is not None
        await real_session_service.append_event(
            session,
            Event(
                author="user",
                content=types.Content(
                    role="user", parts=[types.Part(text="hi from alice")]
                ),
            ),
        )
        return
        yield

    mock_adk_agent.run = _appending_run

    await workflow_client.post(
        f"/api/v1/workflows/{wf['id']}/agent",
        json=_make_run_agent_input(),
        headers={"X-User-Id": "alice", "X-User-Roles": "developer"},
    )

    messages = assert_ok(
        await workflow_client.get(f"/api/v1/workflows/{wf['id']}/messages")
    )
    assert [m["senderUserId"] for m in messages] == [None, "alice"]
