import os
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models.lite_llm import LiteLlm
from a2ui.adk.send_a2ui_to_client_toolset import SendA2uiToClientToolset
from a2ui.basic_catalog import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from a2ui.schema.constants import VERSION_0_9

LITELLM_PREFIX = "litellm:"

_EXAMPLES_PATH = os.path.join(os.path.dirname(__file__), "a2ui", "examples", "*.json")

_schema_manager = A2uiSchemaManager(
    version=VERSION_0_9,
    catalogs=[BasicCatalog.get_config(VERSION_0_9)],
)
_allowed_components=["Text", "Card", "Button", "Modal", "Row", "Column", "List", "TextField", "ChoicePicker"]
_a2ui_catalog = _schema_manager.get_selected_catalog(
    allowed_components=_allowed_components,
)
_a2ui_examples = _a2ui_catalog.load_examples(_EXAMPLES_PATH)


def _a2ui_examples_provider(_: ReadonlyContext) -> str:
    return _a2ui_examples


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
    instruction = _schema_manager.generate_system_prompt(
        role_description=role_description,
        workflow_description=(
            "Use send_a2ui_json_to_client tool to show structured UI when appropriate. "
            "If the tool returns an error, read the validation error carefully, fix the JSON, and call the tool again silently without generating any text message to the user. "
            "IMPORTANT: When building the a2ui_json argument, all string values in the JSON must use escape sequences for special characters. "
            "Newlines must be written as \\n (backslash + n), NOT as literal line breaks. "
            "For example: \"text\": \"line1\\nline2\" is correct; a string with an actual newline character is invalid JSON and will cause a parse error."
        ),
        ui_description=(
            "Use Card to frame key information or forms. "
            "Use Row/Column for layout. "
            "Use Text for displaying explanations or results in Markdown format. "
            "Use TextField and ChoicePicker for user input. "
            "Use Button for actions. "
            "Use Modal for confirmations or supplemental details."
        ),
        include_schema=False,   # Injected per-request by SendA2uiToClientToolset.process_llm_request;
        include_examples=False, # including here causes ADK template substitution to raise KeyError on {expression}.
        allowed_components=_allowed_components,
    )

    if model_env.startswith(LITELLM_PREFIX):
        model_name = model_env[len(LITELLM_PREFIX):]
        model = LiteLlm(model=model_name)
    else:
        model = model_env

    a2ui_toolset = SendA2uiToClientToolset(
        a2ui_enabled=True,
        a2ui_catalog=_a2ui_catalog,
        a2ui_examples=_a2ui_examples_provider,
    )

    return LlmAgent(
        name="simple_agent",
        model=model,
        instruction=instruction,
        tools=[a2ui_toolset],
    )
