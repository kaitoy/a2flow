"""Serve a Python script's public functions as MCP tools over stdio.

Run as ``python -I -S python_runner.py`` with the source in
:data:`infrastructure.script_runners.SOURCE_ENV_VAR`. Every function defined at
the script's top level whose name does not start with ``_`` becomes a tool:
its input schema is derived from the type hints (see :func:`input_schema`) and
its description from the docstring. Functions the script merely imports are
skipped.

``-S`` keeps ``site`` from running, so no site-packages directory -- in
particular the backend's own virtual environment -- is on ``sys.path``: a
script sees the standard library and nothing else. The script's packages, a
JSON array in :data:`infrastructure.script_runners.PACKAGES_ENV_VAR`, are
installed first with ``uv pip install --target`` into a directory put ahead of
the rest of ``sys.path``.

That is also why this file depends on nothing outside the standard library,
the MCP SDK included: it speaks just the slice of MCP a tool server needs --
``initialize``, ``ping``, ``tools/list``, ``tools/call`` -- as newline-delimited
JSON-RPC, like ``node_runner.mjs``.

stdout carries the protocol, so ``sys.stdout`` is pointed at stderr before
the script runs: a stray ``print()`` lands in the server log instead of
corrupting the stream.
"""

import asyncio
import hashlib
import inspect
import json
import os
import shutil
import subprocess
import sys
import traceback
import types
import typing
from collections.abc import Callable
from io import TextIOWrapper
from pathlib import Path
from typing import Any

_SOURCE_ENV_VAR = "A2FLOW_SCRIPT_SOURCE"
_PACKAGES_ENV_VAR = "A2FLOW_SCRIPT_PACKAGES"
_MODULE_NAME = "user_script"

_PRIMITIVES: dict[Any, str] = {
    bool: "boolean",
    int: "integer",
    float: "number",
    str: "string",
    dict: "object",
    list: "array",
    tuple: "array",
    set: "array",
    type(None): "null",
}


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


def load_tools(source: str) -> dict[str, Callable[..., Any]]:
    """Execute ``source`` and collect its public top-level functions.

    Args:
        source: The script's source code.

    Returns:
        The functions that become tools, by name.
    """
    module = types.ModuleType(_MODULE_NAME)
    exec(compile(source, "<script>", "exec"), module.__dict__)  # noqa: S102
    return {
        name: obj
        for name, obj in vars(module).items()
        if inspect.isfunction(obj)
        and not name.startswith("_")
        and obj.__module__ == _MODULE_NAME
    }


def type_schema(hint: Any) -> dict[str, Any]:
    """Map one type hint to a JSON Schema.

    Covers the JSON-shaped types: ``bool``/``int``/``float``/``str``,
    ``list``/``tuple``/``set`` (with ``items`` from a ``list[X]``/``set[X]``
    argument), ``dict``, ``Literal[...]``, and unions such as ``X | None``.

    Args:
        hint: The annotation.

    Returns:
        The schema; ``{}`` (any value) for anything else.
    """
    if hint in _PRIMITIVES:
        return {"type": _PRIMITIVES[hint]}
    origin, args = typing.get_origin(hint), typing.get_args(hint)
    if origin is typing.Literal:
        return {"enum": list(args)}
    if origin is typing.Union or origin is types.UnionType:
        schemas = [type_schema(arg) for arg in args]
        return schemas[0] if len(schemas) == 1 else {"anyOf": schemas}
    if origin in (list, set, frozenset):
        return (
            {"type": "array", "items": type_schema(args[0])}
            if args
            else {"type": "array"}
        )
    if origin in (tuple, dict):
        return {"type": _PRIMITIVES[origin]}
    return {}


