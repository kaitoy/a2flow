# A2Flow

![A2Flow](frontend/assets/logo.png)

A chat application that connects a [Google ADK](https://google.github.io/adk-docs/) agent to a Next.js UI using the [AG-UI protocol](https://docs.ag-ui.com/concepts/events). The agent supports [A2UI](https://a2ui.org/) — it can generate structured UI JSON payloads alongside plain text responses.

The frontend uses a **glassmorphism** visual style with a **light/dark theme toggle** (persisted in `localStorage`, defaults to the OS preference). See [DESIGN.md](DESIGN.md) for the full design system reference.

```
┌──────────────────────────────────┐    AG-UI RunAgentInput (JSON)    ┌──────────────────────┐
│   Next.js frontend               │  (render_a2ui tool injected by   │  FastAPI backend     │
│   @ag-ui/client                  │ ───────────────────────────────► │  Google ADK agent    │
│   @ag-ui/a2ui-middleware         │   A2UIMiddleware)                 │  AGUIToolset         │
│   Redux Toolkit                  │                                   │  InMemorySession     │
│   Admin UI (/admin)              │ ◄─────────────────────────────── │  SQLite (SQLModel)   │
└──────────────────────────────────┘  AG-UI events (SSE) incl.        └──────────────────────┘
     :3000                            A2UI (TOOL_CALL_*)                    :8000
```

## Repository layout

```
a2flow/
├── backend/   # FastAPI + Google ADK agent
└── frontend/  # Next.js 16 chat UI
```

## Quick start

### 1. Backend

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/)

```bash
cd backend
uv sync
cp .env.example .env
# Edit .env — set LLM_MODEL and the corresponding API key (see backend/README.md)
uv run uvicorn main:app --reload
```

The API is now available at `http://localhost:8000`.

### 2. Frontend

Requirements: Node.js 20+, pnpm

