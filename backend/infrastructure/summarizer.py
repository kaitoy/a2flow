"""One-shot LLM summarization of a workflow's planning conversation.

Used by the workflow generation job and the publish use case to distill a
planning session's transcript into the workflow's ``description``, which is
later handed to the execution agent as context. Reuses the application's model
selection (``config.Settings.llm_model`` via
:func:`infrastructure.agent.resolve_model`) so the summarizer always runs on
the same LLM as the agents.
"""

import logging

from google.adk.models.base_llm import BaseLlm
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.registry import LLMRegistry
from google.genai import types

from infrastructure.agent import resolve_model

logger = logging.getLogger(__name__)

#: Hard cap on the transcript text handed to the LLM, so an arbitrarily long
#: planning conversation cannot blow the request up; the head carries the
#: original request and the registered plan, which is what the summary needs.
_TRANSCRIPT_MAX_CHARS = 24_000

_SUMMARY_PROMPT = (
    "Summarize the following workflow-planning conversation into a concise "
    "description of the workflow it produced: what the workflow does, the "
    "inputs or context it needs, and the main steps of its plan. Write plain "
    "prose (no headings, no lists), in the language the conversation was held "
    "in, and keep it under 1500 characters.\n\n"
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


async def summarize_planning_transcript(
    transcript: str, *, max_chars: int = 2000
) -> str:
    """Summarize a planning-session transcript into a workflow description.

    Sends a single user turn to the configured LLM and concatenates the text
    parts of its response. The transcript is truncated to
    :data:`_TRANSCRIPT_MAX_CHARS` before sending, and the result is hard-cut to
    ``max_chars`` so it always fits the ``DescText`` column constraint.

    Args:
        transcript: The planning conversation as plain text (one line per
            message, speaker-prefixed).
        max_chars: Upper bound on the returned summary length; defaults to the
            ``DescText`` maximum.

    Returns:
        The summary text.

    Raises:
        ValueError: If the LLM returned no usable text.
        Exception: Whatever the underlying LLM client raises on failure —
            callers decide the fallback (the generation job records the error,
            publish keeps the previous description).
    """
    llm = build_llm()
    prompt = _SUMMARY_PROMPT.format(transcript=transcript[:_TRANSCRIPT_MAX_CHARS])
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
    summary = "".join(chunks).strip()
    if not summary:
        raise ValueError("LLM returned an empty summary")
    return summary[:max_chars].rstrip()
