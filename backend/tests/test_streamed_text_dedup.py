"""Tests for :mod:`infrastructure.streamed_text_dedup`."""

from collections.abc import AsyncGenerator

from ag_ui.core import (
    BaseEvent,
    EventType,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallStartEvent,
)

from infrastructure.streamed_text_dedup import drop_restreamed_text


def _message(message_id: str, *chunks: str) -> list[BaseEvent]:
    """Build the START / CONTENT... / END events of one text message."""
    return [
        TextMessageStartEvent(message_id=message_id, role="assistant"),
        *(TextMessageContentEvent(message_id=message_id, delta=c) for c in chunks),
        TextMessageEndEvent(message_id=message_id),
    ]


def _tool_call(call_id: str) -> BaseEvent:
    return ToolCallStartEvent(tool_call_id=call_id, tool_call_name="render_a2ui")


async def _source(events: list[BaseEvent]) -> AsyncGenerator[BaseEvent, None]:
    for event in events:
        yield event


async def _run(events: list[BaseEvent]) -> list[BaseEvent]:
    return [e async for e in drop_restreamed_text(_source(events))]


async def test_drops_consolidated_copy_of_streamed_reply() -> None:
    """The shape ag-ui-adk emits for a LiteLLM reply that ends in a tool call."""
    events = [
        *_message("m1", "Hello, ", "world."),
        *_message("m2", "Hello, world."),
        _tool_call("c1"),
    ]

    assert await _run(events) == [*_message("m1", "Hello, ", "world."), events[-1]]


async def test_keeps_distinct_and_separated_messages() -> None:
    """Only a repeat directly after the original is dropped."""
    events = [
        *_message("m1", "Same."),
        *_message("m2", "Different."),
        *_message("m3", "Different!"),
        _tool_call("c1"),
        *_message("m4", "Different!"),
        *_message("m5"),
    ]

    assert await _run(events) == events


async def test_closes_source_when_closed_early() -> None:
    closed = False

    async def source() -> AsyncGenerator[BaseEvent, None]:
        nonlocal closed
        try:
            for event in _message("m1", "a", "b"):
                yield event
        finally:
            closed = True

    stream = drop_restreamed_text(source())
    first = await anext(stream)
    await stream.aclose()

    assert first.type == EventType.TEXT_MESSAGE_START
    assert closed
