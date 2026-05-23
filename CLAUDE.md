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

## Keeping tests in sync

When modifying CSS class names or markup structure of a UI component, update every
`.test.tsx` that asserts those class names or that structure **in the same task**.

Before marking any frontend UI change done, run:

```bash
cd frontend && pnpm test --run
```

All tests must pass. A change is not complete while tests are failing.

## Keeping README.md up to date

Whenever a change falls into any of the following categories, update [README.md](README.md) to reflect it before considering the change done:

- **New feature** — any user-visible capability added to the backend or frontend
- **Architecture change** — modifications to how components interact (e.g. adding a new service, changing the AG-UI message flow)
- **Technology stack change** — swapping or adding a framework, runtime, language, or major library

## Keeping generated API types in sync

`frontend/src/generated/api/` is auto-generated from `backend/openapi.yaml` by running:

```bash
cd frontend && pnpm openapi-ts
```

Whenever `backend/openapi.yaml` changes (e.g. route path prefixes, operation IDs) or types are regenerated, the Zod schema export names in `zod.gen.ts` can change — they embed the full URL path segments. For example, adding an `/api/v1/` prefix changes `zListAgentSkillsAgentSkillsGetResponse` to `zListAgentSkillsApiV1AgentSkillsGetResponse`.

After any regeneration, verify that all imports in `frontend/src/lib/api.ts` still match the current export names in `zod.gen.ts`. A quick check:

```bash
cd frontend && pnpm build
```

Module-not-found errors on `zod.gen` imports indicate a name mismatch that must be fixed before the change is done.
