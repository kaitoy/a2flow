# A2Flow Backend

A Google ADK agent with [A2UI](https://a2ui.org/) support. Accepts prompts via HTTP POST and streams responses as AG-UI SSE events. The agent can return plain text or structured A2UI surfaces for rich UI rendering.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

## A2UI support

A2UI rendering is handled entirely on the frontend by `@ag-ui/a2ui-middleware`. The middleware injects the `render_a2ui` tool into each `RunAgentInput` before it reaches the backend. The backend agent uses `AGUIToolset` (from `ag-ui-adk`) as a placeholder; the `ag-ui-adk` bridge replaces it at runtime with a `ClientProxyToolset` that exposes the frontend-injected tools to the LLM. When the LLM calls `render_a2ui`, the bridge streams `TOOL_CALL_*` events which the middleware converts into `ACTIVITY_SNAPSHOT` events on the client side.

The middleware also sets `forwardedProps.injectA2UITool`, which `ag-ui-adk` 0.7.0+ treats as the opt-in for its own server-side A2UI generation (dropping `render_a2ui` in favour of a `generate_a2ui` sub-agent). A2Flow deliberately opts out: `with_user_id` (`infrastructure/agent.py`) strips the flag so the frontend-rendered path stays in effect. See [docs/a2ui-flow.md](../docs/a2ui-flow.md).

## Setup

```bash
# Install dependencies
cd backend && uv sync

# Create environment file
cp .env.example .env
# Edit backend/.env to configure your API key and model
```

## Configuration

Specify the LLM to use in the `.env` file.

### Gemini (default)

```env
LLM_MODEL=gemini-3.5-flash
GOOGLE_API_KEY=your_google_api_key
```

### OpenAI (via LiteLLM)

```env
LLM_MODEL=litellm:openai/gpt-4o
OPENAI_API_KEY=your_openai_api_key
```

### Anthropic (via LiteLLM)

```env
LLM_MODEL=litellm:anthropic/claude-3-5-sonnet-20241022
ANTHROPIC_API_KEY=your_anthropic_api_key
```

### Agent instruction

```env
AGENT_INSTRUCTION=You are a helpful assistant. Answer concisely and clearly.
```

### Server settings

```env
HOST=0.0.0.0
PORT=8000
# RELOAD=true
```

Defaults to `HOST=0.0.0.0` and `PORT=8000` if omitted. `RELOAD` (default `false`) enables uvicorn autoreload; it only affects `python -m backend.main` — the `uv run uvicorn main:app --reload` command below and the Dockerfile's startup path are unaffected either way.

### Agent skill store

```env
SKILLS_DIR=.skills
# SKILLS_PRUNE_GRACE_SECONDS=3600
# SKILLS_CLONE_TIMEOUT_SECONDS=120
```

Root of the store Agent Skill repositories are shallow-cloned into, laid out as one immutable directory per revision:

```
$SKILLS_DIR/<agent_skill_id>/<commit_sha>/
```

A clone is staged in a temporary sibling and published with a single atomic rename, so no reader ever observes a half-written revision; once published, a revision is never modified. Writers (the clone at registration, and every pull) serialize on the `skill-sync:<id>` advisory lock in `infrastructure/locks.py`. Readers take no lock at all — a pull only adds a sibling directory, so it cannot disturb an agent loading an existing revision.

`SKILLS_PRUNE_GRACE_SECONDS` (default 3600) is how long a revision directory survives regardless of whether anything references it. A pull prunes revisions that no workflow session is pinned to, and the grace window covers the gap between a run reading the skill's current revision and inserting the session row that names it.

`SKILLS_CLONE_TIMEOUT_SECONDS` (default 120) bounds how long a clone's individual HTTP requests may take. Without it, a slow or hanging remote could stall a clone indefinitely — and with it, the skill's sync advisory lock, leaving the skill `pending` and making a pull of it on another replica silently skip rather than wait.

Defaults to `backend/.skills` (relative to the working directory). Under `docker compose` it is `/var/lib/a2flow/skills`, backed by the `skills` named volume.

This is **durable state, not a cache**: a `WorkflowSession` pins the revision it started with, so wiping the directory leaves existing sessions unable to load their skill (HTTP 409 `SKILL_NOT_READY`) until an admin pulls the skill again. Running more than one backend replica requires all of them to mount this same directory.

### Secret management

```env
# SECRET_ENCRYPTION_KEY=
# SECRET_KEY_FILE=.secret_key
# VAULT_ADDR=https://vault.example.com
# VAULT_TOKEN=hvs.xxxxxxxx
# VAULT_ROLE_ID=...
# VAULT_SECRET_ID=...
# VAULT_APPROLE_MOUNT=approle
```

`local`-type [secrets](#secrets) are Fernet-encrypted before storage. The key is resolved at first use: `SECRET_ENCRYPTION_KEY` (must be a valid Fernet key) takes precedence; otherwise the key file at `SECRET_KEY_FILE` (default `.secret_key` next to the SQLite database file) is read; otherwise a key is generated, saved to that file, and a WARNING is logged. Back the key up — losing it makes every stored local secret undecryptable.

`vault`-type secrets are read live from a single HashiCorp Vault (KV v2 only) selected by `VAULT_ADDR`. Authentication uses AppRole (`VAULT_ROLE_ID` + `VAULT_SECRET_ID`, login mount from `VAULT_APPROLE_MOUNT`) when set, else the static `VAULT_TOKEN`. `VAULT_ADDR` is deliberately exempt from the SSRF URL checks applied to user-supplied URLs: it is operator-set deployment configuration and typically points at a private address.

### Application database

```env
DB_URL=sqlite:///a2flow.db
# DB_URL=postgresql://user:password@localhost:5432/a2flow
```

Database URL for REST API data and ADK session storage — both live in the same database. SQLite (the default, relative to the working directory) and PostgreSQL are supported; the async driver suffix (`sqlite+aiosqlite` / `postgresql+asyncpg`) is added automatically, so the plain scheme is enough. With SQLite the ADK session store uses `SqliteSessionService`; any other URL switches it to the SQLAlchemy-based `DatabaseSessionService`. Schema changes are tracked as versioned [Alembic](https://alembic.sqlalchemy.org/) migrations under `alembic/versions/` and applied automatically (`alembic upgrade head`) on startup, so redeploying the app is what brings the schema up to date. To add a migration after changing a model, run `uv run alembic revision --autogenerate -m "..."` and review the generated file before committing.

| Table | Description |
|---|---|
| `users` | Application users (soft-deleted via `deleted_at`; `roles` holds their granted roles); see [Admin user](#admin-user) and [Authorization](#authorization-roles) |
| `auth_sessions` | Server-side login sessions (hashed cookie token + CSRF token); see [Authentication](#authentication) |
| `agent_skills` | Agent skill definitions (incl. optional `repo_auth_secret` / `repo_auth_username` for private-repo clones) |
| `mcp_servers` | Registered remote MCP servers (name, streamable HTTP URL, request headers — values may embed `${secret:NAME}` placeholders) |
| `secrets` | Named credentials: Fernet-encrypted local values or HashiCorp Vault KV v2 references; see [Secrets](#secrets) |
| `workflows` | Workflow definitions |
| `workflow_tasks` | Individual tasks belonging to a `WorkflowSession` (`workflow_session_id` FK with `ON DELETE CASCADE`) |
| `workflow_task_tool_bindings` | MCP tools bound to a task (`task_id` FK `ON DELETE CASCADE`, `mcp_server_id` FK `ON DELETE RESTRICT`) |
| `sessions` | Session metadata and session-level state |
| `events` | Full event history per session (JSON) |
| `app_states` | App-level shared state |
| `user_states` | Per-user state shared across sessions |

### Horizontal scaling

Running more than one backend replica requires PostgreSQL (SQLite is single-writer and single-process). All replicas then share one database, which is also what coordinates them.

Writes to an ADK session are already safe across replicas: google-adk's `DatabaseSessionService.append_event` takes `SELECT ... FOR UPDATE` on the session row for the whole append transaction, so appends to one session are serialized and neither the session state nor the event rows can be lost.

Reads are the part that needs help. The ADK `Runner` holds one in-memory session for the length of an invocation, so events another replica appends during that window never reach it, and the rest of the run reasons over a conversation that is missing them. Serializing writes cannot repair that — only keeping a session to one driver at a time can. So `POST /api/v1/agent` takes a **PostgreSQL session-level advisory lock** (`infrastructure/locks.py`) keyed on `app_name:user_id:thread_id` and holds it for the whole SSE stream. A second concurrent run of the same session is refused with HTTP 409 `SESSION_RUN_IN_PROGRESS` before any SSE headers are sent, rather than being left to diverge quietly. Different sessions never contend, and the lock is briefly waited on before it gives up, so a client that aborts a stream and immediately retries is not rejected while the abandoned run is still tearing down.

Because the lock is session-level (not transaction-level), the deployment must not place a **transaction-pooling** proxy — PgBouncer in `transaction` mode, and most serverless PostgreSQL poolers — between the app and PostgreSQL; the lock would not survive between statements. Session-level pooling (or a direct connection) is required.

Human-in-the-loop is unaffected: a frontend tool call ends the run and closes the stream, releasing the lock, and the approval resumes as a *new* `POST /agent` that may land on any replica.

### Reverse proxy / load balancer

**Sticky sessions / session affinity are not required.** See "Horizontal
scaling" above — the PostgreSQL advisory lock, not routing affinity, is what
keeps one ADK session pinned to one driver at a time, and only for the
duration of a single SSE stream.

The two SSE routes (`POST /api/v1/agent`, `POST /api/v1/workflow-sessions/{id}/agent`)
need the following at the reverse proxy / load balancer layer:

- **Disable response buffering** for these paths. The app already sends
  `X-Accel-Buffering: no` on both, which nginx honors per-response even if
  buffering is enabled globally; other proxies/LBs need buffering disabled at
  the config level instead (e.g. nginx's own `proxy_buffering off;`, since
  `X-Accel-Buffering` only covers nginx).
- **Disable gzip/compression for `text/event-stream`.** The app itself never
  compresses responses (no `GZipMiddleware` is registered), so any
  compression seen by the client can only come from the LB/proxy layer —
  make sure it excludes `text/event-stream`.
- **Size the read/idle timeout generously.** Agent runs have no server-side
  time limit today (no `session_timeout_seconds`, nothing wraps the run in a
  timeout), so a proxy-level read timeout is the only thing that can end a
  stream, and it will silently cut off a legitimate long-running response if
  set too low. Set it well above the longest run you expect, not a "typical"
  request timeout.
- **uvicorn's graceful-shutdown grace period is 30s** (`--timeout-graceful-shutdown`,
  set in `Dockerfile`'s `CMD`). A rolling deploy forcibly ends any SSE stream
  still open 30s after the container receives SIGTERM; this is safe because
  the advisory lock releases with the connection and the client resumes with
  a fresh request, the same way an abandoned/disconnected stream already
  behaves.

### Admin user

On startup the backend seeds two users:

- A hidden **system user** that owns the bootstrap records (it cannot log in and is excluded from the user list).
- An initial **`admin`** user holding the **`super_admin`** role (see [Authorization](#authorization-roles)), created only on the very first startup — that is, while the database has no real (non-system) user yet. Once any real user exists it is never re-created.

The `admin` user's password is read from the `ADMIN_PASSWORD` environment variable:

```env
ADMIN_PASSWORD=change-me-now-123
```

If unset (or empty), a random password is generated instead and logged **once**, at `WARNING` level, when the admin user is created — it is tied to the same first-startup-only bootstrap, so it is never regenerated on a later restart, and it cannot be recovered once the log line has scrolled past. Set `ADMIN_PASSWORD` explicitly before the first run for anything beyond local experimentation, or capture the generated password from the startup logs immediately and change it through the user API afterwards. The username is fixed to `admin`.

### Authentication

All API routes except `POST /api/v1/auth/login` and `GET /api/v1/health` require an authenticated session. Authentication is cookie-based and backed by the `auth_sessions` table.

**Flow**

1. `POST /api/v1/auth/login` with `{ "username", "password" }`. On success the response sets two cookies and returns the current user (without the password hash):
   - `a2flow_session` — HttpOnly, `SameSite=Lax` opaque session token. Only its SHA-256 hash is stored server-side.
   - `a2flow_csrf` — readable (non-HttpOnly), `SameSite=Lax` CSRF token.
2. The browser sends both cookies automatically on subsequent requests. For state-changing requests (`POST`/`PUT`/`PATCH`/`DELETE`) the client must echo the CSRF cookie value in the `X-CSRF-Token` header (double-submit cookie defense). A mismatch or missing header returns `403 CSRF_FAILED`.
3. `GET /api/v1/auth/me` returns the current user; `POST /api/v1/auth/logout` revokes the session and clears the cookies.

A missing or invalid session returns `401 UNAUTHENTICATED`.

**Session lifetime**

Sessions use a sliding idle timeout: each authenticated request refreshes the session's last-active time, and a session left idle longer than `SESSION_IDLE_TIMEOUT_SECONDS` (default `28800`, 8 hours) is rejected and deleted. The cookies themselves are session cookies (no `Max-Age`/`Expires`), so they are also cleared when the browser closes.

```env
# Sliding idle timeout in seconds (default 28800 = 8 hours)
SESSION_IDLE_TIMEOUT_SECONDS=28800
# Mark cookies Secure (HTTPS only); leave false for local HTTP dev (default false)
SESSION_COOKIE_SECURE=false
```

The frontend reaches the backend through a same-origin Next.js rewrite (`/api/*`), so the cookies are first-party and `SameSite=Lax` applies cleanly. Log in with the seeded `admin` user (see [Admin user](#admin-user)) on first run.

### Authorization (roles)

Authenticated users additionally hold **roles** (`users.roles`, a JSON list of `super_admin` / `admin` / `developer` / `requester` / `approver`) that gate the write endpoints. `super_admin` bypasses every route-level role gate; the seeded `admin` user holds it. Two ownership-layer checks are a deliberate exception — see the bullet below. See the [Roles and authorization](../README.md#roles-and-authorization) section of the root README for the full matrix.

Two enforcement points:

- **Route dependency** — `require_roles(...)` (`dependencies/authz.py`) is attached per route (e.g. `dependencies=[Depends(require_roles(Role.developer))]`) on the create/update/delete handlers and on `POST /workflows/{id}/execute`. `GET` routes are not gated.
- **Service layer** — ownership rules that a role cannot express: self-service user/avatar edits (`services/user.py`, `services/user_avatar.py`), the `super_admin` grant/revoke guard, the designated-approver check (`services/approval.py`), `WorkflowTaskService.update`'s status-change guard (`services/workflow_task.py`: changing a task's `status` is restricted to the session owner or, when the task has a linked `Approval`, that Approval's designated approver), and the workflow-session access policy (`services/workflow_session_access.py`: owner, a designated approver of the session, or a super admin; deletion is owner-only). The designated-approver and status-change checks intentionally exclude `super_admin` — no exception, not even for a super admin who isn't the addressee.

Both raise `ForbiddenError` → HTTP 403 `FORBIDDEN`.

### CORS

```env
CORS_ORIGINS=http://localhost:3000
```

Comma-separated list of origins allowed to call `/chat` and `/sessions`. Defaults to `http://localhost:3000`. Add additional origins when the frontend is served from a different host or port:

```env
CORS_ORIGINS=https://app.example.com,http://localhost:3000
```

`*` is rejected at startup — `allow_credentials=True` is always enabled, and pairing it with a wildcard origin is invalid per the CORS spec.

## Development

For conventions on adding new models, repositories, services, and routers, see [.claude/rules/backend-patterns.md](../.claude/rules/backend-patterns.md).

## Running

```bash
cd backend && uv run uvicorn main:app --reload
```

## Testing

```bash
cd backend && uv run pytest
```

No LLM API keys are required to run the tests. Pass `-v` for verbose output:

```bash
cd backend && uv run pytest -v
```

## API

All REST endpoints are documented interactively by the [Scalar API reference](http://localhost:3000/api-doc) (frontend route `/api-doc`), generated from the live OpenAPI spec — paths, request/response schemas, status codes, and a built-in "Test Request" console stay in sync with the running backend automatically. This section does not repeat those per-endpoint signatures; it covers only what the spec does not capture: the conventions shared by every endpoint, each resource's business rules, and the two surfaces intentionally **excluded** from the spec — the agent's AG-UI streaming endpoint and the agent's function tools.

### Conventions

- **Base path** — every REST endpoint is served under `/api/v1` (e.g. `GET /api/v1/agent-skills`).
- **Identity** — the caller is resolved from the authenticated `a2flow_session` cookie (see [Authentication](#authentication)); calling a protected endpoint with `curl` needs a logged-in cookie jar saved with `curl -c`/`-b`.
- **CSRF** — state-changing requests (`POST` / `PATCH` / `DELETE`) must echo the `a2flow_csrf` cookie in the `X-CSRF-Token` header.
- **List parameters** — collection endpoints accept shared `limit` / `offset` / sort (`s`) / filter (`q`) query parameters with camelCase field names.
- **Envelope** — JSON responses are wrapped in a uniform `{meta, data, error}` shape by middleware (the `POST /agent` SSE stream and `GET /health` are excluded).

### Session management

Sessions are created lazily: the backend ADK session is materialized on the first `POST /agent` request that supplies a fresh `threadId`. The client picks the UUID, and that same UUID is reused on subsequent requests to preserve conversation history. **There is no explicit "create session" endpoint.** The list / get / messages / delete endpoints are in the [API reference](http://localhost:3000/api-doc).

---

### Agent skills

Agent skills are reusable skill definitions that can be attached to workflows. Each record stores a unique `name`, a Git `repoUrl`, an optional `repoPath` (default `""`), and an optional `description`. Deleting a skill that is still referenced by one or more workflows returns `409 CONFLICT_REFERENCED`. CRUD endpoints are in the [API reference](http://localhost:3000/api-doc).

Private repositories are supported through the optional `repoAuthSecret` field — the **name** of a registered [secret](#secrets) whose value is used as the HTTP basic-auth password for the clone — plus `repoAuthUsername` (default `x-access-token`, which suits GitHub PATs). Create/update validates that the named secret exists (`422 FOREIGN_KEY_VIOLATION` otherwise), but the reference is by name and resolved lazily at clone time: a later rename or delete of the secret makes the next clone fail with `502 SECRET_RESOLUTION_FAILED`.

The content at `repoUrl`/`repoPath` (e.g. `SKILL.md`) is loaded directly into the workflow agent's LLM prompt, unsandboxed — only register repositories you trust, since their content is effectively an instruction to the agent, not inert data.

---

### MCP servers

A registry of remote [MCP](https://modelcontextprotocol.io/) servers whose tools the workflow agent can bind to WorkflowTasks. Connections use **streamable HTTP** only (SSE-transport servers are not supported). The optional `headers` map (e.g. `{"Authorization": "Bearer …"}`) is sent with every request to the server. Literal header values are stored in plaintext; to keep a credential out of the record, embed a `${secret:NAME}` placeholder referencing a registered [secret](#secrets) — placeholders are expanded only when connecting, and a reference that no longer resolves fails the connection attempt (`502 SECRET_RESOLUTION_FAILED` on the REST path; a per-server `error` entry for the agent's `list_mcp_tools`/`call_mcp_tool` proxies).

The CRUD endpoints are in the [API reference](http://localhost:3000/api-doc). On create, `name` and `url` are required and `headers` defaults to `{}`; a duplicate name returns `409 CONFLICT_UNIQUE`. On update, sending `headers` replaces the full map while omitting it leaves it unchanged. Two behaviors are worth calling out: `GET /api/v1/mcp-servers/{id}/tools` connects to the remote server live and returns its advertised tools (`name`, `description`, `inputSchema`), or `502 MCP_UNREACHABLE` if it cannot be reached within the 30-second timeout; and a server cannot be deleted while WorkflowTask tool bindings still reference it (`409 CONFLICT_REFERENCED`).

`GET /api/v1/mcp-registry` proxies the official [MCP registry](https://registry.modelcontextprotocol.io/) for server discovery. It accepts `search` (substring matched against server names) and `cursor` (pagination) query params and returns `{ servers, nextCursor }`, where each server is flattened to the fields A2Flow can use — only servers exposing a streamable-HTTP remote are included, since that is the only transport supported. The registry base URL is configurable via the `MCP_REGISTRY_URL` env var (default `https://registry.modelcontextprotocol.io`); a registry that cannot be reached returns `502 REGISTRY_UNREACHABLE`. Registration itself reuses the ordinary `POST /api/v1/mcp-servers` create flow from a pre-filled admin form.

---

### Secrets

Named credentials consumed by MCP server header placeholders and agent-skill repository clones. Each secret is either `local` — the submitted `value` is Fernet-encrypted with the key described in [Secret management](#secret-management) and stored in the `secrets` table — or `vault` — only a KV v2 reference (`vaultMount`, `vaultPath`, `vaultKey`) is stored and the value is read from HashiCorp Vault at resolution time.

The API is **write-only for values**: create/update accept a plaintext `value`, but every response uses a read view with no `value` field at all, so neither the plaintext nor the ciphertext is ever serialized to clients. On update, omitting `value` keeps the stored ciphertext; switching `type` clears the other shape's fields, and a PATCH that would leave an invalid merged shape (e.g. a `vault` secret with a `value`) returns `422 INVALID_SECRET`. Names are unique (`409 CONFLICT_UNIQUE`), use the slug charset (letters, digits, `.`, `_`, `-`), and are what placeholders and `repoAuthSecret` reference — deletion is never blocked by references; dangling ones fail at their next resolution with `502 SECRET_RESOLUTION_FAILED` (the failure reason is logged server-side only). CRUD endpoints are in the [API reference](http://localhost:3000/api-doc).

---

### Workflows

A workflow pairs a prompt with an agent skill. Each workflow references exactly one agent skill; a single agent skill may be used by multiple workflows.

A workflow requires a unique `name`, a `prompt`, and an `agentSkillId`; `description` is optional. The CRUD endpoints are in the [API reference](http://localhost:3000/api-doc). Executing a workflow — `POST /api/v1/workflows/{id}/execute` — snapshots its configuration into a new `WorkflowSession` (see below).

---

### Workflow sessions

A `WorkflowSession` is the snapshot record created when a workflow is executed via `POST /workflows/{id}/execute`. The chat experience is exposed at `POST /workflow-sessions/{id}/agent` (streaming) and the session metadata is fetched via `GET /workflow-sessions/{id}`. A list endpoint enables the admin UI to browse all executed sessions ordered by most recent first.

The list (ordered most-recent-first) and get endpoints are in the [API reference](http://localhost:3000/api-doc).

---

### Workflow tasks

A workflow task is a single actionable item belonging to a `WorkflowSession`. The skill-driven workflow agent registers and drives these tasks itself via [agent tools](#agent-task-tools); they are also exposed through the REST endpoints below. Each task carries a `status` (`pending` | `in_progress` | `completed` | `failed` | `skipped`) and an integer `position` used for stable layout ordering within a session. Deleting the parent `WorkflowSession` cascades to its tasks.

Tasks form a **directed acyclic graph (DAG)**: each task may depend on other tasks in the same session through its `dependsOnIds` list (persisted as `(task_id, depends_on_id)` rows in the `workflow_task_dependencies` join table, where `depends_on_id` must precede `task_id`). Read responses include the resolved `dependsOnIds`. Dependency targets must exist and belong to the same session, otherwise the write fails with `422 FOREIGN_KEY_VIOLATION`; edges that would introduce a cycle — including a self-dependency — fail with `409 DEPENDENCY_CYCLE`. Deleting a task cascade-deletes the edges that reference it in either direction.

Tasks may additionally bind **MCP tools** from [registered MCP servers](#mcp-servers) through their `toolBindings` list (`[{"mcpServerId": …, "toolName": …}]`, persisted in the `workflow_task_tool_bindings` join table). Read responses include the resolved `toolBindings`. Every bound `mcpServerId` must reference a registered server, otherwise the write fails with `422 FOREIGN_KEY_VIOLATION`; duplicates are deduplicated. Bindings cascade-delete with their task, while a referenced MCP server cannot be deleted (`409 CONFLICT_REFERENCED`). At execution time the agent may only invoke bound tools via the `call_mcp_tool` proxy (see [Agent task tools](#agent-task-tools)).

#### Agent task tools

When a workflow runs, the skill-bound agent is given function tools so it can plan and drive the task DAG itself, request human approval, and call MCP tools, in addition to the REST endpoints below. The agent runs a **plan-then-execute** flow: it registers the plan, waits for the user's approval, then iterates the tasks updating their status.

| Tool | Purpose |
|---|---|
| `register_workflow_tasks` | Register a whole plan as a DAG in one call (each entry has a `key`, `title`, optional `depends_on` referencing other keys, optional `tools` binding MCP tools) |
| `create_workflow_task` | Add a single task, optionally referencing existing task ids as dependencies and binding MCP tools |
| `list_workflow_tasks` | List the current session's tasks (id, title, status, `dependsOnIds`, position, `tool_bindings`) |
| `get_workflow_task` | Fetch one task in the current session |
| `update_workflow_task` | Change a task's title / description / status / position / dependencies / tool bindings |
| `delete_workflow_task` | Delete a task |
| `request_approval` | Create a `pending` [Approval](#approvals) for the current session (optionally linked to a task) and raise an `approval_request` notification; returns the `approval_id` to pass to the client-side `render_approval` tool |
| `get_approval` | Fetch the current state of an approval in the current session (to re-check a decision) |
| `list_users` | List the registered users (id, username, name, email; system and soft-deleted users excluded) so the agent can choose an `approver` id for `request_approval` |
| `list_mcp_tools` | Discover the tools advertised by every [registered MCP server](#mcp-servers) (queried live and concurrently; per-server failures are isolated) |
| `call_mcp_tool` | Invoke an MCP tool bound to the task currently `in_progress`; calls to unbound tools are rejected with an error listing the allowed tools |

The tools resolve the current session by mapping the ADK session id (the AG-UI thread id, stored on `WorkflowSession.session_id`) back to the `WorkflowSession` primary key, and they reject access to records belonging to other sessions. They live in `infrastructure/workflow_task_tools.py`, `infrastructure/approval_tools.py`, and `infrastructure/mcp_tools.py` and are attached to the agent in `infrastructure/agent.py` only when a skill is bound. `call_mcp_tool` opens one streamable HTTP connection per call (30-second timeout) through the shared adapter in `infrastructure/mcp_client.py`.

The approver's actual approve/reject decision is written from the frontend via `PATCH /api/v1/approvals/{id}` (not an agent tool), and surfaces to the agent as the result of the client-side `render_approval` tool. See [Approvals](#approvals).

The task CRUD endpoints — create, list-for-a-session (ordered `position` ASC then `created_at` ASC), get, update, delete — are in the [API reference](http://localhost:3000/api-doc). A few rules the spec does not spell out: `workflowSessionId` is fixed at creation and a task cannot be re-parented; sending `dependsOnIds` or `toolBindings` replaces that full set while omitting either leaves it unchanged; and the `422 FOREIGN_KEY_VIOLATION` (unknown session, cross-session dependency, or unregistered MCP server) / `409 DEPENDENCY_CYCLE` validation applies to both create and update.

---

### Notifications

Per-user notifications surfaced in the frontend's toolbar bell. Notifications are generated as a side effect of the agent's task tools — `register_workflow_tasks` raises an `approval_request`, and the final `update_workflow_task` that drives every task to a terminal state raises a one-shot `session_completed` — and are addressed to the user who started the workflow session. Both endpoints below are scoped to the authenticated user; the list never accepts a `user_id`, and reading or marking another user's notification returns `404 NOT_FOUND`.

Each notification stores a `type` (`approval_request` / `session_completed`), `title`, optional `body`, the linked `workflowSessionId`, and a `read` flag. Rows cascade-delete with their recipient user and their linked `WorkflowSession`.

---

### Approvals

A human-in-the-loop decision the workflow agent asks for mid-execution. The agent creates a `pending` Approval with the `request_approval` [agent tool](#agent-task-tools) (which also raises an `approval_request` notification), then calls the client-side `render_approval` tool to show Approve / Reject controls. The frontend writes the decision back via `PATCH /api/v1/approvals/{approval_id}`, which records the requesting user as the approver in the audit fields.

Each approval stores `workflowSessionId` (FK, `ON DELETE CASCADE`), an optional `workflowTaskId` (FK, `ON DELETE SET NULL`), a `title`, optional `description`, a `status` (`pending` / `approved` / `rejected`), and an optional `response` comment. The `GET /api/v1/approvals` (list, with the shared pagination / sort / filter query params) and `GET` / `PATCH /api/v1/approvals/{id}` endpoints are in the [API reference](http://localhost:3000/api-doc). Fetching a missing approval returns `404 NOT_FOUND`.

Both endpoints — list (ordered `created_at` DESC, `?unreadOnly=true` for the bell's unread badge) and mark-read — are in the [API reference](http://localhost:3000/api-doc). Reading or marking another user's notification returns `404 NOT_FOUND`.

---

### Agent streaming — `POST /api/v1/agent`

This endpoint and its per-skill variant `POST /api/v1/workflow-sessions/{id}/agent` are marked `include_in_schema=False`, so they are **not** in the [API reference](http://localhost:3000/api-doc) and are documented here instead.

Send an [AG-UI `RunAgentInput`](https://docs.ag-ui.com/concepts/events) to a session and receive the agent's response as an SSE stream. If no ADK session exists for the provided `threadId`, one is created implicitly.

**Request body** (AG-UI standard format, camelCase)

| Field | Type | Required | Description |
|---|---|---|---|
| `threadId` | string | Yes | Session ID (a UUID generated by the client; sessions are created lazily on first use) |
| `messages` | array | Yes | Message list; the last `role: "user"` entry is used as the prompt |
| `runId` | string | No | Run ID (auto-generated UUID if omitted) |
| `tools` | array | No | Tool definitions (currently unused) |
| `context` | array | No | Context items (currently unused) |
| `state` | any | No | Agent state (currently unused) |

The caller's identity is resolved from the authenticated session cookie (same convention as the REST endpoints). As a `POST`, this endpoint also requires the `X-CSRF-Token` header.

Reusing the same `threadId` preserves conversation history.

Only one run of a given session may be in flight at a time. A request for a `threadId` that is already streaming — including from another backend replica — is refused with HTTP 409 `SESSION_RUN_IN_PROGRESS` before any SSE headers are sent, so the caller gets a normal JSON error envelope rather than a broken stream. See [Horizontal scaling](#horizontal-scaling).

**SSE response (AG-UI event sequence)**

Text response:

```
data: {"type":"RUN_STARTED","threadId":"<threadId>","runId":"<runId>"}

data: {"type":"TEXT_MESSAGE_START","messageId":"<id>","role":"assistant"}

data: {"type":"TEXT_MESSAGE_CONTENT","messageId":"<id>","delta":"chunk of response text"}

data: {"type":"TEXT_MESSAGE_END","messageId":"<id>"}

data: {"type":"RUN_FINISHED","threadId":"<threadId>","runId":"<runId>"}
```

A2UI response (when the agent calls `send_a2ui_json_to_client`):

```
data: {"type":"RUN_STARTED","threadId":"<threadId>","runId":"<runId>"}

data: {"type":"TOOL_CALL_START","toolCallId":"<id>","toolName":"send_a2ui_json_to_client"}

data: {"type":"TOOL_CALL_ARGS","toolCallId":"<id>","delta":"...A2UI JSON..."}

data: {"type":"TOOL_CALL_END","toolCallId":"<id>"}

data: {"type":"RUN_FINISHED","threadId":"<threadId>","runId":"<runId>"}
```

On error:

```
data: {"type":"RUN_ERROR","message":"error description"}
```

**curl example**

```bash
# Generate a thread/session ID once and reuse it on subsequent requests to keep the conversation in the same session.
SESSION=$(python -c 'import uuid; print(uuid.uuid4())')

curl -N -X POST http://localhost:8000/api/v1/agent \
  -H "Content-Type: application/json" \
  -b cookies.txt -H "X-CSRF-Token: $CSRF" \
  -d "{\"threadId\": \"$SESSION\", \"runId\": \"$(python -c 'import uuid; print(uuid.uuid4())')\", \"state\": {}, \"tools\": [], \"context\": [], \"messages\": [{\"id\": \"m1\", \"role\": \"user\", \"content\": \"What is Python?\"}], \"forwardedProps\": {}}"
```

---

### `GET /api/v1/health`

Health check — checks database connectivity (`SELECT 1`) and returns `200
{"status": "ok"}` or `503 {"status": "unavailable"}`, outside the response
envelope. Used for both liveness and readiness gating (e.g. a Kubernetes
probe, or `compose.yml`'s `backend` service `healthcheck:`). Polled
frequently, so it's excluded from the uvicorn access log (see
`infrastructure/logging_context.py`).

```bash
curl -i http://localhost:8000/api/v1/health
# 200 {"status": "ok"}
```
