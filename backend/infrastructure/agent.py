from collections import OrderedDict
from collections.abc import Callable, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any

from ag_ui.core import Context, Message, RunAgentInput, TextInputContent, UserMessage
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
from infrastructure.planning_task_tools import (
    create_planning_task,
    delete_planning_task,
    get_planning_task,
    list_planning_tasks,
    register_planning_tasks,
    update_planning_task,
)
from infrastructure.workflow_task_tools import (
    create_workflow_task,
    delete_workflow_task,
    get_workflow_task,
    list_workflow_tasks,
    update_workflow_task,
)

ToolUnion = Callable[..., Any] | BaseTool | BaseToolset

LITELLM_PREFIX = "litellm:"


class AgentKind(StrEnum):
    """Role a skill-backed agent plays, selecting its instruction and toolset.

    ``initial_planning`` is the unattended background run that turns a
    "Generate workflow" prompt into the workflow's first task templates; it
    carries no A2UI toolset because no client is connected to execute frontend
    tools. ``planning`` is the interactive planning-session chat used to refine
    the templates. ``execution`` drives a WorkflowSession created from a
    published workflow.
    """

    initial_planning = "initial_planning"
    planning = "planning"
    execution = "execution"


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

#: Descriptions of the two ``context`` entries ``@ag-ui/a2ui-middleware`` injects
#: on every request (see its ``injectSchemaContext`` / ``injectToolGuidelines``):
#: the component catalog, and the argument format for ``render_a2ui``. Neither is
#: derivable from the tool's own JSON schema, which types ``components`` as a bare
#: array of objects — without them the LLM guesses the component shape (``type``
#: instead of ``component``) and invents component names, and every surface it
#: renders dies in the client's ``MessageProcessor``.
#:
#: Both strings must stay byte-identical to the middleware's: it matches them by
#: exact equality to replace its own entries, and so does :func:`keep_a2ui_context`.
#: The guide's description embeds the tool name, which is ``render_a2ui`` because
#: A2Flow passes ``injectA2UITool: true`` (a bool, not a custom name).
A2UI_SCHEMA_CONTEXT_DESCRIPTION = (
    "A2UI Component Schema — available components for generating UI surfaces. "
    "Use these component names and properties when creating A2UI operations."
)
A2UI_GUIDE_CONTEXT_DESCRIPTION = (
    "A2UI render tool usage guide — how to call render_a2ui with valid arguments."
)

_SESSION_TITLE_MAX_LENGTH = 60

#: Upper bound on cached ADKAgents per tenant in :class:`AgentRegistry`. One
#: entry per skill revision actually run; pulling past a revision leaves its
#: entry behind, so each tenant's cache is capped rather than left to grow with
#: the pull count.
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


def keep_a2ui_context(context: Sequence[Context]) -> list[Context]:
    """Return only the A2UI entries of a client-sent ``context``.

    ``context`` feeds the agent's system instruction (via ``CONTEXT_STATE_KEY``),
    so an endpoint that shares one ADK session across users cannot pass the
    client's through wholesale. It cannot drop it wholesale either: the A2UI
    component catalog and ``render_a2ui`` call format reach the LLM *only* as
    context entries the frontend middleware injects, so discarding them leaves it
    inventing an A2UI dialect the client cannot render.

    This keeps the two entries A2Flow's own middleware config produces — matched
    by :data:`A2UI_SCHEMA_CONTEXT_DESCRIPTION` / :data:`A2UI_GUIDE_CONTEXT_DESCRIPTION`
    — and drops everything else, including any extra entry a client invents. Their
    *values* are still client-supplied, so this is an allowlist of purpose, not a
    proof of provenance; a caller who forges one only reaches an LLM they can
    already send chat messages to.

    Args:
        context: The client-sent context entries.

    Returns:
        The subset carrying A2UI instructions, in their original order.
    """
    allowed = {A2UI_SCHEMA_CONTEXT_DESCRIPTION, A2UI_GUIDE_CONTEXT_DESCRIPTION}
    return [entry for entry in context if entry.description in allowed]


