"""Run the backend with a scripted LLM, for the browser end-to-end suite in ``e2e/``.

Usage (from ``backend/``, with ``LLM_MODEL=e2e-fake``)::

    uv run python -m scripts.e2e_server

The suite plays the demo AWS EC2 launch through with tool mocks, so it needs an
agent that behaves the same on every run and costs nothing. :class:`E2eFakeLlm`
is that agent. It is registered with ADK's :class:`LLMRegistry` under the name
``e2e-fake`` before the app is imported, and :func:`infrastructure.agent.resolve_model`
hands any name without the ``litellm:`` prefix to that registry, so every agent
and the summarizer reach it without a line of production code knowing it exists.

The script is stateless: each call reads which agent is asking from the tools
it was given, and how far it has got from the function responses already in
the request.
"""

from collections.abc import AsyncGenerator
from typing import Any

import uvicorn
from google.adk.models import BaseLlm, LLMRegistry
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from infrastructure.demo_data import DEMO_APPROVERS_GROUP_ID, DEMO_MCP_SERVER_ID

#: Title of the first task template, which asks for approval.
APPROVE_TITLE = "Request approval"
#: Title of the second task template, which launches the instance.
LAUNCH_TITLE = "Launch instance"
#: The execution agent's closing message; the e2e suite waits for it.
FINAL_TEXT = "Launched the EC2 instance."
#: The tool the launch task is bound to; the demo data mocks it.
LAUNCH_TOOL = "aws___call_aws"
#: The command passed to the mocked tool. It never reaches AWS.
LAUNCH_COMMAND = "aws ec2 run-instances --image-id ami-e2e --instance-type t4g.nano"

_TASK_TEMPLATES = [
    {"key": "approve", "title": APPROVE_TITLE},
    {
        "key": "launch",
        "title": LAUNCH_TITLE,
        "depends_on": ["approve"],
        "tools": [{"server_id": DEMO_MCP_SERVER_ID, "tool_name": LAUNCH_TOOL}],
    },
]


def _call(name: str, args: dict[str, Any]) -> types.Part:
    """Build a function-call part."""
    return types.Part(function_call=types.FunctionCall(name=name, args=args))


def _text(text: str) -> types.Part:
    """Build a text part, which ends the agent's turn."""
    return types.Part(text=text)


def _responses(llm_request: LlmRequest) -> list[tuple[str, dict[str, Any]]]:
    """Return every function response in the request as ``(name, response)``, oldest first."""
    return [
        (part.function_response.name or "", part.function_response.response or {})
        for content in llm_request.contents
        for part in content.parts or []
        if part.function_response is not None
    ]


def _design_step(responses: list[tuple[str, dict[str, Any]]]) -> types.Part:
    """Register the two task templates once, then finish the design turn."""
    if not any(name == "register_task_templates" for name, _ in responses):
        return _call("register_task_templates", {"tasks": _TASK_TEMPLATES})
    return _text("Registered the task templates.")


def _execution_step(responses: list[tuple[str, dict[str, Any]]]) -> types.Part:
    """Work both tasks through to ``completed``, one tool call per model call.

    The first call lists the tasks to learn their ids. Every later call counts
    the responses received since then to find its place in the script, and
    stops with a text reply naming the failure if a tool answered with an error.
    """
    names = [name for name, _ in responses]
    if "list_workflow_tasks" not in names:
        return _call("list_workflow_tasks", {})
    start = names.index("list_workflow_tasks")
    for name, response in responses[start:]:
        if "error" in response:
            return _text(f"E2E fake LLM stopped: {name} returned {response}")

    ids = {task["title"]: task["id"] for task in responses[start][1]["tasks"]}
    approve, launch = ids[APPROVE_TITLE], ids[LAUNCH_TITLE]
    script = [
        _call("update_workflow_task", {"task_id": approve, "status": "in_progress"}),
        _call(
            "request_approval",
            {
                "title": "Launch an EC2 instance",
                "workflow_task_id": approve,
                "approver_group_id": DEMO_APPROVERS_GROUP_ID,
                "approved_calls": [
                    {
                        "mcp_server_id": DEMO_MCP_SERVER_ID,
                        "tool_name": LAUNCH_TOOL,
                        "arguments": {},
                    }
                ],
            },
        ),
        _call("update_workflow_task", {"task_id": approve, "status": "completed"}),
        _call("update_workflow_task", {"task_id": launch, "status": "in_progress"}),
        _call(
            "call_mcp_tool",
            {
                "server_id": DEMO_MCP_SERVER_ID,
                "tool_name": LAUNCH_TOOL,
                "arguments": {"cli_command": LAUNCH_COMMAND},
            },
        ),
        _call("update_workflow_task", {"task_id": launch, "status": "completed"}),
    ]
    done = len(responses) - start - 1
    return script[done] if done < len(script) else _text(FINAL_TEXT)


class E2eFakeLlm(BaseLlm):
    """A scripted model that answers the design agent, the execution agent, and the summarizer."""

    @classmethod
    def supported_models(cls) -> list[str]:
        """Return the model-name patterns this class serves: just ``e2e-fake``."""
        return [r"e2e-fake"]

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """Yield the next scripted step for whichever agent is asking.

        Args:
            llm_request: The request ADK built; its tools tell the agents apart.
            stream: Ignored; the whole response is always yielded at once.

        Yields:
            A single model response holding one function call or one text part.
        """
        tools = llm_request.tools_dict
        responses = _responses(llm_request)
        if "register_task_templates" in tools:
            part = _design_step(responses)
        elif "update_workflow_task" in tools:
            part = _execution_step(responses)
        else:
            part = _text("Request approval, then launch an EC2 instance.")
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


def main() -> None:
    """Register :class:`E2eFakeLlm` and serve the app on 127.0.0.1:8099."""
    LLMRegistry.register(E2eFakeLlm)
    uvicorn.run("main:app", host="127.0.0.1", port=8099)


if __name__ == "__main__":
    main()
