"""Drops the second copy of an assistant reply that ag-ui-adk sends twice.

Why this exists: under ``StreamingMode.SSE`` ADK yields a reply as
``partial=True`` chunks and then once more as a consolidated
``partial=False`` event carrying the whole text. ag-ui-adk's
``EventTranslator._translate_text_content`` is meant to drop that
consolidated copy, but misses it when both of these hold -- which they do for
LiteLLM-backed models whenever the reply ends in a tool call (``render_a2ui``,
for instance):

- the last chunk carries a ``finish_reason``, so the translator already closed
  the streamed message (``TEXT_MESSAGE_END``) before the consolidated event
  arrives, and its "skip consolidated text during an active stream" check no
  longer applies;
- the consolidated event also holds the function call, so ADK's
  ``Event.is_final_response()`` is ``False`` and the translator never reaches
  its other check, the comparison against the text it just streamed.

The consolidated text then goes out as a second ``TEXT_MESSAGE_START`` /
``CONTENT`` / ``END`` with a new message id, and a live chat shows the reply
twice. The persisted session holds it once, so reloading the page "fixes" it.
Seen with ag-ui-adk 0.11.0 through 0.13.0.

:func:`drop_restreamed_text` filters an ``ADKAgent.run()`` event stream: a
text message that directly follows a finished one and whose first content
chunk is that message's entire text is dropped. Only the ``START`` of each
message is held back, until its first chunk, so a normal stream is delayed by
one chunk at most. Remove this filter (and its call sites) once ag-ui-adk
applies its duplicate check to non-final consolidated events too.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import aclosing

from ag_ui.core import (
    BaseEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)

logger = logging.getLogger(__name__)


async def drop_restreamed_text(
    events: AsyncGenerator[BaseEvent, None],
) -> AsyncGenerator[BaseEvent, None]:
    """Yield ``events`` without ag-ui-adk's repeated copy of a streamed reply.

    A text message is treated as the repeat when its ``TEXT_MESSAGE_START``
    comes right after the previous message's ``TEXT_MESSAGE_END``, with no
    other event between them, and its first ``TEXT_MESSAGE_CONTENT`` equals
    the previous message's full text. Its start, content, and end events are
    then all dropped. Everything else passes through in order.

    The source generator is closed when this one is, so a client that
    disconnects mid-run still runs ag-ui-adk's own cleanup.

    Args:
        events: The event stream of one ``ADKAgent.run()`` call.

    Yields:
        The same events, minus the repeated message.
    """
    # Text of the message whose END was the event just before, or None once
    # anything else has come in between.
    last_text: str | None = None
    # Accumulated text of each open message, by message id.
    open_text: dict[str, str] = {}
    # A START held back until its first chunk shows whether it is a repeat,
    # with the previous message's text it is to be compared against.
    held: tuple[TextMessageStartEvent, str | None] | None = None
    dropped: set[str] = set()

    async with aclosing(events) as stream:
        async for event in stream:
            if isinstance(event, TextMessageContentEvent | TextMessageEndEvent) and (
                event.message_id in dropped
            ):
                if isinstance(event, TextMessageEndEvent):
                    dropped.discard(event.message_id)
                continue

            if isinstance(event, TextMessageStartEvent):
                if held is not None:
                    yield held[0]
                held = (event, last_text)
                last_text = None
                open_text[event.message_id] = ""
                continue

            if held is not None:
                start, against = held
                held = None
                if (
                    isinstance(event, TextMessageContentEvent)
                    and event.message_id == start.message_id
                    and against
                    and event.delta == against
                ):
                    logger.info(
                        "Dropping text message %s: it repeats the reply just streamed",
                        event.message_id,
                    )
                    open_text.pop(event.message_id, None)
                    dropped.add(event.message_id)
                    continue
                # Any other event -- the first chunk of a new reply, an END
                # with no content, or something unrelated -- releases the START.
                yield start

            if isinstance(event, TextMessageContentEvent):
                open_text[event.message_id] = (
                    open_text.get(event.message_id, "") + event.delta
                )
                last_text = None
            elif isinstance(event, TextMessageEndEvent):
                last_text = open_text.pop(event.message_id, "")
            else:
                last_text = None
            yield event

        if held is not None:
            yield held[0]
