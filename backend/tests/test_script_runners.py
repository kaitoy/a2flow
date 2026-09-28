"""End-to-end tests for the script runners in ``infrastructure.script_runners``.

Each test launches a real runner as a child process through the same
connection resolution and stdio client the app uses, so what is checked is
what an agent would see: the tools a script advertises and what calling one
returns. The JavaScript cases skip when ``node`` is not on ``PATH``, and the
package cases when the package registries cannot be reached.
"""

import os
import shutil
import socket
from typing import Any

import pytest

from infrastructure.mcp_client import call_server_tool, list_server_tools
from infrastructure.mcp_connection import resolve_connection
from infrastructure.secret_resolver import SecretResolver
from models.mcp_server import MCPServer, McpTransport, ScriptLanguage
from repositories.exceptions import McpConnectionError


class _PassThroughResolver:
    """Stand-in for ``SecretResolver`` that returns env values unchanged."""

    async def resolve_mapping(self, values: dict[str, str]) -> dict[str, str]:
        return dict(values)


_PYTHON_SOURCE = '''
import json
from os.path import join

print("printed at import time")


def add(a: int, b: int) -> int:
    """Add two integers."""
    print("printed inside a tool")
    return a + b


async def greet(name: str) -> str:
    """Greet someone."""
    return "hello " + name


def fail() -> None:
    raise RuntimeError("boom")


def _helper() -> None:
    pass
'''

_JS_SOURCE = """
import { basename } from "node:path";

console.log("printed at import time");

export function add({ a, b }) {
  console.log("printed inside a tool");
  return a + b;
}
add.description = "Add two numbers.";
add.inputSchema = {
  type: "object",
  properties: { a: { type: "number" }, b: { type: "number" } },
  required: ["a", "b"],
};

export async function greet({ name }) {
  return "hello " + basename("/users/" + name);
}

export function fail() {
  throw new Error("boom");
}

export function _helper() {}
export default function ignored() {}
export const notAFunction = 1;
"""


async def _connection(
    language: ScriptLanguage, source: str, packages: list[str] | None = None
) -> Any:
    # uv and npm run with only the server's env; hand them this machine's
    # certificate setting so a TLS-intercepting proxy does not break installs.
    env = {k: v for k, v in os.environ.items() if k == "UV_SYSTEM_CERTS"}
    server = MCPServer(
        id="srv-1",
        name="script",
        tenant_id="t-1",
        created_by="u-1",
        updated_by="u-1",
        transport=McpTransport.script,
        language=language,
        source=source,
        packages=packages or [],
        env=env,
    )
    resolver: SecretResolver = _PassThroughResolver()  # type: ignore[assignment]
    return await resolve_connection(server, resolver)


def _text(result: Any) -> str:
    return "".join(block.text for block in result.content)


_needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not found")


def _reachable(host: str) -> bool:
    try:
        socket.create_connection((host, 443), timeout=3).close()
    except OSError:
        return False
    return True


_needs_pypi = pytest.mark.skipif(not _reachable("pypi.org"), reason="PyPI unreachable")
_needs_npm = pytest.mark.skipif(
    shutil.which("node") is None or not _reachable("registry.npmjs.org"),
    reason="node or the npm registry unavailable",
)


async def test_python_runner_exposes_public_top_level_functions() -> None:
    connection = await _connection(ScriptLanguage.python, _PYTHON_SOURCE)
    tools = {tool.name: tool for tool in await list_server_tools(connection)}

    assert set(tools) == {"add", "greet", "fail"}
    assert tools["add"].description == "Add two integers."
    assert tools["add"].inputSchema["properties"]["a"]["type"] == "integer"
    assert tools["add"].inputSchema["required"] == ["a", "b"]


async def test_python_runner_calls_a_tool_despite_prints() -> None:
    connection = await _connection(ScriptLanguage.python, _PYTHON_SOURCE)

    added = await call_server_tool(connection, "add", {"a": 2, "b": 3})
    greeted = await call_server_tool(connection, "greet", {"name": "ada"})

    assert not added.isError
    assert _text(added) == "5"
    assert _text(greeted) == "hello ada"


async def test_python_runner_reports_an_exception_as_a_tool_error() -> None:
    connection = await _connection(ScriptLanguage.python, _PYTHON_SOURCE)
    result = await call_server_tool(connection, "fail", {})
    assert result.isError
    assert "boom" in _text(result)


