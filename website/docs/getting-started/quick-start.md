---
title: Quick start
sidebar_position: 1
---

# Quick start

## 0. Toolchain ([mise](https://mise.jdx.dev/))

Python, Node.js, pnpm, uv, and lefthook versions are pinned in [mise.toml](https://github.com/kaitoy/a2flow/blob/master/mise.toml) and provisioned by mise, so every machine runs the same toolchain. Install mise once:

| OS | Command |
|---|---|
| Windows | `winget install jdx.mise` |
| macOS | `brew install mise` |
| Linux | See the [installation docs](https://mise.jdx.dev/installing-mise.html) |

Activate it in your shell (see [activation docs](https://mise.jdx.dev/installing-mise.html#shells) for bash/zsh/fish; on Windows add `(&mise activate pwsh) | Out-String | Invoke-Expression` to your PowerShell `$PROFILE`), then install the tools from the repository root:

```bash
mise trust
mise install
```

On Windows, also put mise's shims directory (`%LOCALAPPDATA%\mise\shims`) on your `PATH`. Git hooks and editor integrations are spawned outside an activated shell and resolve `uv` / `pnpm` / `python` from `PATH` alone.

Not using mise? The minimum versions are Python 3.11+, Node.js 20+, plus [uv](https://docs.astral.sh/uv/), pnpm, and lefthook installed by hand.

## 1. Backend

The backend itself needs only Python and uv; Node.js is used only to launch stdio [MCP servers](../guides/mcp-servers.md) published as npm packages (`npx`), and the `docker compose` image ships it.

```bash
cd backend
uv sync
cp .env.example .env
# Edit .env — set LLM_MODEL and the corresponding API key (see backend/README.md)
uv run uvicorn main:app --reload
```

The API is now available at `http://localhost:8000`.

## 2. Frontend

```bash
cd frontend
pnpm install
# Optional: cp .env.local.example .env.local  (only needed if backend is not on :8000)
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000). To run on a different port, see [Changing the port](https://github.com/kaitoy/a2flow/blob/master/frontend/README.md#changing-the-port) in the frontend README.

## 3. Git hooks (lefthook)

Pre-commit / pre-push hooks (lefthook) run linters, formatters, type checkers, and tests. `mise install` already provides the `lefthook` binary; run `lefthook install` once from the repository root to wire it into `.git/hooks/`. See [.claude/rules/git-workflow.md](https://github.com/kaitoy/a2flow/blob/master/.claude/rules/git-workflow.md) for details.