```bash
cd frontend
pnpm install
# Optional: cp .env.local.example .env.local  (only needed if backend is not on :8000)
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000).

### 3. Git hooks (lefthook)

Pre-commit / pre-push hooks run linters, formatters, type checkers, and tests automatically. Configuration lives in [lefthook.yml](lefthook.yml). Install [lefthook](https://lefthook.dev/) once per machine using your preferred package manager:

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

## Admin UI

The admin area lives at [http://localhost:3000/admin](http://localhost:3000/admin).

### Agent Skills

Navigate to [http://localhost:3000/admin/agent-skills](http://localhost:3000/admin/agent-skills) to manage the Agent Skills registry — a catalog of AI agent skills stored in Git repositories.

| Operation | Path |
|-----------|------|
| List all skills | `GET /admin/agent-skills` |
| Register a new skill | `GET /admin/agent-skills/new` |
| Edit / delete a skill | `GET /admin/agent-skills/{id}` |

Skills are persisted in a SQLite database (`a2flow.db` by default, configurable via `DB_URL` in `backend/.env`). Each record stores the skill name, repository URL, repository path, and description.

### Workflows

Navigate to [http://localhost:3000/admin/workflows](http://localhost:3000/admin/workflows) to manage Workflows — named configurations that pair a prompt with an Agent Skill.

| Operation | Path |
|-----------|------|
| List all workflows | `GET /admin/workflows` |
| Create a new workflow | `GET /admin/workflows/new` |
| Edit / delete a workflow | `GET /admin/workflows/{id}` |
| Run a workflow | "Run" button in the list (calls `POST /workflows/{id}/execute`) |

Each workflow record stores a name, prompt (instructions for the agent), a reference to an Agent Skill, and an optional description. Workflows are also persisted in `a2flow.db`.

#### Running a workflow

Clicking **Run** on a workflow creates a **WorkflowSession** — an independent entity that captures a snapshot of the workflow configuration at execution time:

1. The backend shallow-clones the linked Agent Skill's repository into `backend/.skills_cache/<agent_skill_id>/` (only on first run) using [Dulwich](https://www.dulwich.io/) — no external `git` CLI required.
2. A new ADK session is created with the skill binding stored in its state. A `WorkflowSession` record is persisted to the database, capturing the workflow name, prompt, skill details, and the ADK session ID.
3. The backend returns the `WorkflowSession` (HTTP 201). The frontend redirects to `/workflow-sessions/{workflowSession.id}`.
4. On mount, the `/workflow-sessions/{id}` page fetches the `WorkflowSession`, and if no prior messages exist for the session, it automatically sends `workflow.prompt` as the first user message via `POST /workflow-sessions/{id}/agent`.
5. The `/workflow-sessions/{id}/agent` endpoint loads the skill-bound `ADKAgent` (keyed by `agent_skill_id`) and streams AG-UI SSE events back, identical to the regular `POST /agent` endpoint. The agent runs under a workflow-specific instruction: *"use the provided skill to produce an actionable task list for the user's request"*.
6. Subsequent user messages continue to flow through `POST /workflow-sessions/{id}/agent`, so A2UI rendering and the full chat experience work normally.

Workflow sessions are independent of regular chat sessions — deleting a workflow does not affect existing `WorkflowSession` records (the `workflow_id` FK is set to `NULL` on delete, but the snapshot data remains).

The individual tasks produced during a workflow session are persisted as `WorkflowTask` records and managed via dedicated CRUD endpoints. Each task carries a status (`pending` / `in_progress` / `completed` / `failed` / `skipped`) and an integer `position` for stable layout ordering. See [backend/README.md](backend/README.md#workflow-tasks) for the API reference. Deleting a `WorkflowSession` cascades to its tasks.

Tasks form a **directed acyclic graph (DAG)** rather than a flat list: each task may depend on zero or more other tasks in the same session via its `dependsOnIds` field (`(task, dependsOn)` edges are stored in the `workflow_task_dependencies` join table). A task's edges can be set at creation time or replaced on update by sending the full `dependsOnIds` list; omitting the field on update leaves edges unchanged. Dependency targets must exist and belong to the same session (otherwise HTTP 422 `FOREIGN_KEY_VIOLATION`), and edges that would introduce a cycle — including a self-dependency — are rejected with HTTP 409 `DEPENDENCY_CYCLE`. Deleting a task cascades to the dependency edges that reference it in either direction.

### Workflow Sessions

Navigate to [http://localhost:3000/admin/workflow-sessions](http://localhost:3000/admin/workflow-sessions) to browse every executed `WorkflowSession`. Each row links to the chat UI (`/workflow-sessions/{id}`) and to the nested **Workflow Tasks** admin page (`/admin/workflow-sessions/{id}/workflow-tasks`) where individual tasks belonging to that session can be created, edited, deleted, and have their status updated inline. The create and edit forms include a **Depends on** picker for selecting which other tasks in the same session a task depends on (its DAG edges); dependencies are shown as a column on the list, and edges that would form a cycle are rejected by the server.

| Operation | Path |
|-----------|------|
| List all sessions | `GET /admin/workflow-sessions` |
| List a session's tasks | `GET /admin/workflow-sessions/{id}/workflow-tasks` |
| Create a task | `GET /admin/workflow-sessions/{id}/workflow-tasks/new` |
| Edit / delete a task | `GET /admin/workflow-sessions/{id}/workflow-tasks/{taskId}` |

## How it works

1. When the user clicks "+ New session", the frontend navigates to `/newSession` without contacting the backend. The session ID (`threadId`) is generated by the frontend (`crypto.randomUUID()`) at the moment the user submits the first message; the ADK session is created implicitly by the backend on the first `POST /agent` request that references it. The page URL is then replaced with `/sessions/{id}` so the streamed response continues under the canonical session route.
2. When the user submits a message, `createChatAgent()` creates an `HttpAgent` (from `@ag-ui/client`) configured with the `X-User-Id` header and `A2UIMiddleware` (from `@ag-ui/a2ui-middleware`) applied. Before each request reaches the backend, the middleware injects the `render_a2ui` tool into `RunAgentInput.tools` and the A2UI Basic Catalog schema (downloaded from `https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json` at build time) into `RunAgentInput.context`.
3. The backend's `ADKAgent` (from `ag-ui-adk`) bridges the AG-UI protocol to a Google ADK `LlmAgent` — translating events, managing sessions, and streaming AG-UI SSE events back to the client. The agent uses `AGUIToolset`, which the bridge replaces at runtime with a `ClientProxyToolset` built from `RunAgentInput.tools` — making the frontend-injected `render_a2ui` tool callable by the LLM.
4. When the LLM calls `render_a2ui`, the `ADKAgent` streams `TOOL_CALL_*` events. The `A2UIMiddleware` intercepts these, reconstructs the A2UI operations, and emits `ACTIVITY_SNAPSHOT` events (one per surface, `activityType: "a2ui-surface"`). No tool execution happens on the backend.
5. The frontend's `AgentSubscriber` dispatches each event to a Redux store. Text events update the chat incrementally. `ACTIVITY_SNAPSHOT` events carry A2UI operations under the `a2ui_operations` key, which are stored in Redux. `A2uiRenderer` feeds the operations to `MessageProcessor` (from `@a2ui/web_core/v0_9`) and renders surfaces via `<A2uiSurface>`. Component rendering uses `tailwindCatalog` — a custom `Catalog<ReactComponentImplementation>` in `src/components/a2uiCatalog.tsx` that provides Tailwind CSS–styled versions of `Text`, `Button`, `Card`, `Row`, `Column`, `TextField`, and `ChoicePicker`. `marked` is used as the markdown renderer via `MarkdownContext`.
6. When the LLM calls `render_a2ui`, `useChat` captures the tool call ID via `onToolCallEndEvent` and stores it in a ref. When the user triggers an action on the rendered surface (e.g. clicking a `Button`), `sendA2uiAction` sends a tool result message for that `render_a2ui` call — with the action description as the content — directly to `POST /agent`. This lets the backend match the result against the pending `render_a2ui` tool call and forward it to the LLM, which then responds to the user's action. `forwardedProps.a2uiAction` / `A2UIMiddleware.processUserAction` is not used.
7. Session state is preserved in memory on the backend; `threadId` is used directly as the ADK session ID (`use_thread_id_as_session_id=True`), so reusing the same `threadId` continues the conversation efficiently.

## API contract (OpenAPI → Zod)

The REST endpoints are described by the FastAPI app and exported as OpenAPI 3.1. The frontend consumes that spec to generate Zod schemas and TypeScript types, which are then used for runtime response validation.

```
backend/main.py (FastAPI app)
   │
   │  uv run python -m scripts.export_openapi
   ▼
