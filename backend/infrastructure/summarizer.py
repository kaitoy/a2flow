"""Rendering and one-shot LLM summarization of a workflow's design conversation.

Used by the workflow generation job and by ``POST
/workflows/{id}/generate-prompt`` to distill a design session's
transcript into the workflow's ``generated_prompt``, which is later handed
to the execution agent as context. :func:`build_design_transcript` turns the
ADK session's raw events into that transcript;
:func:`summarize_design_transcript` summarizes it into the prompt, and
:func:`describe_design_transcript` into the short description shown to the
people who run the workflow (generation job only). Both reuse the

application's model selection (``config.Settings.llm_model`` via
:func:`infrastructure.agent.resolve_model`) so the summarizer always runs on
the same LLM as the agents.
"""

import logging

from ag_ui_adk import adk_events_to_messages
from google.adk.events import Event
from google.adk.models.base_llm import BaseLlm
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.registry import LLMRegistry
from google.genai import types

from infrastructure.agent import resolve_model

logger = logging.getLogger(__name__)


def build_design_transcript(events: list[Event]) -> str:
    """Render a design session's ADK events as a plain-text transcript.

    Keeps only plain-text ``user`` and ``assistant`` turns (tool calls and
    their results are noise for summarization) and prefixes each line with its
    speaker.

    Args:
        events: The ADK session's events, oldest first.

    Returns:
        The transcript, one ``Speaker: text`` paragraph per message.
    """
    lines: list[str] = []
    for message in adk_events_to_messages(events):
        data = message.model_dump(mode="json", by_alias=True)
        role = data.get("role")
        content = data.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        text = content.strip()
        if text:
            lines.append(f"{role.capitalize()}: {text}")
    return "\n\n".join(lines)


#: Hard cap on the transcript text handed to the LLM, so an arbitrarily long
#: design conversation cannot blow the request up; the head carries the
#: original request and the registered task templates, which is what the summary needs.
_TRANSCRIPT_MAX_CHARS = 24_000

_SUMMARY_PROMPT = (
    "Summarize the following workflow-design conversation into a concise "
    "description of the workflow it produced: what the workflow does, the "
    "inputs or context it needs, and its main steps. Write plain "
    "prose (no headings, no lists), in the language the conversation was held "
    "in, and keep it under 1500 characters.\n\n"
    "Conversation:\n{transcript}"
)

_DESCRIPTION_PROMPT = (
    "Read the following workflow-design conversation and write a short "
    "description of the workflow it produced, for the people who will run it. "
    "Say what the workflow does for them and, if they need to have something "
    "ready, what that is. Do not describe internal steps, tools, systems, "
    "credentials, or how the work is carried out. Write one to three plain "
    "sentences (no headings, no lists), in the language the conversation was "
    "held in, and keep it under 300 characters.\n\n"
    "Conversation:\n{transcript}"
)


def build_llm() -> BaseLlm:
    """Instantiate a :class:`BaseLlm` for one-shot calls from the configured model.

    :func:`resolve_model` already yields a :class:`LiteLlm` instance for
    ``litellm:``-prefixed selections; bare model names (e.g. Gemini) are turned
    into an instance via :meth:`LLMRegistry.new_llm`.
    """
    model = resolve_model()
    if isinstance(model, LiteLlm):
        return model
    return LLMRegistry.new_llm(model)


async def summarize_design_transcript(
    transcript: str, *, max_chars: int = 10000
) -> str:
    """Summarize a design-session transcript into a workflow prompt.

    Sends a single user turn to the configured LLM and concatenates the text
    parts of its response. The transcript is truncated to
    :data:`_TRANSCRIPT_MAX_CHARS` before sending, and the result is hard-cut to
    ``max_chars`` so it always fits the ``WorkflowPromptText`` column constraint.

    Args:
        transcript: The design conversation as plain text (one line per
            message, speaker-prefixed).
        max_chars: Upper bound on the returned summary length; defaults to the
            ``WorkflowPromptText`` maximum.

    Returns:
        The summary text.

    Raises:
        ValueError: If the LLM returned no usable text.
        Exception: Whatever the underlying LLM client raises on failure —
            callers decide the fallback (the generation job falls back to the
            transcript head; the on-demand endpoint surfaces HTTP 502).
    """
    summary = await _complete(_SUMMARY_PROMPT, transcript)
    return summary[:max_chars].rstrip()


async def describe_design_transcript(transcript: str, *, max_chars: int = 2000) -> str:
    """Write a short, requester-facing description from a design transcript.

    Unlike :func:`summarize_design_transcript`, whose output is the prompt a
    run is told, this is meant for everyone who may run the workflow: a few
    sentences on what it does for them, leaving out the internal steps,
    tools, and systems that only the prompt's readers may see.

    Args:
        transcript: The design conversation as plain text (one line per
            message, speaker-prefixed).
        max_chars: Upper bound on the returned text; defaults to the
            ``DescText`` maximum of a workflow's ``description``.

    Returns:
        The description text.

    Raises:
        ValueError: If the LLM returned no usable text.
        Exception: Whatever the underlying LLM client raises on failure.
    """
    description = await _complete(_DESCRIPTION_PROMPT, transcript)
    return description[:max_chars].rstrip()


async def _complete(template: str, transcript: str) -> str:
    """Send one prompt built from ``template`` and return the reply text.

    The transcript is truncated to :data:`_TRANSCRIPT_MAX_CHARS` before it is
    substituted into ``template``'s ``{transcript}`` placeholder.

    Args:
        template: The instruction, with a ``{transcript}`` placeholder.
        transcript: The design conversation as plain text.

    Returns:
        The reply's concatenated text parts, stripped.

    Raises:
        ValueError: If the LLM returned no usable text.
    """
    llm = build_llm()
    prompt = template.format(transcript=transcript[:_TRANSCRIPT_MAX_CHARS])
    request = LlmRequest(
        model=getattr(llm, "model", None),
        contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
    )
    chunks: list[str] = []
    async for response in llm.generate_content_async(request, stream=False):
        content = response.content
        if content is None or not content.parts:
            continue
        for part in content.parts:
            if part.text:
                chunks.append(part.text)
    text = "".join(chunks).strip()
    if not text:
        raise ValueError("LLM returned an empty summary")
    return text
