import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ag_ui.core import RunAgentInput
from ag_ui_adk import CONTEXT_STATE_KEY, ADKAgent, AGUIToolset
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import BaseSessionService
from google.adk.skills import load_skill_from_dir
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.skill_toolset import SkillToolset

from infrastructure.approval_tools import get_approval, list_users, request_approval
from infrastructure.mcp_tools import call_mcp_tool, list_mcp_tools
from infrastructure.workflow_task_tools import (
    create_workflow_task,
    delete_workflow_task,
    get_workflow_task,
    list_workflow_tasks,
    register_workflow_tasks,
    update_workflow_task,
)

ToolUnion = Callable[..., Any] | BaseTool | BaseToolset

LITELLM_PREFIX = "litellm:"

AGENT_SKILL_ID_KEY = "agent_skill_id"
SKILL_DIR_KEY = "skill_dir"

USER_ID_PROP_KEY = "userId"
DEFAULT_USER_ID = "user"


def extract_user_id(input_data: RunAgentInput) -> str:
    """Read the user id that the router placed into ``forwarded_props``.

    Used as the ``ADKAgent.user_id_extractor`` so the agent's session is keyed by
    the value the router injected from the trusted ``X-User-Id`` header.

    Args:
        input_data: The incoming AG-UI run input.

    Returns:
        The user id from ``forwarded_props['userId']``, or :data:`DEFAULT_USER_ID`
        when absent.
    """
    props = input_data.forwarded_props or {}
    return str(props.get(USER_ID_PROP_KEY, DEFAULT_USER_ID))


def with_user_id(input_data: RunAgentInput, user_id: str) -> RunAgentInput:
    """Return a copy of ``input_data`` with the trusted user id in ``forwarded_props``.

    Overrides any client-supplied ``userId`` so the agent's session is keyed by
    the server-validated identity rather than untrusted client props.

    Args:
        input_data: The incoming AG-UI run input.
        user_id: The user id derived from the ``X-User-Id`` header; falls back to
            :data:`DEFAULT_USER_ID` when empty.

    Returns:
        A copy of ``input_data`` whose ``forwarded_props['userId']`` is set.
    """
    props = dict(input_data.forwarded_props or {})
    props[USER_ID_PROP_KEY] = user_id or DEFAULT_USER_ID
    return input_data.model_copy(update={"forwarded_props": props})


WORKFLOW_AGENT_INSTRUCTION = (
    "You are a workflow execution agent. You have a Skill that defines how to do "
    "the work, plus tools to manage a list of WorkflowTasks for this run.\n\n"
    "Phase 1 - Plan: Follow the Skill's instructions to break the user's request "
    "into concrete steps. Before registering the plan, call `list_mcp_tools` to "
    "see the MCP tools available on the registered MCP servers. If a step needs "
    "an external tool, bind it by adding a `tools` entry "
    '(`[{"server_id": ..., "tool_name": ...}]`) to that task in '
    "`register_workflow_tasks`. Only bind tools a task actually needs. Express "
    "the steps as a DAG and register them in ONE call to "
    "`register_workflow_tasks`, using each task's `key` and `depends_on` to "
    "encode ordering. Every task starts as `pending`. Then present the registered "
    "plan to the user and ask for approval. Do NOT start executing until the user "
    "approves.\n\n"
    "Phase 2 - Execute (only after the user approves): loop until no `pending` "
    "tasks remain:\n"
    "1. Call `list_workflow_tasks` to see the current tasks and their statuses.\n"
    "2. Pick the next runnable task: a `pending` task whose `depends_on_ids` are "
    "all `completed`. If several are runnable, pick the lowest `position`.\n"
    "3. Call `update_workflow_task` to set its status to `in_progress`.\n"
    "4. Do that task's work according to the Skill. When the task has bound MCP "
    "tools (its `tool_bindings`), invoke them with "
    "`call_mcp_tool(server_id, tool_name, arguments)`; only tools bound to the "
    "current `in_progress` task are allowed, and calls to unbound tools are "
    "rejected.\n"
    "5. Call `update_workflow_task` to set `completed` (or `failed` if it cannot "
    "be done; use `skipped` only when the Skill says to skip).\n"
    "6. Repeat from step 1.\n\n"
    "Never start a task before its dependencies are completed. When every task is "
    "completed, failed, or skipped, summarize the outcome. Use "
    "`create_workflow_task`, `get_workflow_task`, and `delete_workflow_task` to "
    "adjust the plan when needed.\n\n"
    "Human approval: when a task requires the user's explicit go-ahead before you "
    "act (for example a destructive or irreversible operation), call "
    "`request_approval(title, description, workflow_task_id)` to record a pending "
    "approval and notify the user. To address the request to a specific person, "
    "first call `list_users` to look up the registered users and pass the chosen "
    "user's `id` as the `approver` argument. Then briefly explain the request in plain text "
    "and call the `render_approval` tool with the returned `approval_id` to show "
    "approve/reject controls in the UI; do NOT use A2UI buttons for this. The "
    "user's decision is returned as the `render_approval` result (and you can "
    "re-check it with `get_approval`). Only proceed when the decision is "
    "`approved`; if it is `rejected`, mark the task `failed` (or `skipped` when "
    "appropriate) and do not perform the action."
)