def input_schema(fn: Callable[..., Any]) -> dict[str, Any]:
    """Build a tool's input schema from its function signature.

    Every named parameter becomes a property typed by :func:`type_schema`;
    one without a default is required, and a JSON-literal default is carried
    over. ``*args`` and ``**kwargs`` are left out. Arguments are passed to the
    function as they arrive -- nothing is coerced.

    Args:
        fn: The tool's function.

    Returns:
        An ``object`` schema.
    """
    try:
        hints = typing.get_type_hints(fn)
    except Exception:
        hints = {}
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, param in inspect.signature(fn).parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        schema = type_schema(hints[name]) if name in hints else {}
        if param.default is param.empty:
            required.append(name)
        elif isinstance(param.default, str | int | float | bool | None):
            schema = {**schema, "default": param.default}
        properties[name] = schema
    return {"type": "object", "properties": properties, "required": required}


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


def call_tool(fn: Callable[..., Any], arguments: dict[str, Any]) -> dict[str, Any]:
    """Invoke a tool and wrap its outcome as an MCP ``tools/call`` result.

    Args:
        fn: The tool's function; a coroutine function is run to completion.
        arguments: The call's arguments, passed as keyword arguments.

    Returns:
        The result: a string value as is, anything else as JSON, or the
        exception with ``isError`` set.
    """
    try:
        value = fn(**arguments)
        if inspect.iscoroutine(value):
            value = asyncio.run(value)
        text = value if isinstance(value, str) else json.dumps(value, default=str)
    except Exception as exc:
        return {
            "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
            "isError": True,
        }
    return {"content": [{"type": "text", "text": text}]}


def handle(
    request: dict[str, Any],
    tools: dict[str, Callable[..., Any]],
    load_error: str | None,
) -> dict[str, Any]:
    """Answer one JSON-RPC request.

    A script that failed to load is still served, so the handshake completes
    and the client sees ``load_error`` instead of a closed connection:
    ``tools/list`` answers with it as an error, ``tools/call`` as an
    ``isError`` result.

    Args:
        request: The parsed request.
        tools: The script's tools, by name.
        load_error: Why the script failed to load, or ``None``.

    Returns:
        Either ``{"result": ...}`` or ``{"error": ...}``.
    """
    method, params = request.get("method"), request.get("params") or {}
    if method == "initialize":
        return {
            "result": {
                "protocolVersion": params.get("protocolVersion"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "script", "version": "1.0.0"},
            }
        }
    if method == "ping":
        return {"result": {}}
    if method == "tools/list":
        if load_error is not None:
            return {"error": {"code": -32603, "message": load_error}}
        return {
            "result": {
                "tools": [
                    {
                        "name": name,
                        "description": inspect.getdoc(fn),
                        "inputSchema": input_schema(fn),
                    }
                    for name, fn in tools.items()
                ]
            }
        }
    if method == "tools/call":
        if load_error is not None:
            return {
                "result": {
                    "content": [{"type": "text", "text": load_error}],
                    "isError": True,
                }
            }
        name = str(params.get("name"))
        fn = tools.get(name)
        if fn is None:
            message = f"Unknown tool: {name}"
            return {"error": {"code": -32602, "message": message}}
        return {"result": call_tool(fn, params.get("arguments") or {})}
    return {"error": {"code": -32601, "message": f"Method not found: {method}"}}


def main() -> None:
    """Load the script from the environment and serve it until stdin closes."""
    protocol_out = TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")
    protocol_in = TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
    sys.stdout = sys.stderr

    def send(message: dict[str, Any]) -> None:
        protocol_out.write(json.dumps({"jsonrpc": "2.0", **message}) + "\n")
        protocol_out.flush()

    tools: dict[str, Callable[..., Any]] = {}
    load_error: str | None = None
    try:
        packages = json.loads(os.environ.pop(_PACKAGES_ENV_VAR, "[]"))
        if packages:
            sys.path.insert(0, str(install_packages(packages)))
        tools = load_tools(os.environ.pop(_SOURCE_ENV_VAR))
    except Exception as exc:
        load_error = script_traceback(exc)
        print(load_error, file=sys.stderr)

    for line in protocol_in:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("not a JSON-RPC message")
        except ValueError:
            send({"id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        # A message without an id is a notification (e.g.
        # notifications/initialized): no reply.
        if request.get("id") is None:
            continue
        send({"id": request["id"], **handle(request, tools, load_error)})


if __name__ == "__main__":
    main()
