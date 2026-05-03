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

## Design system

Colors, typography, spacing, and component styles are defined in [DESIGN.md](DESIGN.md). Consult it whenever adding or modifying UI components.

## Keeping README.md up to date

Whenever a change falls into any of the following categories, update [README.md](README.md) to reflect it before considering the change done:

- **New feature** — any user-visible capability added to the backend or frontend
- **Architecture change** — modifications to how components interact (e.g. adding a new service, changing the AG-UI message flow)
- **Technology stack change** — swapping or adding a framework, runtime, language, or major library