#: Shared description of the plan-registration call, used by both planning
#: instructions so the DAG/tool-binding rules stay identical.
_PLAN_REGISTRATION_RULES = (
    "Before registering the plan, call `list_mcp_tools` to see the MCP tools "
    "available on the registered MCP servers. If a step needs an external tool, "
    'bind it by adding a `tools` entry (`[{"server_id": ..., "tool_name": ...}]`) '
    "to that task in `register_planning_tasks`. Only bind tools a task actually "
    "needs. Express the steps as a DAG and register them in ONE call to "
    "`register_planning_tasks`, using each task's `key` and `depends_on` to "
    "encode ordering."
)

INITIAL_PLANNING_AGENT_INSTRUCTION = (
    "You are a workflow planning agent running unattended in the background: "
    "nobody is watching this run and nobody can answer questions. A draft "
    "Workflow was just created from the user's request (the first message). "
    "Your only job is to turn that request into the workflow's task templates.\n\n"
    "Follow the Skill's instructions to break the request into concrete steps. "
    + _PLAN_REGISTRATION_RULES
    + "\n\n"
    "After registering, reply with a concise plain-text summary of the plan. "
    "Do NOT execute any task, do NOT ask questions, and do NOT wait for input — "
    "finish in this single run."
)

PLANNING_AGENT_INSTRUCTION = (
    "You are a workflow planning agent. This chat is the planning session of a "
    "Workflow: the task templates you manage here are the workflow's reusable "
    "plan, executed later (and possibly many times) in separate workflow "
    "sessions once the workflow is published.\n\n"
    "Use `list_planning_tasks` to see the current plan. Refine it as the user "
    "asks with `create_planning_task`, `update_planning_task`, and "
    "`delete_planning_task`; when the plan is still empty (or the user asks to "
    "rebuild it from scratch), follow the Skill's instructions to break the "
    "request into concrete steps. " + _PLAN_REGISTRATION_RULES + "\n\n"
    "After changing the plan, present the result and ask whether further "
    "adjustments are needed. Never execute a task: this session only shapes the "
    "plan. Publishing the workflow and running it happen outside this chat."
)

EXECUTION_AGENT_INSTRUCTION = (
    "You are a workflow execution agent. You have a Skill that defines how to "
    "do the work, plus tools to manage this run's WorkflowTasks. The plan was "
    "prepared and approved in advance: this session already contains its tasks, "
    "copied from the workflow's published templates (the workflow's description "
    "is provided as context). Begin executing immediately — do NOT re-plan and "
    "do NOT ask for approval of the plan.\n\n"
    "Execute: loop until no `pending` tasks remain:\n"
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
    input components; informational messages stay as streamed plain text; the
    user's input is read from the render call's ``values`` result, not from the
    action ``context``) + any context entries stored in session state.
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
            "The result of a `render_a2ui` call tells you what the user did with the surface. "
            'When they submit it, the result is a JSON object with `status: "action"` whose '
            "`values` field is the surface's entire data model — every value the user typed or "
            "selected, keyed by the paths the input components bind to. Read the user's input "
            "from `values`; do not rely on the action's `context`, which holds only the bindings "
            'you declared on the acted-on component. A result of `{"status": "rendered"}` '
            "means the surface was shown but the user has not acted on it.\n\n"
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


def resolve_model() -> LiteLlm | str:
    """Resolve ``config.Settings.llm_model`` into an ADK model selection.

    - Gemini model name (e.g. "gemini-*"): returned as-is, so ADK uses
      Google AI / Vertex AI directly.
    - "litellm:<provider>/<model>" format: wrapped in :class:`LiteLlm` so any
      LLM can be used via LiteLLM, e.g. ``litellm:openai/gpt-4o``.

    Shared by :func:`create_agent` and the one-shot summarizer
    (:mod:`infrastructure.summarizer`) so model selection is defined once.
    """
    model_env = get_settings().llm_model
    if model_env.startswith(LITELLM_PREFIX):
        return LiteLlm(model=model_env[len(LITELLM_PREFIX) :])
    return model_env


