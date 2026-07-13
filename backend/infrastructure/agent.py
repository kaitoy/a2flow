from collections import OrderedDict
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ag_ui.core import Message, RunAgentInput, TextInputContent, UserMessage
from ag_ui_adk import CONTEXT_STATE_KEY, ADKAgent, AGUIToolset
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.apps import App, ResumabilityConfig
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import BaseSessionService
from google.adk.skills import load_skill_from_dir
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.skill_toolset import SkillToolset

from config import get_settings
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

SESSION_TITLE_KEY = "session_title"

USER_ID_PROP_KEY = "userId"
DEFAULT_USER_ID = "user"

#: ``forwarded_props`` flag that ``@ag-ui/a2ui-middleware`` sets on every request
#: (see its ``injectToolAndFlag``). ``ag-ui-adk`` >= 0.7.0 reads it as the opt-in
#: for server-side A2UI generation: it drops the frontend-injected ``render_a2ui``
#: tool and injects its own ``generate_a2ui`` sub-agent instead. A2Flow renders
#: A2UI on the frontend (see ``docs/a2ui-flow.md``) and its agent instruction
#: tells the LLM to call ``render_a2ui``, so the flag is stripped to keep that
#: tool in place.
A2UI_INJECT_PROP_KEY = "injectA2UITool"

_SESSION_TITLE_MAX_LENGTH = 60

#: Upper bound on cached ADKAgents in :class:`AgentRegistry`. One entry per
#: skill revision actually run; pulling past a revision leaves its entry behind,
#: so the cache is capped rather than left to grow with the pull count.
_AGENT_CACHE_MAX_ENTRIES = 64


def first_user_message_text(messages: Sequence[Message]) -> str | None:
    """Return the text of the first user message in ``messages``, if any.

    Args:
        messages: The AG-UI messages to scan.

    Returns:
        The message's ``content`` when it is a plain string, the first
        ``TextInputContent`` fragment's text when it is multimodal content, or
        ``None`` when no user message with extractable text is found.
    """
    for message in messages:
        if not isinstance(message, UserMessage):
            continue
        if isinstance(message.content, str):
            return message.content
        for part in message.content:
            if isinstance(part, TextInputContent):
                return part.text
        return None
    return None


def derive_session_title(text: str) -> str | None:
    """Derive a short session title from a message's raw text.

    Args:
        text: The raw message text to summarize.

    Returns:
        The whitespace-collapsed text truncated to
        :data:`_SESSION_TITLE_MAX_LENGTH` characters (with a trailing
        ellipsis when truncated), or ``None`` when ``text`` has no visible
        content.
    """
    collapsed = " ".join(text.split())
    if not collapsed:
        return None
    if len(collapsed) <= _SESSION_TITLE_MAX_LENGTH:
        return collapsed
    return collapsed[:_SESSION_TITLE_MAX_LENGTH].rstrip() + "…"


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
    """Return a copy of ``input_data`` with ``forwarded_props`` sanitized.

    ``forwarded_props`` is client-controlled, so both run endpoints funnel their
    input through this before handing it to :class:`~ag_ui_adk.ADKAgent`:

    - ``userId`` is overridden so the agent's session is keyed by the
      server-validated identity rather than an untrusted client prop.
    - :data:`A2UI_INJECT_PROP_KEY` is dropped so ``ag-ui-adk`` leaves the
      frontend-injected ``render_a2ui`` tool alone instead of swapping in its own
      server-side A2UI sub-agent.

    Args:
        input_data: The incoming AG-UI run input.
        user_id: The user id derived from the ``X-User-Id`` header; falls back to
            :data:`DEFAULT_USER_ID` when empty.

    Returns:
        A copy of ``input_data`` whose ``forwarded_props['userId']`` is set and
        whose A2UI injection flag is removed.
    """
    props = dict(input_data.forwarded_props or {})
    props[USER_ID_PROP_KEY] = user_id or DEFAULT_USER_ID
    props.pop(A2UI_INJECT_PROP_KEY, None)
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
    "Human approval: when a task requires a person's explicit go-ahead before you "
    "act (for example a destructive or irreversible operation), call "
    "`request_approval(title, approver, description, workflow_task_id)` to record a "
    "pending approval and notify the approver. The `approver` is required: first "
    "call `list_users` to look up the registered users and pass the chosen user's "
    "`id` as the `approver` argument — only that user is notified and only they can "
    "approve or reject the request. Then briefly explain the request in plain text "
    "and call the `render_approval` tool with the returned `approval_id` to show "
    "approve/reject controls in the UI; do NOT use A2UI buttons for this. The "
    "user's decision is returned as the `render_approval` result (and you can "
    "re-check it with `get_approval`). Only proceed when the decision is "
    "`approved`; if it is `rejected`, mark the task `failed` (or `skipped` when "
    "appropriate) and do not perform the action."
)


