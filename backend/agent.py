import os
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.lite_llm import LiteLlm
from ag_ui_adk import AGUIToolset, CONTEXT_STATE_KEY

LITELLM_PREFIX = "litellm:"


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
        parts = [self._base, a2ui_rules]
        if context_entries:
            context_text = "\n\n".join(
                f"# {entry['description']}\n{entry['value']}"
                for entry in context_entries
            )
            parts.append(context_text)
        instruction = "\n\n".join(parts)
        print(instruction)
        return instruction


def create_agent() -> LlmAgent:
    """
    Create an agent based on LLM_MODEL in .env.

    - Gemini model name (e.g. "gemini-*"): uses Google AI / Vertex AI directly
    - "litellm:<provider>/<model>" format: uses any LLM via LiteLLM
      e.g. litellm:openai/gpt-4o
           litellm:anthropic/claude-3-5-sonnet-20241022
    """
    model_env = os.getenv("LLM_MODEL", "gemini-2.0-flash")
    role_description = os.getenv("ROLE_DESCRIPTION", "You are a helpful assistant.")

    if model_env.startswith(LITELLM_PREFIX):
        model_name = model_env[len(LITELLM_PREFIX):]
        model = LiteLlm(model=model_name)
    else:
        model = model_env

    return LlmAgent(
        name="simple_agent",
        model=model,
        instruction=A2UIInstructionProvider(role_description),
        tools=[AGUIToolset()],
    )
