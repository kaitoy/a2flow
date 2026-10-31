"""Tests for the per-launch bubblewrap sandbox around stdio MCP servers."""

from pathlib import Path

import pytest

from infrastructure.mcp_client import StdioConnection
from infrastructure.mcp_sandbox import SANDBOX_HOME, wrap
from repositories.exceptions import McpConnectionError

TENANT = "0190a2b4-0000-7000-8000-000000000001"


def _connection(tenant_id: str | None = TENANT) -> StdioConnection:
    return StdioConnection(
        command="npx",
        args=["-y", "pkg", "--token", "s3cret"],
        env={"API_KEY": "s3cret"},
        raw_args=["-y", "pkg", "--token", "${env:API_KEY}"],
        tenant_id=tenant_id,
    )


def test_wrap_isolates_the_launch_in_its_tenants_home(tmp_path: Path) -> None:
    wrapped = wrap(_connection(), tmp_path)

    assert wrapped.command == "bwrap"
    args = wrapped.args
    # Own PID namespace and /proc, killed with its parent, read-only root.
    for flag in ("--unshare-all", "--die-with-parent", "--new-session"):
        assert flag in args
    assert args[args.index("--proc") + 1] == "/proc"
    assert args[args.index("--ro-bind") + 1 : args.index("--ro-bind") + 3] == ["/", "/"]
    # The tenant's directory, created on demand, is the only persistent write.
    home = tmp_path / TENANT
    assert home.is_dir()
    assert args[args.index("--bind") + 1 : args.index("--bind") + 3] == [
        str(home),
        SANDBOX_HOME,
    ]
    assert args[
        args.index("/var/lib/a2flow") - 1 : args.index("/var/lib/a2flow") + 1
    ] == ["--tmpfs", "/var/lib/a2flow"]
    # The original command follows `--` unchanged.
    assert args[args.index("--") + 1 :] == ["npx", "-y", "pkg", "--token", "s3cret"]
    assert wrapped.env == {"API_KEY": "s3cret", "HOME": SANDBOX_HOME}
    # The label still shows the unexpanded argv, never the secret.
    assert "s3cret" not in wrapped.label


@pytest.mark.parametrize("tenant_id", [None, "", "../other", "not-a-uuid"])
def test_wrap_refuses_a_launch_without_a_valid_tenant(
    tmp_path: Path, tenant_id: str | None
) -> None:
    with pytest.raises(McpConnectionError):
        wrap(_connection(tenant_id), tmp_path)
    assert list(tmp_path.iterdir()) == []
