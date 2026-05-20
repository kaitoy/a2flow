import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ag_ui_adk import CONTEXT_STATE_KEY, ADKAgent, AGUIToolset
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import BaseSessionService
from google.adk.skills import load_skill_from_dir
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.skill_toolset import SkillToolset

ToolUnion = Callable[..., Any] | BaseTool | BaseToolset

LITELLM_PREFIX = "litellm:"

AGENT_SKILL_ID_KEY = "agent_skill_id"
SKILL_DIR_KEY = "skill_dir"

WORKFLOW_AGENT_INSTRUCTION = (
    "You are an assistant that uses the provided skill to fulfill the user's request. "
    "Follow the skill's instructions to produce a clear, actionable task list that breaks "
    "the request into concrete steps."
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
    exposed to the agent via SkillToolset alongside the A2UI tools.
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
                user_id_extractor=lambda input: input.forwarded_props.get(
                    "userId", "user"
                ),
                session_service=self._session_service,
                use_thread_id_as_session_id=True,
                emit_messages_snapshot=True,
            )
        return self._cache[agent_skill_id]
