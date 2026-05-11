# A2Flow

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

Each workflow record stores a name, prompt (instructions for the agent), a reference to an Agent Skill, and an optional description. Workflows are also persisted in `a2flow.db`.

## How it works

1. The frontend creates a session via `POST /sessions` on startup, obtaining an `id` / `threadId`.
2. When the user submits a message, `createChatAgent()` creates an `HttpAgent` (from `@ag-ui/client`) with `A2UIMiddleware` (from `@ag-ui/a2ui-middleware`) applied. Before each request reaches the backend, the middleware injects the `render_a2ui` tool into `RunAgentInput.tools` and the A2UI Basic Catalog schema (downloaded from `https://a2ui.org/specification/v0_9/basic_catalog.json` at build time) into `RunAgentInput.context`.
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
