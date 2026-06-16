# A2Flow

![A2Flow](frontend/assets/logo.png)

A chat application that connects a [Google ADK](https://google.github.io/adk-docs/) agent to a Next.js UI using the [AG-UI protocol](https://docs.ag-ui.com/concepts/events). The agent supports [A2UI](https://a2ui.org/) — it can generate structured UI JSON payloads alongside plain text responses.

The frontend uses a **glassmorphism** visual style with a **light/dark theme toggle** (persisted in `localStorage`, defaults to the OS preference). See [DESIGN.md](DESIGN.md) for the full design system reference. A **notification center** in the top toolbar surfaces workflow events such as plan approval requests (see [Notifications](#notifications)).

```
┌──────────────────────────────────┐    AG-UI RunAgentInput (JSON)    ┌──────────────────────┐
│   Next.js frontend               │  (render_a2ui tool injected by   │  FastAPI backend     │
│   @ag-ui/client                  │ ───────────────────────────────► │  Google ADK agent    │
│   @ag-ui/a2ui-middleware         │   A2UIMiddleware)                 │  AGUIToolset         │
│   Redux Toolkit                  │                                   │  InMemorySession     │
│   Admin UI (/admin)              │ ◄─────────────────────────────── │  SQLite/PostgreSQL   │
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

Pre-commit / pre-push hooks (lefthook) run linters, formatters, type checkers, and tests. See [.claude/rules/git-workflow.md](.claude/rules/git-workflow.md) for installation and details.

## Run with Docker Compose

Alternatively, the whole stack — PostgreSQL 17, the backend, and the frontend — can be built and started with Docker Compose ([compose.yml](compose.yml)):

```bash
echo GOOGLE_API_KEY=your_google_api_key_here > .env
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000). Database data persists in the `pgdata` volume across restarts.

## Database

All persistent data — REST API records and ADK session storage — lives in one relational database selected by `DB_URL` in `backend/.env`:

| Backend | `DB_URL` | Notes |
|---|---|---|
| SQLite (default) | `sqlite:///a2flow.db` | Zero-config local file |
| PostgreSQL | `postgresql://user:password@host:5432/a2flow` | Used by the Docker Compose stack |

The async driver suffix (`aiosqlite` / `asyncpg`) is added automatically. Tables are created on startup; no migration step is needed.

## Authentication

The app requires sign-in. Visiting any page while logged out redirects to `/login`. On first run, log in with the seeded **`admin`** user (password from `ADMIN_PASSWORD`, default `admin12345678`); manage additional users from the [admin UI](#users).

- **Session** — login creates a server-side session (`auth_sessions` table) and sets an HttpOnly `a2flow_session` cookie holding an opaque token (only its hash is stored). Sessions use a sliding **idle timeout** (`SESSION_IDLE_TIMEOUT_SECONDS`, default 8 hours).
- **CSRF** — login also sets a readable `a2flow_csrf` cookie; the frontend echoes it in the `X-CSRF-Token` header on every state-changing request (double-submit cookie). The backend rejects mismatches with `403`.
- **Same-origin proxy** — the browser calls the frontend origin (`:3000`); Next.js rewrites `/api/*` to the backend (`:8000`), so the auth cookies are first-party and `SameSite=Lax` works. Point the proxy elsewhere with `BACKEND_BASE_URL`.

See [backend/README.md](backend/README.md#authentication) for the endpoint and cookie details.

## Admin UI

The admin area lives at [http://localhost:3000/admin](http://localhost:3000/admin).

Every admin list table shares interactive features: **per-column sorting and filtering** (applied server-side via the list APIs' `s` and `q` query parameters, so they cover the whole dataset rather than just the current page), **drag-to-resize column widths** (kept for the session, not persisted), and **hover tooltips** that reveal the full text of any cell clipped to its column width.

### Users

Navigate to [http://localhost:3000/admin/users](http://localhost:3000/admin/users) to manage application users.

| Operation | Path |
|-----------|------|
| List all users | `GET /admin/users` |
| Create a new user | `GET /admin/users/new` |
| Edit / delete a user | `GET /admin/users/{id}` |

Each user record stores a username (unique), first name, last name, email, an `enabled` flag, and an `emailVerified` flag. Passwords are hashed with [bcrypt](https://pypi.org/project/bcrypt/) before persistence and are never returned by the API. On edit, leaving the password field blank keeps the existing password. Users are persisted in `a2flow.db`.

**Audit ownership.** Every persistent record stores `createdBy` / `updatedBy` as a foreign key to `users.id`, populated from the **authenticated session** (see [Authentication](#authentication)). A write whose acting user does not exist is rejected with HTTP 422 (`FOREIGN_KEY_VIOLATION`). To resolve the bootstrap "who creates the first user" problem, a hidden, login-disabled **system user** is seeded on startup when the `users` table is empty, and it owns the initial seeded `admin` user. In the admin UI the raw IDs are never shown — each detail page resolves `createdBy` / `updatedBy` to the user's `first last` name, and list views resolve user IDs the same way.

**Deleting a user.** If no other record references the user, it is hard-deleted from the database. If it is still referenced (via any `createdBy` / `updatedBy`), it is instead **soft-deleted**: `deletedAt` is set and the account is disabled, so existing references stay valid and the name still resolves. Soft-deleted users (and the system user) are hidden from the user list but remain fetchable by id.

### Agent Skills

Navigate to [http://localhost:3000/admin/agent-skills](http://localhost:3000/admin/agent-skills) to manage the Agent Skills registry — a catalog of AI agent skills stored in Git repositories.

| Operation | Path |
|-----------|------|
| List all skills | `GET /admin/agent-skills` |
| Register a new skill | `GET /admin/agent-skills/new` |
| Edit / delete a skill | `GET /admin/agent-skills/{id}` |

Skills are persisted in a SQLite database (`a2flow.db` by default, configurable via `DB_URL` in `backend/.env`). Each record stores the skill name, repository URL, repository path, and description.

### MCP Servers

Navigate to [http://localhost:3000/admin/mcp-servers](http://localhost:3000/admin/mcp-servers) to manage the registry of remote [MCP](https://modelcontextprotocol.io/) servers whose tools the workflow agent can bind to WorkflowTasks (see [MCP tools for tasks](#mcp-tools-for-tasks)).

| Operation | Path |
|-----------|------|
| List all servers | `GET /admin/mcp-servers` |
| Register a new server | `GET /admin/mcp-servers/new` |
| Edit / delete a server | `GET /admin/mcp-servers/{id}` |

Each record stores a unique name, the server's **streamable HTTP** endpoint URL (SSE-only servers are not supported), and an optional set of HTTP headers sent with every request — typically `Authorization: Bearer …` for servers that require auth. ⚠️ Header values are stored **in plaintext** in `a2flow.db` and returned by the API; this is acceptable for the app's local single-operator deployment model, but don't store credentials you can't afford to expose to other users of the same instance.

`GET /api/v1/mcp-servers/{id}/tools` queries the live server and returns the tools it advertises (name, description, input schema); the admin task forms use it to populate the tool picker. An unreachable server yields HTTP 502 (`MCP_UNREACHABLE`). A server cannot be deleted while WorkflowTask tool bindings still reference it (HTTP 409 `CONFLICT_REFERENCED`).

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
5. The `/workflow-sessions/{id}/agent` endpoint loads the skill-bound `ADKAgent` (keyed by `agent_skill_id`) and streams AG-UI SSE events back, identical to the regular `POST /agent` endpoint. The agent runs under a **plan-then-execute** workflow instruction and is equipped with WorkflowTask management tools (see below).
6. Subsequent user messages continue to flow through `POST /workflow-sessions/{id}/agent`, so A2UI rendering and the full chat experience work normally.

##### Agent-managed task DAG

The skill-driven agent does not just *suggest* steps — it **manages the WorkflowTasks itself** through dedicated agent tools, in two phases:

1. **Plan** — following the skill's instructions, the agent breaks the request into concrete steps and registers them as a DAG in a single `register_workflow_tasks` call (each step declares a `key` and its `depends_on` predecessors). It then presents the plan and **waits for your approval** before doing any work. Registering the plan also raises an **approval-request notification** (see [Notifications](#notifications)).
2. **Execute** — once approved, the agent loops: it lists the tasks, picks the next runnable one (a `pending` task whose dependencies are all `completed`), marks it `in_progress`, does the work per the skill, and marks it `completed` (or `failed` / `skipped`). When every task reaches a terminal state, a **session-completed notification** is raised.

Six tools back this — `register_workflow_tasks`, `create_workflow_task`, `list_workflow_tasks`, `get_workflow_task`, `update_workflow_task`, and `delete_workflow_task` — which resolve the current session from the ADK session id and operate on the same `WorkflowTask` records exposed by the REST API. You can watch the statuses update live in the **Workflow Tasks** admin view (Table or Graph). See [backend/README.md](backend/README.md#agent-task-tools) for the tool reference.

##### MCP tools for tasks

WorkflowTasks can use tools from remote MCP servers registered in the [MCP Servers](#mcp-servers) admin page:

1. **Bind at plan time** — during the Plan phase the agent calls `list_mcp_tools`, which queries every registered server concurrently and returns each server's advertised tools (unreachable servers are reported per-server without failing the listing). Steps that need an external tool get a `tools` entry (`[{"server_id": …, "tool_name": …}]`) in `register_workflow_tasks`; bindings are persisted in the `workflow_task_tool_bindings` join table and surfaced as `toolBindings` on the REST read model.
2. **Enforce at execution time** — the agent invokes bound tools through the `call_mcp_tool(server_id, tool_name, arguments)` proxy. The backend validates that the pair is bound to a task currently `in_progress` in the session (the union of bindings when several are in progress) before opening a per-call streamable HTTP connection to the server and forwarding the call. Calls to unbound tools are rejected with an error listing the allowed tools, so a shared, skill-cached agent can never use tools a task wasn't granted.

Bound tools appear as chips in the **Tools** column of the Workflow Tasks list, and the task create/edit forms include an **MCP Tools** picker populated live from the registered servers (already-bound tools stay visible even if their server is unreachable).

Workflow sessions are independent of regular chat sessions — deleting a workflow does not affect existing `WorkflowSession` records (the `workflow_id` FK is set to `NULL` on delete, but the snapshot data remains).

The individual tasks produced during a workflow session are persisted as `WorkflowTask` records and managed via dedicated CRUD endpoints. Each task carries a status (`pending` / `in_progress` / `completed` / `failed` / `skipped`) and an integer `position` for stable layout ordering. See [backend/README.md](backend/README.md#workflow-tasks) for the API reference. Deleting a `WorkflowSession` cascades to its tasks.

Tasks form a **directed acyclic graph (DAG)** rather than a flat list: each task may depend on zero or more other tasks in the same session via its `dependsOnIds` field (`(task, dependsOn)` edges are stored in the `workflow_task_dependencies` join table). A task's edges can be set at creation time or replaced on update by sending the full `dependsOnIds` list; omitting the field on update leaves edges unchanged. Dependency targets must exist and belong to the same session (otherwise HTTP 422 `FOREIGN_KEY_VIOLATION`), and edges that would introduce a cycle — including a self-dependency — are rejected with HTTP 409 `DEPENDENCY_CYCLE`. Deleting a task cascades to the dependency edges that reference it in either direction.

##### Human approval

When a task needs the user's explicit go-ahead before the agent acts (for example a destructive or irreversible operation), the agent asks for an **approval** mid-execution:

1. The agent calls the `request_approval` backend tool, which persists a `pending` **Approval** record for the current session (optionally linked to a `WorkflowTask`) and raises an **approval-request notification** addressed to the session owner.
2. The agent explains the request in plain text and then calls **`render_approval`** — an AG-UI **frontend tool** (declared by the client via `RunAgentInput.tools`, distinct from A2UI). Like `render_a2ui`, the bridge exposes it as a long-running client tool: the run pauses and the frontend renders **Approve / Reject** controls in the chat.
3. Clicking a button writes the decision **directly** to the backend via `PATCH /api/v1/approvals/{id}` (recording the approver in the audit fields), then returns the decision as the tool result so the agent run resumes.
4. On `approved` the agent proceeds; on `rejected` it marks the task `failed` (or `skipped`). The agent can re-check a decision with the `get_approval` tool.

Approvals are persisted in `a2flow.db` and cascade-delete with their `WorkflowSession` (the optional `WorkflowTask` link is set to `NULL` when that task is deleted). Browse them in the [Approvals](#approvals) admin view.

### Workflow Sessions

Navigate to [http://localhost:3000/admin/workflow-sessions](http://localhost:3000/admin/workflow-sessions) to browse every executed `WorkflowSession`. Each row links to the chat UI (`/workflow-sessions/{id}`) and to the nested **Workflow Tasks** admin page (`/admin/workflow-sessions/{id}/workflow-tasks`) where individual tasks belonging to that session can be created, edited, deleted, and have their status updated inline. The create and edit forms include a **Depends on** picker for selecting which other tasks in the same session a task depends on (its DAG edges); dependencies are shown as a column on the list, and edges that would form a cycle are rejected by the server. The Workflow Tasks page offers a **Table / Graph** toggle: the Graph view renders the task DAG with [React Flow](https://reactflow.dev/), auto-laid-out top-to-bottom with [dagre](https://github.com/dagrejs/dagre) so prerequisites sit above the tasks that depend on them. The graph is read-only (pan / zoom / fit) — dependencies are edited from the task forms.

| Operation | Path |
|-----------|------|
| List all sessions | `GET /admin/workflow-sessions` |
| List a session's tasks | `GET /admin/workflow-sessions/{id}/workflow-tasks` |
| Create a task | `GET /admin/workflow-sessions/{id}/workflow-tasks/new` |
| Edit / delete a task | `GET /admin/workflow-sessions/{id}/workflow-tasks/{taskId}` |

### Approvals

Navigate to [http://localhost:3000/admin/approvals](http://localhost:3000/admin/approvals) to browse every **Approval** request (see [Human approval](#human-approval)). The list shows the title, status (`pending` / `approved` / `rejected`), a link to the originating `/workflow-sessions/{id}` chat, and the creation time, with sort and filter controls. Decisions are normally made from the in-chat Approve / Reject controls; this view is read-only browsing. The `GET`/`PATCH /api/v1/approvals` endpoints are documented in the [API reference](http://localhost:3000/api-doc).

## Notifications

A **bell icon** in the top toolbar (present on both the chat header and the admin sidebar) opens a notification center with an unread-count badge. Notifications are **per-user**, persisted in `a2flow.db`, and delivered by **polling** (the frontend refreshes every 30 seconds).

Two workflow events generate a notification, both raised by the agent's task tools and addressed to the user who started the session:

| Type | Raised when |
|---|---|
| `approval_request` | The agent registers a plan (`register_workflow_tasks`), or requests a mid-execution decision (`request_approval`), and is waiting for human approval. |
| `session_completed` | Every `WorkflowTask` in the session has reached a terminal state (`completed` / `failed` / `skipped`) — emitted once per session. |

Clicking a notification marks it read and deep-links to the relevant `/workflow-sessions/{id}` chat.

The list (`?unreadOnly=true` for unread) and mark-read endpoints are documented in the [API reference](http://localhost:3000/api-doc); both are scoped to the authenticated user, so reading or updating another user's notification returns HTTP 404. Notifications cascade-delete with their recipient user and their linked `WorkflowSession`.

## How it works

1. When the user clicks "+ New session", the frontend navigates to `/newSession` without contacting the backend. The session ID (`threadId`) is generated by the frontend (`crypto.randomUUID()`) at the moment the user submits the first message; the ADK session is created implicitly by the backend on the first `POST /agent` request that references it. The page URL is then replaced with `/sessions/{id}` so the streamed response continues under the canonical session route.
2. When the user submits a message, `createChatAgent()` creates an `HttpAgent` (from `@ag-ui/client`) that sends the auth session cookie (`credentials: "include"`) and the `X-CSRF-Token` header, with `A2UIMiddleware` (from `@ag-ui/a2ui-middleware`) applied. Before each request reaches the backend, the middleware injects the `render_a2ui` tool into `RunAgentInput.tools` and the A2UI Basic Catalog schema (downloaded from `https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json` at build time) into `RunAgentInput.context`.
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

### Interactive API reference

An interactive [Scalar](https://scalar.com/) reference is served at [http://localhost:3000/api-doc](http://localhost:3000/api-doc). It loads the FastAPI app's live OpenAPI document (`/openapi.json`, proxied to the backend by `next.config.ts`), so it always reflects the running backend. The page is behind the same login gate as the rest of the app.

## List query parameters

Every collection endpoint accepts a shared set of `limit` / `offset` / sort (`s`) / filter (`q`) query parameters, with camelCase field names. See [.claude/rules/api-conventions.md](.claude/rules/api-conventions.md) for the full reference.

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