backend/openapi.yaml ◄─── gitignored (regenerated locally / in CI)
   │
   │  pnpm generate:api  (frontend)
   ▼
frontend/src/generated/api/{types.gen.ts, zod.gen.ts}  ◄─── gitignored
```

The AG-UI streaming endpoint (`POST /agent`) is marked `include_in_schema=False` and is intentionally excluded from the spec — its events are typed by `@ag-ui/core`. The `{meta, data, error}` response envelope is applied by middleware and is not part of the spec; the frontend's `unwrap()` helper handles it, and the generated Zod schemas validate the inner `data` payload.

`pnpm generate:api` (frontend) runs the backend export step via `uv` first, then the Zod codegen — so a single command keeps both layers in sync. The frontend's `predev` and `prebuild` hooks invoke it automatically, so `pnpm dev` and `pnpm build` regenerate the spec and schemas on every run. `uv` must be available on `PATH`.

## List query parameters

Every collection endpoint (`GET /agent-skills`, `GET /workflows`, `GET /workflow-sessions`, `GET /workflow-sessions/{id}/workflow-tasks`) accepts the same set of optional query parameters. Field names are written in **camelCase** (matching the JSON response), and an unknown field, operator, or uncoercible value returns HTTP 400 with the `INVALID_QUERY` error code.

| Param | Purpose | Syntax | Example |
|---|---|---|---|
| `limit` | Page size (1–1000, default 20) | integer | `?limit=50` |
| `offset` | Records to skip (default 0) | integer | `?offset=100` |
| `s` | Sort | Comma-separated fields; prefix `-` for descending | `?s=-createdAt,name` |
| `q` | Filter (repeatable) | `field:op:value` | `?q=name:like:foo&q=status:eq:pending` |

Filter operators (`op`):

| Operator | Meaning |
|---|---|
| `eq` / `ne` | Equal / not equal |
| `lt` / `lte` / `gt` / `gte` | Less / less-or-equal / greater / greater-or-equal |
| `like` | Case-insensitive substring match (string fields) |
| `in` | Matches any of a comma-separated list, e.g. `status:in:pending,completed` |

When `s` is omitted, each endpoint falls back to its default ordering (`createdAt` descending; workflow tasks order by `position` then `createdAt` ascending).

## LLM configuration

Set `LLM_MODEL` in `backend/.env`:

| Provider | Value |
|---|---|
| Google Gemini (default) | `gemini-2.0-flash` |
| OpenAI via LiteLLM | `litellm:openai/gpt-4o` |
| Anthropic via LiteLLM | `litellm:anthropic/claude-3-5-sonnet-20241022` |

See [backend/README.md](backend/README.md) for the full configuration reference.

## Further reading

- [backend/README.md](backend/README.md) — API reference, environment variables, running options
- [frontend/README.md](frontend/README.md) — project structure, component overview, environment variables
