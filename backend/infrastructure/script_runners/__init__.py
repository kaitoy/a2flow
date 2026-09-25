"""Runners that serve a ``script`` MCP server's source over stdio.

A script server is launched like any stdio server: the backend resolves it
(:func:`infrastructure.mcp_connection.resolve_connection`) into a command that
starts one of the runners here, with the source in the
:data:`SOURCE_ENV_VAR` environment variable. The runner loads the source and
exposes each public top-level function as an MCP tool.

Both images carry this directory at the same path (the Dockerfile copies the
whole backend tree into their shared base stage), so a path computed here in
the backend is valid in the MCP proxy container too.
"""

from pathlib import Path

#: Environment variable carrying the script's source to its runner.
SOURCE_ENV_VAR = "A2FLOW_SCRIPT_SOURCE"

#: Runner for Python scripts; started with the backend's own interpreter.
PYTHON_RUNNER = Path(__file__).with_name("python_runner.py")

#: Runner for JavaScript (ES module) scripts; started with ``node``.
NODE_RUNNER = Path(__file__).with_name("node_runner.mjs")
