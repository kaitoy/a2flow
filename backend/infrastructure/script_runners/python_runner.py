"""Serve a Python script's public functions as MCP tools over stdio.

Run as ``python -I python_runner.py`` with the source in
:data:`infrastructure.script_runners.SOURCE_ENV_VAR`. Every function defined at
the script's top level whose name does not start with ``_`` becomes a tool:
FastMCP derives its input schema from the type hints and its description from
the docstring. Functions the script merely imports are skipped.

stdout carries the MCP protocol, so ``sys.stdout`` is pointed at stderr before
the script runs: a stray ``print()`` lands in the server log instead of
corrupting the stream.

This file is started as a script, not imported, so it depends on nothing of
A2Flow's own -- only the MCP SDK installed alongside it.
"""

import inspect
import os
import sys
import types
from io import TextIOWrapper

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.stdio import stdio_server

_SOURCE_ENV_VAR = "A2FLOW_SCRIPT_SOURCE"
_MODULE_NAME = "user_script"


def load_tools(source: str) -> FastMCP:
    """Execute ``source`` and register its public functions on a new server.

    Args:
        source: The script's source code.

    Returns:
        A FastMCP server exposing one tool per public top-level function.
    """
    module = types.ModuleType(_MODULE_NAME)
    exec(compile(source, "<script>", "exec"), module.__dict__)  # noqa: S102
    server = FastMCP("script")
    for name, obj in vars(module).items():
        if (
            inspect.isfunction(obj)
            and not name.startswith("_")
            and obj.__module__ == _MODULE_NAME
        ):
            server.add_tool(obj)
    return server


async def _serve(server: FastMCP, protocol_out: TextIOWrapper) -> None:
    """Run ``server`` over stdin and ``protocol_out``.

    Mirrors ``FastMCP.run_stdio_async``, which writes to whatever
    ``sys.stdout`` is at the time and so cannot be used once it points at
    stderr.

    Args:
        server: The server to run.
        protocol_out: The process's real stdout.
    """
    async with stdio_server(stdout=anyio.wrap_file(protocol_out)) as (read, write):
        low_level = server._mcp_server
        await low_level.run(read, write, low_level.create_initialization_options())


def main() -> None:
    """Load the script from the environment and serve it until stdin closes."""
    protocol_out = TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stdout = sys.stderr
    server = load_tools(os.environ.pop(_SOURCE_ENV_VAR))
    anyio.run(_serve, server, protocol_out)


if __name__ == "__main__":
    main()
