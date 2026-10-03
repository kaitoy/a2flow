from typing import Any

import pytest
from google.adk.sessions import InMemorySessionService
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from dependencies.context import APP_NAME
from infrastructure.agent import (
    tenant_app_name,
)
from models.user import SYSTEM_USER_ID
from models.workflow_execution import WorkflowExecution
from services.session_inputs import EXECUTION_KICKOFF_PROMPT
from tests._envelope import assert_err, assert_ok
from tests._seed import DEFAULT_TEST_TENANT_ID
from tests._workflow import (
    GENERATE_BODY,
    add_template,
    create_published_workflow,
    create_skill,
    generate_workflow,
    insert_workflow_task,
    publish_workflow,
)


async def _create_skill(client: AsyncClient) -> Any:
    return await create_skill(client)


async def _execute_workflow(client: AsyncClient, skill_id: str) -> Any:
    wf = await create_published_workflow(client, skill_id)
    return assert_ok(
        await client.post(f"/api/v1/workflows/{wf['id']}/execute"), status=201
    )


# ---------- GET /workflow-executions (list) ----------


async def test_list_workflow_executions_empty_initially(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get("/api/v1/workflow-executions")
    assert assert_ok(response) == []


async def test_list_workflow_executions_returns_executed_sessions(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    await _execute_workflow(workflow_client, skill["id"])
    response = await workflow_client.get("/api/v1/workflow-executions")
    assert len(assert_ok(response)) == 1


async def test_list_workflow_executions_respects_limit_param(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    wf = await create_published_workflow(workflow_client, skill["id"])
    for _ in range(3):
        assert_ok(
            await workflow_client.post(f"/api/v1/workflows/{wf['id']}/execute"),
            status=201,
        )
    response = await workflow_client.get(
        "/api/v1/workflow-executions", params={"limit": 2}
    )
    assert len(assert_ok(response)) == 2


# ---------- GET /workflow-executions/{id} ----------


async def test_get_workflow_execution_returns_200(workflow_client: AsyncClient) -> None:
    skill = await _create_skill(workflow_client)
    execution = await _execute_workflow(workflow_client, skill["id"])
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}"
    )
    assert response.status_code == 200


async def test_get_workflow_execution_returns_correct_data(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    execution = await _execute_workflow(workflow_client, skill["id"])
    body = assert_ok(
        await workflow_client.get(f"/api/v1/workflow-executions/{execution['id']}")
    )
    assert body["id"] == execution["id"]
    assert body["name"].startswith(f"{GENERATE_BODY['name']}-")
    assert "workflowPrompt" not in body
    assert body["agentSkillId"] == skill["id"]
    assert body["sessionId"] == execution["sessionId"]
    assert body["isDraft"] is False


async def test_get_workflow_execution_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get("/api/v1/workflow-executions/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- running a workflow ----------


async def test_execute_assigns_the_root_tasks_to_the_main_session(
    workflow_client: AsyncClient,
) -> None:
    """The first runnable tasks are the main session's before the agent's first turn."""
    skill = await _create_skill(workflow_client)
    wf = await generate_workflow(workflow_client, skill["id"])
    first = await add_template(workflow_client, wf["id"], title="First")
    await add_template(
        workflow_client, wf["id"], title="Second", depends_on_ids=[first["id"]]
    )
    await publish_workflow(workflow_client, wf["id"])
    execution = assert_ok(
        await workflow_client.post(f"/api/v1/workflows/{wf['id']}/execute"),
        status=201,
    )

    tasks = assert_ok(
        await workflow_client.get(
            f"/api/v1/workflow-executions/{execution['id']}/workflow-tasks"
        )
    )
    by_title = {t["title"]: t for t in tasks}
    assert by_title["First"]["sessionId"] == execution["sessionId"]
    assert by_title["Second"]["sessionId"] is None


# ---------- GET /workflow-executions/{id}/sessions/{sid}/messages ----------


async def test_workflow_execution_messages_show_the_queued_kickoff_before_first_run(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    execution = await _execute_workflow(workflow_client, skill["id"])
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/sessions/{execution['sessionId']}/messages"
    )
    history = assert_ok(response)
    assert history["streamCursor"] == 0
    assert history["running"] is True
    assert [m["content"] for m in history["messages"]] == [EXECUTION_KICKOFF_PROMPT]


async def test_workflow_execution_messages_shared_across_users(
    workflow_client: AsyncClient,
    real_session_service: InMemorySessionService,
) -> None:
    from google.adk.events.event import Event
    from google.genai import types

    skill = await _create_skill(workflow_client)
    execution = await _execute_workflow(workflow_client, skill["id"])

    # Seed the owner's ADK session with one user message.
    session = await real_session_service.create_session(
        app_name=tenant_app_name(APP_NAME, DEFAULT_TEST_TENANT_ID),
        user_id=execution["initiatorId"],
        session_id=execution["sessionId"],
    )
    await real_session_service.append_event(
        session,
        Event(
            author="user",
            content=types.Content(
                role="user", parts=[types.Part(text="hello from owner")]
            ),
        ),
    )

    # A different user (alice) fetches the history and sees the owner's messages.
    response = await workflow_client.get(
        f"/api/v1/workflow-executions/{execution['id']}/sessions/{execution['sessionId']}/messages",
        headers={"X-User-Id": "alice"},
    )
    messages = assert_ok(response)["messages"]
    # The kickoff is still queued, so it follows the seeded history.
    assert [m["content"] for m in messages] == [
        "hello from owner",
        EXECUTION_KICKOFF_PROMPT,
    ]
    # A message with no attribution row (legacy history) reports no sender, so
    # the UI can fall back to the execution initiator.
    assert messages[0]["senderUserId"] is None


async def test_workflow_execution_messages_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.get(
        "/api/v1/workflow-executions/nonexistent/sessions/nonexistent/messages"
    )
    assert_err(response, code="NOT_FOUND", status=404)


# ---------- DELETE /workflow-executions/{id} ----------


async def test_delete_workflow_execution_returns_200(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    execution = await _execute_workflow(workflow_client, skill["id"])
    response = await workflow_client.delete(
        f"/api/v1/workflow-executions/{execution['id']}"
    )
    assert assert_ok(response, status=200) is None


async def test_delete_workflow_execution_removes_from_list(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    execution = await _execute_workflow(workflow_client, skill["id"])
    await workflow_client.delete(f"/api/v1/workflow-executions/{execution['id']}")
    response = await workflow_client.get("/api/v1/workflow-executions")
    assert assert_ok(response) == []


async def test_delete_workflow_execution_cascades_tasks(
    workflow_client: AsyncClient,
) -> None:
    skill = await _create_skill(workflow_client)
    execution = await _execute_workflow(workflow_client, skill["id"])
    task_id = await insert_workflow_task(
        workflow_execution_id=execution["id"], title="Step one"
    )
    await workflow_client.delete(f"/api/v1/workflow-executions/{execution['id']}")
    response = await workflow_client.get(f"/api/v1/workflow-tasks/{task_id}")
    assert_err(response, code="NOT_FOUND", status=404)


async def test_delete_workflow_execution_deletes_adk_session(
    workflow_client: AsyncClient,
    real_session_service: InMemorySessionService,
) -> None:
    skill = await _create_skill(workflow_client)
    execution = await _execute_workflow(workflow_client, skill["id"])
    await real_session_service.create_session(
        app_name=tenant_app_name(APP_NAME, DEFAULT_TEST_TENANT_ID),
        user_id=SYSTEM_USER_ID,
        session_id=execution["sessionId"],
    )
    await workflow_client.delete(f"/api/v1/workflow-executions/{execution['id']}")
    remaining = await real_session_service.get_session(
        app_name=tenant_app_name(APP_NAME, DEFAULT_TEST_TENANT_ID),
        user_id=SYSTEM_USER_ID,
        session_id=execution["sessionId"],
    )
    assert remaining is None


async def test_delete_workflow_execution_succeeds_without_adk_session(
    workflow_client: AsyncClient,
) -> None:
    # The ADK session is created lazily on the first agent call, so a freshly
    # executed session has none. Deletion must still succeed.
    skill = await _create_skill(workflow_client)
    execution = await _execute_workflow(workflow_client, skill["id"])
    response = await workflow_client.delete(
        f"/api/v1/workflow-executions/{execution['id']}"
    )
    assert assert_ok(response, status=200) is None


async def test_delete_workflow_execution_unknown_id_returns_404(
    workflow_client: AsyncClient,
) -> None:
    response = await workflow_client.delete("/api/v1/workflow-executions/nonexistent")
    assert_err(response, code="NOT_FOUND", status=404)


async def test_delete_workflow_execution_requires_admin_role(
    workflow_client: AsyncClient,
) -> None:
    """Even the execution's own initiator cannot delete it without admin/super_admin.

    This is the behavior change from the previous initiator-or-super-admin rule:
    deletion is now admin-or-super-admin only, regardless of who started the run.
    """
    skill = await _create_skill(workflow_client)
    workflow = await create_published_workflow(workflow_client, skill["id"])
    execution = assert_ok(
        await workflow_client.post(
            f"/api/v1/workflows/{workflow['id']}/execute",
            headers={"X-User-Id": "alice", "X-User-Roles": "requester"},
        ),
        status=201,
    )
    response = await workflow_client.delete(
        f"/api/v1/workflow-executions/{execution['id']}",
        headers={"X-User-Id": "alice", "X-User-Roles": "requester"},
    )
    assert_err(response, code="FORBIDDEN", status=403)


async def test_delete_workflow_execution_allows_admin_who_is_not_initiator(
    workflow_client: AsyncClient,
) -> None:
    """A plain ``admin`` may delete an execution they did not initiate."""
    skill = await _create_skill(workflow_client)
    execution = await _execute_workflow(workflow_client, skill["id"])
    response = await workflow_client.delete(
        f"/api/v1/workflow-executions/{execution['id']}",
        headers={"X-User-Id": "carol", "X-User-Roles": "admin"},
    )
    assert assert_ok(response, status=200) is None


async def test_initiator_id_must_reference_an_existing_user(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """``initiator_id`` is a real FK, not just a documented convention.

    Written directly against the database because every API path that creates
    a WorkflowExecution takes the initiator from the authenticated caller, who
    also becomes ``created_by`` -- so a bad id would trip that FK first and
    this one would never be exercised.
    """
    _, engine = workflow_client_with_engine
    async with AsyncSession(engine) as db:
        db.add(
            WorkflowExecution(
                session_id="sess-orphan",
                name="wf",
                agent_skill_id="skill-1",
                agent_skill_name="skill",
                agent_skill_repo_url="https://example.com/repo",
                agent_skill_repo_path=".",
                initiator_id="ghost-user",
                tenant_id=DEFAULT_TEST_TENANT_ID,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()


# ---------- tool invocations ----------


async def test_tool_invocations_lists_the_runs_recorded_decisions(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    """Rows are written by the MCP gateway, so this seeds them directly."""
    from models.mcp_tool_invocation import McpAuditDecision, MCPToolInvocation

    client, engine = workflow_client_with_engine
    skill = await _create_skill(client)
    execution = await _execute_workflow(client, skill["id"])
    async with AsyncSession(engine) as db:
        for tool_name, decision in (
            ("search", McpAuditDecision.allowed),
            ("write", McpAuditDecision.denied),
        ):
            db.add(
                MCPToolInvocation(
                    session_id=execution["sessionId"],
                    workflow_execution_id=execution["id"],
                    mcp_server_id="srv-1",
                    tool_name=tool_name,
                    decision=decision,
                    arguments_digest="0" * 64,
                    tenant_id=DEFAULT_TEST_TENANT_ID,
                    created_by=SYSTEM_USER_ID,
                    updated_by=SYSTEM_USER_ID,
                )
            )
        await db.commit()

    body = assert_ok(
        await client.get(
            f"/api/v1/workflow-executions/{execution['id']}/tool-invocations"
        )
    )
    assert {row["toolName"] for row in body} == {"search", "write"}
    assert all(row["argumentsDigest"] == "0" * 64 for row in body)

    denied = assert_ok(
        await client.get(
            f"/api/v1/workflow-executions/{execution['id']}"
            "/tool-invocations?q=decision:eq:denied"
        )
    )
    assert [row["toolName"] for row in denied] == ["write"]


async def test_tool_invocations_of_another_run_are_not_listed(
    workflow_client_with_engine: tuple[AsyncClient, AsyncEngine],
) -> None:
    from models.mcp_tool_invocation import McpAuditDecision, MCPToolInvocation

    client, engine = workflow_client_with_engine
    skill = await _create_skill(client)
    workflow = await create_published_workflow(client, skill["id"])
    first = assert_ok(
        await client.post(f"/api/v1/workflows/{workflow['id']}/execute"), status=201
    )
    second = assert_ok(
        await client.post(f"/api/v1/workflows/{workflow['id']}/execute"), status=201
    )
    async with AsyncSession(engine) as db:
        db.add(
            MCPToolInvocation(
                session_id=first["sessionId"],
                workflow_execution_id=first["id"],
                mcp_server_id="srv-1",
                tool_name="search",
                decision=McpAuditDecision.allowed,
                arguments_digest="0" * 64,
                tenant_id=DEFAULT_TEST_TENANT_ID,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await db.commit()

    body = assert_ok(
        await client.get(f"/api/v1/workflow-executions/{second['id']}/tool-invocations")
    )
    assert body == []
