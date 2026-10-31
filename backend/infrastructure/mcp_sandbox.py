"""Wrap a stdio MCP server's launch in a per-launch bubblewrap sandbox.

Every stdio server -- an ``npx``/``uvx`` package or a ``script`` runner -- is
third-party or tenant-written code, and the MCP proxy launches all of them,
for every tenant, as one Unix user. Without a sandbox, one launch could read
another's resolved secrets from ``/proc/<pid>/environ``, outlive its call by
calling ``setsid``, or rewrite the runners and package caches the next
tenant's launch loads.

:func:`wrap` turns a connection into the same command run under ``bwrap``:

* ``--unshare-all`` (user, PID, IPC, UTS, cgroup) with a fresh ``/proc``: the
  launch sees only its own processes, so no other launch's environment or
  ``argv`` is readable.
* ``--die-with-parent``: when the call ends and ``bwrap`` goes, PID 1 of the
  namespace goes with it, and the kernel kills everything left inside --
  including a grandchild that escaped the process group.
* ``--ro-bind / /``: the system, the application tree, and the runners are
  read-only. The proxy's own state under ``/var/lib/a2flow`` (its TLS private
  key) is hidden behind an empty tmpfs.
* The only writable places are a scratch ``/tmp`` and ``HOME``, which is bound
  from ``<sandbox_dir>/<tenant_id>``: ``npx``, ``uv`` and the script runners
  keep their package caches under ``HOME``, so a cache is shared within a
  tenant and never across tenants.

The network namespace is shared on purpose: a server's job is to reach the
outside world, and what the proxy container can reach is already bounded by
its Docker network.
"""

import subprocess
import uuid
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from repositories.exceptions import McpConnectionError

if TYPE_CHECKING:  # mcp_client imports this module when it launches a server
    from infrastructure.mcp_client import StdioConnection

#: ``HOME`` inside the sandbox; the tenant's directory is bound here.
SANDBOX_HOME = "/home/a2flow"

#: The proxy's own state, hidden from every launch.
_HIDDEN_DIR = "/var/lib/a2flow"


def wrap(connection: "StdioConnection", sandbox_dir: Path) -> "StdioConnection":
    """Return ``connection`` with its command run inside a bubblewrap sandbox.

    Args:
        connection: The stdio server to launch; its ``tenant_id`` picks the
            home directory.
        sandbox_dir: Directory holding one home directory per tenant.

    Returns:
        A connection that runs ``bwrap`` with the original command after
        ``--``. ``env`` is unchanged apart from ``HOME``, and ``raw_args`` stays
        the original, unexpanded ``argv`` so the label never shows a secret.

    Raises:
        McpConnectionError: If the connection carries no tenant, or one that is
            not a UUID -- the id becomes a path segment, so anything else is
            refused rather than sanitized.
    """
    try:
        tenant = str(uuid.UUID(connection.tenant_id or ""))
    except ValueError:
        raise McpConnectionError(
            connection.label, "stdio launch has no valid tenant for its sandbox"
        ) from None
    home = sandbox_dir / tenant
    home.mkdir(parents=True, exist_ok=True)
    # fmt: off
    args = [
        "--die-with-parent", "--new-session",
        "--unshare-all", "--share-net",
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
        "--tmpfs", _HIDDEN_DIR,
        "--tmpfs", "/home",
        "--bind", str(home), SANDBOX_HOME,
        "--chdir", SANDBOX_HOME,
        "--", connection.command, *connection.args,
    ]
    # fmt: on
    return replace(
        connection,
        command="bwrap",
        args=args,
        env={**connection.env, "HOME": SANDBOX_HOME},
        raw_args=connection.args
        if connection.raw_args is None
        else connection.raw_args,
    )


def probe(sandbox_dir: Path) -> str | None:
    """Launch ``true`` the way :func:`wrap` launches a server, once.

    Called at proxy startup, so a host or container that cannot create the
    sandbox -- ``bwrap`` missing, user namespaces blocked by seccomp or
    AppArmor, a fresh ``/proc`` refused -- stops the proxy there instead of
    leaving it healthy while every stdio launch fails.

    Args:
        sandbox_dir: The directory :func:`wrap` will be given.

    Returns:
        ``None`` when the sandbox works, else why it does not.
    """
    from infrastructure.mcp_client import StdioConnection

    probe_tenant = str(uuid.UUID(int=0))
    wrapped = wrap(StdioConnection(command="true", tenant_id=probe_tenant), sandbox_dir)
    try:
        completed = subprocess.run(  # noqa: S603 -- fixed argv, no shell
            [wrapped.command, *wrapped.args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)
    if completed.returncode != 0:
        return completed.stderr.strip() or f"bwrap exited {completed.returncode}"
    return None
