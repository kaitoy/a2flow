# Git hooks (lefthook)

Pre-commit / pre-push hooks run linters, formatters, type checkers, and tests automatically. Configuration lives in [lefthook.yml](../../lefthook.yml). Install [lefthook](https://lefthook.dev/) once per machine using your preferred package manager:

| OS | Command |
|---|---|
| Windows | `winget install Evilmartians.Lefthook` (or `scoop install lefthook`) |
| macOS | `brew install lefthook` |
| Linux | See [installation docs](https://lefthook.dev/installation/) |

Then wire the hooks into `.git/hooks/` from the repository root:

```bash
lefthook install
```

**pre-commit** (parallel, ~25s on a clean repo): `ruff check` / `ruff format --check` / `mypy` / `pytest` on the backend, `biome ci` / `vitest run` on the frontend. Each job is gated by a `glob` so backend-only or frontend-only commits skip the other side's jobs.

**pre-push** (sequential): `next build` to catch type errors and missing `zod.gen` exports before the change reaches the remote.

To skip the hooks for an emergency commit, set `LEFTHOOK=0` (e.g. `LEFTHOOK=0 git commit ...`).