#: Task-management toolset per skill-backed agent kind. Planning kinds edit the
#: workflow's task templates through the planning tools; the execution kind
#: manages the run's WorkflowTasks (with no bulk registration — the plan comes
#: pre-copied from the templates) plus the approval and MCP invocation tools.
_KIND_TOOLS: dict[AgentKind, list[ToolUnion]] = {
    AgentKind.initial_planning: [
        register_planning_tasks,
        list_planning_tasks,
        list_mcp_tools,
    ],
    AgentKind.planning: [
        register_planning_tasks,
        create_planning_task,
        list_planning_tasks,
        get_planning_task,
        update_planning_task,
        delete_planning_task,
        list_mcp_tools,
    ],
    AgentKind.execution: [
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
    ],
}


def create_agent(
    skill_dir: Path | None = None, kind: AgentKind = AgentKind.execution
) -> LlmAgent:
    """Create an agent based on ``config.Settings.llm_model``.

    When ``skill_dir`` is provided, the directory is loaded as an ADK Skill and
    exposed to the agent via SkillToolset, and ``kind`` selects the instruction
    and task toolset: planning kinds manage the workflow's task templates
    (``*_planning_task`` tools), while the execution kind manages the run's
    WorkflowTasks plus the approval and MCP invocation tools. The
    ``initial_planning`` kind is built without the A2UI toolset (and without
    the A2UI instruction rules) because its run happens in the background with
    no client connected to execute frontend tools. Without ``skill_dir`` the
    default skill-less chat agent is returned and ``kind`` is ignored.
    """
    settings = get_settings()
    role_description = settings.role_description
    model = resolve_model()

    instruction: str | A2UIInstructionProvider
    tools: list[ToolUnion]
    if skill_dir is not None:
        skill = load_skill_from_dir(skill_dir)
        tools = [] if kind is AgentKind.initial_planning else [AGUIToolset()]
        tools.append(SkillToolset(skills=[skill]))
        tools.extend(_KIND_TOOLS[kind])
        if kind is AgentKind.initial_planning:
            instruction = INITIAL_PLANNING_AGENT_INSTRUCTION
        elif kind is AgentKind.planning:
            instruction = A2UIInstructionProvider(PLANNING_AGENT_INSTRUCTION)
        else:
            instruction = A2UIInstructionProvider(EXECUTION_AGENT_INSTRUCTION)
    else:
        tools = [AGUIToolset()]
        instruction = A2UIInstructionProvider(role_description)

    return LlmAgent(
        name="simple_agent",
        model=model,
        instruction=instruction,
        tools=tools,
    )