@_needs_node
async def test_node_runner_exposes_public_exported_functions() -> None:
    connection = await _connection(ScriptLanguage.javascript, _JS_SOURCE)
    tools = {tool.name: tool for tool in await list_server_tools(connection)}

    assert set(tools) == {"add", "greet", "fail"}
    assert tools["add"].description == "Add two numbers."
    assert tools["add"].inputSchema["required"] == ["a", "b"]
    assert tools["greet"].description is None
    assert tools["greet"].inputSchema == {"type": "object"}


@_needs_node
async def test_node_runner_calls_a_tool_despite_console_log() -> None:
    connection = await _connection(ScriptLanguage.javascript, _JS_SOURCE)

    added = await call_server_tool(connection, "add", {"a": 2, "b": 3})
    greeted = await call_server_tool(connection, "greet", {"name": "ada"})

    assert not added.isError
    assert _text(added) == "5"
    assert _text(greeted) == "hello ada"


@_needs_node
async def test_node_runner_reports_an_exception_as_a_tool_error() -> None:
    connection = await _connection(ScriptLanguage.javascript, _JS_SOURCE)
    result = await call_server_tool(connection, "fail", {})
    assert result.isError
    assert _text(result) == "boom"


@pytest.mark.parametrize(
    ("language", "source", "expected"),
    [
        pytest.param(ScriptLanguage.python, "def broken(:\n", "SyntaxError", id="py"),
        pytest.param(
            ScriptLanguage.python,
            "raise ValueError('bad top')\n",
            "bad top",
            id="py-raise",
        ),
        pytest.param(
            ScriptLanguage.javascript,
            "export function broken( {\n",
            "SyntaxError",
            id="js",
            marks=_needs_node,
        ),
        pytest.param(
            ScriptLanguage.javascript,
            "throw new Error('bad top');\n",
            "bad top",
            id="js-raise",
            marks=_needs_node,
        ),
    ],
)
async def test_runner_reports_a_load_failure_over_the_protocol(
    language: ScriptLanguage, source: str, expected: str
) -> None:
    connection = await _connection(language, source)

    with pytest.raises(McpConnectionError) as caught:
        await list_server_tools(connection)
    called = await call_server_tool(connection, "anything", {})

    assert expected in caught.value.reason
    assert "script_runners" not in caught.value.reason
    assert "base64" not in caught.value.reason
    assert called.isError
    assert expected in _text(called)


_PYTHON_PACKAGE_SOURCE = '''
import humanize


def size(n: int) -> str:
    """Format a byte count."""
    return humanize.naturalsize(n)
'''

_JS_PACKAGE_SOURCE = """
import isNumber from "is-number";

export function check({ value }) {
  return isNumber(value);
}
"""


@_needs_pypi
async def test_python_runner_imports_a_declared_package() -> None:
    connection = await _connection(
        ScriptLanguage.python, _PYTHON_PACKAGE_SOURCE, ["humanize"]
    )

    result = await call_server_tool(connection, "size", {"n": 3000})

    assert not result.isError
    assert _text(result) == "3.0 kB"


@_needs_npm
async def test_node_runner_imports_a_declared_package() -> None:
    connection = await _connection(
        ScriptLanguage.javascript, _JS_PACKAGE_SOURCE, ["is-number@7"]
    )

    result = await call_server_tool(connection, "check", {"value": "42"})

    assert not result.isError
    assert _text(result) == "true"


@_needs_npm
async def test_node_runner_reports_a_failed_install_over_the_protocol() -> None:
    connection = await _connection(
        ScriptLanguage.javascript,
        "export function f() { return 1; }\n",
        ["a2flow-no-such-package-xyz"],
    )

    with pytest.raises(McpConnectionError) as caught:
        await list_server_tools(connection)

    assert "npm install failed" in caught.value.reason
    assert "script_runners" not in caught.value.reason


@_needs_pypi
async def test_python_runner_reports_a_failed_install_over_the_protocol() -> None:
    connection = await _connection(
        ScriptLanguage.python,
        "def f() -> int:\n    return 1\n",
        ["a2flow-no-such-package-xyz"],
    )

    with pytest.raises(McpConnectionError) as caught:
        await list_server_tools(connection)

    assert "uv pip install failed" in caught.value.reason
    assert "a2flow-no-such-package-xyz" in caught.value.reason
    assert "script_runners" not in caught.value.reason
