# A2Flow

A chat application that connects a Google ADK agent to a Next.js UI via the AG-UI protocol. See [README.md](README.md) for the full overview, architecture diagram, and quick-start instructions.

## Repository layout

```
a2flow/
├── backend/   # FastAPI + Google ADK agent (Python)
└── frontend/  # Next.js 16 chat UI (TypeScript)
```

See each directory's README.md for details.

## Conventions

All documentation (docs, comments, commit messages) must be written in English.

## Toolchain versions

[mise.toml](mise.toml) at the repository root is the single source of truth for the Python, Node.js, pnpm, uv, and lefthook versions used in development. Run `mise install` after cloning or after any change to that file.

When bumping a version in `mise.toml`, update the places that pin the same tool independently in the same change:

| `mise.toml` entry | Also update |
|---|---|
| `python` | `backend/.python-version`, `backend/Dockerfile` and `frontend/Dockerfile` base image tags |
| `node` | `backend/Dockerfile` and `frontend/Dockerfile` base image tags |
| `pnpm` | `packageManager` in `frontend/package.json` (corepack reads it during the Docker build, and pnpm self-switches to it) |

`backend/pyproject.toml` sets `[tool.uv] python-preference = "only-system"` so `uv sync` builds `backend/.venv` from the mise-pinned interpreter on `PATH` instead of downloading its own. `requires-python`, ruff's `target-version`, and mypy's `python_version` stay at the 3.11 support floor and are deliberately not bumped alongside `mise.toml`.

## Documentation comments

When adding or modifying any module, class, or function, write and maintain a documentation comment for it:

- **Python** — use docstrings (`"""..."""`) on every module, class, and public function. Follow Google style.
- **TypeScript** — use JSDoc (`/** ... */`) on every exported component, function, type, and interface.

A change that adds or modifies a symbol without updating its doc comment is not considered done.

## Claude Code hooks

A `PostToolUse` hook fires after every `Write` or `Edit` tool call and runs the following tools automatically:

| Tool | Target | Role |
|------|--------|------|
| **Ruff** | `backend/` (Python) | Lint + format |
| **Biome** | `frontend/` (TypeScript) | Lint + format |
| **mypy** | `backend/` (Python) | Type check |

Hook scripts live in `scripts/hooks/`. Errors reported by these tools must be fixed before considering a change done.

Ruff removes unused imports automatically. When adding a new import to a Python file, always add the import and the code that uses it in the same `Edit` call. Otherwise the hook will strip the import before the next edit can reference it.

## Design system

Colors, typography, spacing, and component styles are defined in [DESIGN.md](DESIGN.md). Consult it whenever adding or modifying UI components.

## UI consistency

Pages that share the same structural element (header, footer, form layout, etc.) must use the same shared component — never duplicate markup with hand-written classes. If no suitable shared component exists yet, extract one before writing the new page. Inline styles or one-off class combinations that duplicate an existing component are not acceptable; extend the existing component instead.

## Keeping tests in sync

When modifying CSS class names or markup structure of a UI component, update every
`.test.tsx` that asserts those class names or that structure **in the same task**.

Before marking any frontend UI change done, run:

```bash
cd frontend && pnpm test --run
```

All tests must pass. A change is not complete while tests are failing.

Skip this manual run if you're about to commit immediately afterward — lefthook's pre-commit hook (see [git-workflow.md](.claude/rules/git-workflow.md)) already runs the full backend and frontend suites, so running them again first just duplicates that work. Run it manually when you want feedback mid-task, before the commit step.

## Keeping README.md up to date

Whenever a change falls into any of the following categories, update [README.md](README.md) to reflect it before considering the change done:

- **New feature** — any user-visible capability added to the backend or frontend
- **Architecture change** — modifications to how components interact (e.g. adding a new service, changing the AG-UI message flow)
- **Technology stack change** — swapping or adding a framework, runtime, language, or major library

## Keeping generated API types in sync

`frontend/src/generated/api/` is auto-generated from `backend/openapi.yaml`. `backend/openapi.yaml` itself is regenerated from the FastAPI app by:

```bash
cd backend && uv run python -m scripts.export_openapi
```

Routes declare `response_model=ApiResponse[T]` and return `ApiResponse(meta=meta, data=...)`, so the spec produced by `app.openapi()` already contains the `{meta, data, error}` envelope shape — the export script does no post-processing. `ApiMeta` and `ApiError` are real Pydantic models in `backend/models/response.py`, and they appear in the spec because `ApiResponse[T]` references them.

After the YAML is regenerated, refresh the frontend bindings:

```bash
cd frontend && pnpm openapi-ts
```

Whenever `backend/openapi.yaml` changes (e.g. route path prefixes, operation IDs) or types are regenerated, the Zod schema export names in `zod.gen.ts` can change — they embed the full URL path segments. For example, adding an `/api/v1/` prefix changes `zListAgentSkillsAgentSkillsGetResponse` to `zListAgentSkillsApiV1AgentSkillsGetResponse`.

After any regeneration, verify that all imports in `frontend/src/lib/api.ts` still match the current export names in `zod.gen.ts`. A quick check:

```bash
cd frontend && pnpm build
```

Module-not-found errors on `zod.gen` imports indicate a name mismatch that must be fixed before the change is done.