def create_app(
    app_name: str,
    skill_dir: Path | None = None,
    kind: AgentKind = AgentKind.execution,
) -> App:
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
            agent's ``app_name``, so it must match the one the routers use. For
            a tenant-scoped run this is :func:`tenant_app_name`'s result, as
            computed by :meth:`AgentRegistry.get`.
        skill_dir: Directory ADK loads the skill from, or ``None`` for the
            default skill-less agent.
        kind: Role of the skill-backed agent (see :class:`AgentKind`); ignored
            when ``skill_dir`` is ``None``.

    Returns:
        An App wrapping the agent, with resumability enabled.
    """
    return App(
        name=app_name,
        root_agent=create_agent(skill_dir=skill_dir, kind=kind),
        resumability_config=ResumabilityConfig(is_resumable=True),
    )


def tenant_app_name(app_name: str, tenant_id: str) -> str:
    """Scope a base ADK application name to one tenant.

    ADK's session store and :class:`AgentRegistry`'s agent cache are both keyed
    by app_name, so two tenants sharing one process must use distinct strings
    here or one tenant could read another's ADK sessions or reuse another
    tenant's cached agent. Every caller that talks to ``session_service``,
    builds a run lock key (``infrastructure.locks.agent_run_key``), or calls
    :meth:`AgentRegistry.get` must derive its app_name through this helper once
    a ``tenant_id`` is in scope — never the bare ``dependencies.context.APP_NAME``
    constant directly — so all three call sites keep agreeing on the same
    identity.

    The colon that would be the obvious separator is not an option: this string
    is also used as ADK's ``App.name``, which
    ``google.adk.apps.app.validate_app_name`` restricts to
    ``^[a-zA-Z][a-zA-Z0-9_-]*$`` (letters, digits, underscores, and hyphens
    only), so a hyphen is used instead. ``tenant_id`` is a UUID7 string, which
    already satisfies that character set on its own.

    Args:
        app_name: The process-wide base app name (``dependencies.context.APP_NAME``).
        tenant_id: The tenant to scope the name to.

    Returns:
        The tenant-scoped app name.
    """
    return f"{app_name}-{tenant_id}"


class AgentRegistry:
    """Caches one ADKAgent per tenant, per ``(agent_skill_id, commit_sha, kind)``.

    Agents are stateless across sessions — per-session context lives in the ADK
    session state — so a single ADKAgent serves every session running the same
    revision of the same skill in the same role, for the same tenant.
    ``(None, None, execution)`` keys the default agent that has no skill loaded.

    The revision has to be part of the key because ``create_agent`` reads the
    skill directory eagerly (``load_skill_from_dir`` slurps every file into
    memory) and never looks at it again. Keying on the skill alone would pin the
    first revision loaded for the life of the process, so a ``pull`` would never
    take effect; keying on the revision means a pull is picked up by the next
    session while sessions already pinned to the old revision keep the agent
    they started with.

    Each tenant gets its own cache, bounded by :data:`_AGENT_CACHE_MAX_ENTRIES`
    on a least-recently-used basis: pruning keeps the number of live revisions
    small per tenant, but nothing else would ever evict the entry for a
    revision that has been pulled past. Partitioning by tenant means one
    tenant filling its cache cannot evict another tenant's agents. The outer
    mapping — the set of tenants with at least one cached agent — is itself
    unbounded; nothing currently prunes the entry for a tenant that stops being
    active. This is a known, accepted tradeoff, not something this cache
    solves.

    Every agent is built through ``ADKAgent.from_app(create_app(...))`` rather
    than the plain ``ADKAgent(...)`` constructor, so long-running tool calls pause
    on ADK's own resumability machinery — see :func:`create_app`.
    """

    def __init__(self, session_service: BaseSessionService, app_name: str) -> None:
        self._session_service = session_service
        self._app_name = app_name
        self._cache: dict[
            str, OrderedDict[tuple[str | None, str | None, AgentKind], ADKAgent]
        ] = {}

    def get(
        self,
        agent_skill_id: str | None,
        commit_sha: str | None,
        skill_dir: Path | None,
        *,
        tenant_id: str,
        kind: AgentKind = AgentKind.execution,
    ) -> ADKAgent:
        """Return the ADKAgent for one tenant's revision of a skill.

        Builds and caches it on first use.

        Args:
            agent_skill_id: Id of the skill, or ``None`` for the default
                skill-less agent.
            commit_sha: The published revision of that skill, or ``None`` for
                the default agent.
            skill_dir: Directory ADK loads the skill from; only read when the
                agent is not already cached.
            tenant_id: Id of the tenant the agent is being resolved for. Part
                of the cache partition — each tenant gets its own capped
                cache — and folded into the ADK app_name via
                :func:`tenant_app_name` so two tenants never share an ADK
                session store namespace even when the underlying database is
                shared.
            kind: Role of the skill-backed agent (see :class:`AgentKind`);
                part of the cache key because each kind bakes a different
                instruction and toolset into its agent.

        Returns:
            The cached (or freshly built) agent for that tenant, revision, and kind.
        """
        key = (agent_skill_id, commit_sha, kind)
        tenant_cache = self._cache.setdefault(tenant_id, OrderedDict())
        cached = tenant_cache.get(key)
        if cached is not None:
            tenant_cache.move_to_end(key)
            return cached
        agent = ADKAgent.from_app(
            create_app(
                tenant_app_name(self._app_name, tenant_id),
                skill_dir=skill_dir,
                kind=kind,
            ),
            user_id_extractor=extract_user_id,
            session_service=self._session_service,
            use_thread_id_as_session_id=True,
            emit_messages_snapshot=True,
            session_timeout_seconds=None,
        )
        tenant_cache[key] = agent
        if len(tenant_cache) > _AGENT_CACHE_MAX_ENTRIES:
            tenant_cache.popitem(last=False)
        return agent