class A2UIInstructionProvider:
    """Instruction provider that appends the shared A2UI usage rules.

    Wraps a base role instruction and composes the final agent instruction as
    ``# Role`` + the A2UI rules (input requests go through ``render_a2ui``
    input components; informational messages stay as streamed plain text) +
    any context entries stored in session state.
    """

    def __init__(self, base_instruction: str) -> None:
        self._base = base_instruction

    def __call__(self, ctx: ReadonlyContext) -> str:
        context_entries = ctx.state.get(CONTEXT_STATE_KEY, [])
        a2ui_rules = (
            "# A2UI Rules\n"
            "A2UI (`render_a2ui`) is for collecting input from the user, not for prose.\n\n"
            "When you need input from the user (a question, a choice between options, "
            "parameters, a confirmation), ALWAYS call `render_a2ui` and present input "
            "components so the user can see exactly what to provide:\n"
            "- `TextField` for free-form values (use the `longText` variant for multi-line input),\n"
            "- `ChoicePicker` for selecting among known options (`mutuallyExclusive` for a single choice),\n"
            "- a `Button` that submits the action,\n"
            "- short `Text` components inside the surface for labels and context only.\n\n"
            "When you are only conveying information (status updates, explanations, results, "
            "summaries), reply with plain streamed text and do NOT call `render_a2ui`. Plain "
            "messages render Markdown, and text streams token-by-token so the user sees your "
            "output immediately instead of waiting for a tool call to finish."
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
    Create an agent based on ``config.Settings.llm_model``.

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
    settings = get_settings()
    model_env = settings.llm_model
    role_description = settings.role_description

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


def create_app(app_name: str, skill_dir: Path | None = None) -> App:
    """Wrap :func:`create_agent` in a resumable ADK :class:`~google.adk.apps.App`.

    Resumability is what makes ADK itself own the human-in-the-loop pause: the
    Runner persists the long-running FunctionCall event and suspends the
    invocation, so ``ag-ui-adk`` can drain its event stream to completion instead
    of taking its deprecated "fire-and-forget" path. That path abandons ADK's
    ``run_async`` async generator mid-iteration on the first long-running tool
    call (``render_a2ui``, ``render_approval``); the generator is then finalized
    by asyncio's async-generator hook in a *different* task, so the OpenTelemetry
    context tokens its suspended spans hold get detached from a context they were
    not created in — one ``Failed to detach context`` ERROR per long-running tool
    call.

    Args:
        app_name: Name of the ADK app; ``ADKAgent.from_app`` adopts it as the
            agent's ``app_name``, so it must match the one the routers use.
        skill_dir: Directory ADK loads the skill from, or ``None`` for the
            default skill-less agent.

    Returns:
        An App wrapping the agent, with resumability enabled.
    """
    return App(
        name=app_name,
        root_agent=create_agent(skill_dir=skill_dir),
        resumability_config=ResumabilityConfig(is_resumable=True),
    )


class AgentRegistry:
    """Caches one ADKAgent per ``(agent_skill_id, commit_sha)`` revision of a skill.

    Agents are stateless across sessions — per-session context lives in the ADK
    session state — so a single ADKAgent serves every session running the same
    revision of the same skill. ``(None, None)`` keys the default agent that has
    no skill loaded.

    The revision has to be part of the key because ``create_agent`` reads the
    skill directory eagerly (``load_skill_from_dir`` slurps every file into
    memory) and never looks at it again. Keying on the skill alone would pin the
    first revision loaded for the life of the process, so a ``pull`` would never
    take effect; keying on the revision means a pull is picked up by the next
    session while sessions already pinned to the old revision keep the agent
    they started with.

    Bounded by :data:`_AGENT_CACHE_MAX_ENTRIES` on a least-recently-used basis:
    pruning keeps the number of live revisions small, but nothing else would
    ever evict the entry for a revision that has been pulled past.

    Every agent is built through ``ADKAgent.from_app(create_app(...))`` rather
    than the plain ``ADKAgent(...)`` constructor, so long-running tool calls pause
    on ADK's own resumability machinery — see :func:`create_app`.
    """

    def __init__(self, session_service: BaseSessionService, app_name: str) -> None:
        self._session_service = session_service
        self._app_name = app_name
        self._cache: OrderedDict[tuple[str | None, str | None], ADKAgent] = (
            OrderedDict()
        )

    def get(
        self,
        agent_skill_id: str | None,
        commit_sha: str | None,
        skill_dir: Path | None,
    ) -> ADKAgent:
        """Return the ADKAgent for one revision of a skill, building it on first use.

        Args:
            agent_skill_id: Id of the skill, or ``None`` for the default
                skill-less agent.
            commit_sha: The published revision of that skill, or ``None`` for
                the default agent.
            skill_dir: Directory ADK loads the skill from; only read when the
                agent is not already cached.

        Returns:
            The cached (or freshly built) agent for that revision.
        """
        key = (agent_skill_id, commit_sha)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        agent = ADKAgent.from_app(
            create_app(self._app_name, skill_dir=skill_dir),
            user_id_extractor=extract_user_id,
            session_service=self._session_service,
            use_thread_id_as_session_id=True,
            emit_messages_snapshot=True,
            session_timeout_seconds=None,
        )
        self._cache[key] = agent
        if len(self._cache) > _AGENT_CACHE_MAX_ENTRIES:
            self._cache.popitem(last=False)
        return agent
