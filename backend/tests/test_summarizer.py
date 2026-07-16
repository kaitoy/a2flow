"""Tests for the one-shot planning-transcript summarizer."""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from google.genai import types

from infrastructure import summarizer
from infrastructure.summarizer import (
    _TRANSCRIPT_MAX_CHARS,
    build_llm,
    summarize_planning_transcript,
)


class _FakeLlm:
    """Minimal ``BaseLlm`` stand-in capturing the request and yielding responses."""

    def __init__(self, texts: list[str | None]) -> None:
        self.texts = texts
        self.requests: list[Any] = []
        self.model = "fake-model"

    async def generate_content_async(
        self, llm_request: Any, stream: bool = False
    ) -> AsyncGenerator[Any, None]:
        self.requests.append(llm_request)
        for text in self.texts:
            content = (
                types.Content(role="model", parts=[types.Part(text=text)])
                if text is not None
                else None
            )
            yield type("Resp", (), {"content": content})()


async def test_summarize_concatenates_text_parts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FakeLlm(["A workflow that ", "does the thing."])
    monkeypatch.setattr(summarizer, "build_llm", lambda: llm)

    result = await summarize_planning_transcript("User: do the thing")

    assert result == "A workflow that does the thing."
    prompt = llm.requests[0].contents[0].parts[0].text
    assert "User: do the thing" in prompt


async def test_summarize_truncates_to_max_chars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FakeLlm(["x" * 5000])
    monkeypatch.setattr(summarizer, "build_llm", lambda: llm)

    result = await summarize_planning_transcript("t", max_chars=100)

    assert len(result) == 100


async def test_summarize_caps_the_transcript_it_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FakeLlm(["ok"])
    monkeypatch.setattr(summarizer, "build_llm", lambda: llm)

    await summarize_planning_transcript("y" * (_TRANSCRIPT_MAX_CHARS + 10_000))

    prompt = llm.requests[0].contents[0].parts[0].text
    assert len(prompt) < _TRANSCRIPT_MAX_CHARS + 1_000


async def test_summarize_raises_on_empty_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FakeLlm([None])
    monkeypatch.setattr(summarizer, "build_llm", lambda: llm)

    with pytest.raises(ValueError):
        await summarize_planning_transcript("t")


def test_build_llm_uses_litellm_for_prefixed_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ``litellm:`` prefix selects LiteLlm with the prefix stripped."""
    from google.adk.models.lite_llm import LiteLlm

    monkeypatch.setenv("LLM_MODEL", "litellm:openai/gpt-4o")
    from config import get_settings

    get_settings.cache_clear()
    llm = build_llm()
    assert isinstance(llm, LiteLlm)
    assert llm.model == "openai/gpt-4o"


def test_build_llm_uses_registry_for_bare_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODEL", "gemini-2.5-flash")
    from config import get_settings

    get_settings.cache_clear()
    llm = build_llm()
    assert llm.model == "gemini-2.5-flash"
