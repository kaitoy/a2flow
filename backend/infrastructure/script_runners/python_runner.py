"""Serve a Python script's public functions as MCP tools over stdio.

Run as ``python -I python_runner.py`` with the source in
:data:`infrastructure.script_runners.SOURCE_ENV_VAR`. Every function defined at
the script's top level whose name does not start with ``_`` becomes a tool:
FastMCP derives its input schema from the type hints and its description from
the docstring. Functions the script merely imports are skipped.

The script's packages, a JSON array in
:data:`infrastructure.script_runners.PACKAGES_ENV_VAR`, are installed first
with ``uv pip install --target`` into a directory put ahead of the rest of
``sys.path``.

stdout carries the MCP protocol, so ``sys.stdout`` is pointed at stderr before
the script runs: a stray ``print()`` lands in the server log instead of
corrupting the stream.

This file is started as a script, not imported, so it depends on nothing of
A2Flow's own -- only the MCP SDK installed alongside it.
"""

import hashlib
import inspect
import json
import os
import shutil
import subprocess
import sys
import traceback
from io import TextIOWrapper
from pathlib import Path
from types import ModuleType
from typing import Any

import anyio
from mcp import types
from mcp.server.fastmcp import FastMCP
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

_SOURCE_ENV_VAR = "A2FLOW_SCRIPT_SOURCE"
_PACKAGES_ENV_VAR = "A2FLOW_SCRIPT_PACKAGES"
_MODULE_NAME = "user_script"


def install_packages(packages: list[str]) -> Path:
    """Install ``packages`` into a cache directory and return it.

    The directory is shared by every script declaring the same set on the same
    Python version, keyed by their hash. A missing one is built under a
    temporary name and renamed into place, so a concurrent launch never sees a
    half-installed directory; losing that race just discards the duplicate.

    Args:
        packages: pip requirement strings.

    Returns:
        The directory holding the installed packages.

    Raises:
        RuntimeError: If ``uv`` is missing or the install fails; the message
            carries uv's error output.
    """
    key = hashlib.sha256(
        json.dumps([sys.version_info[:2], sorted(packages)]).encode()
    ).hexdigest()
    # ponytail: cache directories are never pruned; add a cleanup when disk use
    # matters.
    target = Path.home() / ".cache" / "a2flow-script-packages" / "python" / key
    if target.exists():
        return target
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv was not found on PATH")
    tmp = target.with_name(f"{key}.tmp-{os.getpid()}")
    completed = subprocess.run(
        [uv, "pip", "install", "--quiet", "--python", sys.executable]
        + ["--target", str(tmp), "--", *packages],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError(f"uv pip install failed:\n{completed.stderr.strip()}")
    try:
        tmp.rename(target)
    except OSError:
        shutil.rmtree(tmp, ignore_errors=True)
        if not target.exists():
            raise
    return target


def load_tools(source: str) -> FastMCP:
    """Execute ``source`` and register its public functions on a new server.

    Args:
        source: The script's source code.

    Returns:
        A FastMCP server exposing one tool per public top-level function.
    """
    module = ModuleType(_MODULE_NAME)
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


def script_traceback(exc: BaseException) -> str:
    """Format a load failure with only the script's own frames.

    The runner's frames say nothing to the script's author and would expose
    where the runner lives, so they are dropped; a ``SyntaxError`` keeps its
    caret line, which carries no frame at all.

    Args:
        exc: The exception raised while loading the script.

    Returns:
        The traceback text.
    """
    summary = traceback.TracebackException.from_exception(exc)
    summary.stack = traceback.StackSummary.from_list(
        [frame for frame in summary.stack if frame.filename == "<script>"]
    )
    return "".join(summary.format())


def failed_server(error: str) -> Server[Any, Any]:
    """Build a server that reports a script load failure on every request.

    The handshake still completes, so the client sees ``error`` -- the
    traceback -- instead of a connection that closed before initializing:
    ``tools/list`` answers with a JSON-RPC error and ``tools/call`` with an
    ``isError`` result, both carrying it.

    Args:
        error: The load failure's traceback.

    Returns:
        A low-level server advertising no tools.
    """
    server: Server[Any, Any] = Server("script")

    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[types.Tool]:
        raise RuntimeError(error)

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[Any]:
        raise RuntimeError(error)

    return server


async def _serve(server: Server[Any, Any], protocol_out: TextIOWrapper) -> None:
    """Run ``server`` over stdin and ``protocol_out``.

    Mirrors ``FastMCP.run_stdio_async``, which writes to whatever
    ``sys.stdout`` is at the time and so cannot be used once it points at
    stderr.

    Args:
        server: The low-level server to run.
        protocol_out: The process's real stdout.
    """
    async with stdio_server(stdout=anyio.wrap_file(protocol_out)) as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    """Load the script from the environment and serve it until stdin closes.

    A script that fails to load -- a package that will not install, a syntax
    error, an exception at its top level -- is served by :func:`failed_server`, so its traceback reaches the
    client rather than only this process's stderr.
    """
    protocol_out = TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stdout = sys.stderr
    try:
        packages = json.loads(os.environ.pop(_PACKAGES_ENV_VAR, "[]"))
        if packages:
            sys.path.insert(0, str(install_packages(packages)))
        server = load_tools(os.environ.pop(_SOURCE_ENV_VAR))._mcp_server
    except Exception as exc:
        error = script_traceback(exc)
        print(error, file=sys.stderr)
        server = failed_server(error)
    anyio.run(_serve, server, protocol_out)


if __name__ == "__main__":
    main()
