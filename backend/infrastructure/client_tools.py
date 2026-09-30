"""The client tools and A2UI context the server attaches to the runs it drives.

A turn the browser starts arrives already carrying ``render_approval``,
``render_a2ui``, and the two A2UI context entries (the component catalog and
the ``render_a2ui`` usage guide): the frontend declares the first and its A2UI
middleware injects the rest. A turn the server starts itself -- a run's
kickoff, or its resumption once an approval is decided -- has no browser to add
them, yet must offer the model exactly the same, or the agent renders surfaces
the frontend cannot draw.

So they are read from ``client_contract.json``, which the frontend's
``src/lib/clientContract.test.ts`` generates from the request body a real agent
sends and fails on whenever the two drift apart.
"""

import json
from functools import lru_cache
from pathlib import Path

from ag_ui.core import Context, Tool

#: Name of the client tool that shows approve/reject controls for an approval.
RENDER_APPROVAL_TOOL_NAME = "render_approval"

#: Name of the client tool that draws an A2UI surface.
RENDER_A2UI_TOOL_NAME = "render_a2ui"

#: Every tool the browser executes: a call to one pauses the turn until a
#: person answers it.
CLIENT_TOOL_NAMES = frozenset({RENDER_APPROVAL_TOOL_NAME, RENDER_A2UI_TOOL_NAME})

_CONTRACT_PATH = Path(__file__).with_name("client_contract.json")


@lru_cache(maxsize=1)
def _contract() -> dict[str, list[dict[str, object]]]:
    """Read the committed contract once per process."""
    loaded: dict[str, list[dict[str, object]]] = json.loads(
        _CONTRACT_PATH.read_text(encoding="utf-8")
    )
    return loaded


def client_tools() -> list[Tool]:
    """Return the client tool definitions the browser declares on every run."""
    return [Tool.model_validate(tool) for tool in _contract()["tools"]]


def a2ui_context() -> list[Context]:
    """Return the A2UI context entries the browser's middleware injects on every run."""
    return [Context.model_validate(entry) for entry in _contract()["context"]]