class A2UIInstructionProvider:
    def __init__(self, base_instruction: str) -> None:
        self._base = base_instruction

    def __call__(self, ctx: ReadonlyContext) -> str:
        context_entries = ctx.state.get(CONTEXT_STATE_KEY, [])
        a2ui_rules = (
            "# A2UI Rules\n"
            "When creating responses or requesting input from the user, use A2UI as appropriate.\n\n"
            "IMPORTANT: When your response contains Markdown (headings, lists, code blocks, bold, italic, etc.), "
            "you MUST render it via A2UI using Text components. Plain text messages do not render Markdown "
            "formatting, so users will see raw symbols (e.g. **bold**, ## Heading) instead of formatted text. "
            "Always use render_a2ui with Text components (with appropriate variant) to deliver any Markdown content."
        )
        parts = [f"# Role\n{self._base}", a2ui_rules]
        if context_entries:
            context_text = "\n\n".join(
                f"# {entry['description']}\n{entry['value']}"
                for entry in context_entries
            )
            parts.append(context_text)
        instruction = "\n\n".join(parts)
        return instruction


def create_agent(skill_dir: Path | None = None) -> LlmAgent:
    """
    Create an agent based on LLM_MODEL in .env.

    - Gemini model name (e.g. "gemini-*"): uses Google AI / Vertex AI directly
    - "litellm:<provider>/<model>" format: uses any LLM via LiteLLM
      e.g. litellm:openai/gpt-4o
           litellm:anthropic/claude-3-5-sonnet-20241022

    When `skill_dir` is provided, the directory is loaded as an ADK Skill and
    exposed to the agent via SkillToolset alongside the A2UI tools, the
    WorkflowTask management tools (register/create/list/get/update/delete), and
    the MCP proxy tools (`list_mcp_tools` / `call_mcp_tool`), and the agent runs
    under the plan-then-execute workflow instruction.
    """
    model_env = os.getenv("LLM_MODEL", "gemini-2.0-flash")
    role_description = os.getenv("ROLE_DESCRIPTION", "You are a helpful assistant.")

    model: LiteLlm | str
    if model_env.startswith(LITELLM_PREFIX):
        model_name = model_env[len(LITELLM_PREFIX) :]
        model = LiteLlm(model=model_name)
    else:
        model = model_env

    tools: list[ToolUnion] = [AGUIToolset()]
    if skill_dir is not None:
        skill = load_skill_from_dir(skill_dir)
        tools.append(SkillToolset(skills=[skill]))
        tools.extend(
            [
                register_workflow_tasks,
                create_workflow_task,
                list_workflow_tasks,
                get_workflow_task,
                update_workflow_task,
                delete_workflow_task,
                request_approval,
                get_approval,
                list_users,
                list_mcp_tools,
                call_mcp_tool,
            ]
        )
        instruction = A2UIInstructionProvider(WORKFLOW_AGENT_INSTRUCTION)
    else:
        instruction = A2UIInstructionProvider(role_description)

    return LlmAgent(
        name="simple_agent",
        model=model,
        instruction=instruction,
        tools=tools,
    )


class AgentRegistry:
    """Caches one ADKAgent per agent_skill_id (None = default agent without skill).

    Agents are stateless across sessions — per-session context lives in the ADK
    session state — so a single ADKAgent can serve every session that uses the
    same skill.
    """

    def __init__(self, session_service: BaseSessionService, app_name: str) -> None:
        self._session_service = session_service
        self._app_name = app_name
        self._cache: dict[str | None, ADKAgent] = {}

    def get(self, agent_skill_id: str | None, skill_dir: Path | None) -> ADKAgent:
        if agent_skill_id not in self._cache:
            llm_agent = create_agent(skill_dir=skill_dir)
            self._cache[agent_skill_id] = ADKAgent(
                adk_agent=llm_agent,
                app_name=self._app_name,
                user_id_extractor=extract_user_id,
                session_service=self._session_service,
                use_thread_id_as_session_id=True,
                emit_messages_snapshot=True,
                session_timeout_seconds=None,
            )
        return self._cache[agent_skill_id]
