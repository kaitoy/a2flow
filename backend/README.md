# A2Flow Backend

A Google ADK agent with [A2UI](https://a2ui.org/) support. Accepts prompts via HTTP POST and streams responses as AG-UI SSE events. The agent can return plain text or structured A2UI surfaces for rich UI rendering.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

## A2UI support

A2UI rendering is handled entirely on the frontend by `@ag-ui/a2ui-middleware`. The middleware injects the `render_a2ui` tool into each `RunAgentInput` before it reaches the backend. The backend agent uses `AGUIToolset` (from `ag-ui-adk`) as a placeholder; the `ag-ui-adk` bridge replaces it at runtime with a `ClientProxyToolset` that exposes the frontend-injected tools to the LLM. When the LLM calls `render_a2ui`, the bridge streams `TOOL_CALL_*` events which the middleware converts into `ACTIVITY_SNAPSHOT` events on the client side.

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
LLM_MODEL=gemini-2.0-flash
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
```

Defaults to `HOST=0.0.0.0` and `PORT=8000` if omitted.

### Application database

```env
DB_URL=sqlite:///a2flow.db
```

SQLite URL for REST API data and ADK session storage. Both the SQLModel async engine and `SqliteSessionService` open the same file. Defaults to `sqlite:///a2flow.db` (relative to the working directory). The database and tables are created automatically on first run.

| Table | Description |
|---|---|
| `users` | Application users (soft-deleted via `deleted_at`); see [Admin user](#admin-user) |
| `auth_sessions` | Server-side login sessions (hashed cookie token + CSRF token); see [Authentication](#authentication) |
| `agent_skills` | Agent skill definitions |
| `mcp_servers` | Registered remote MCP servers (name, streamable HTTP URL, plaintext request headers) |
| `workflows` | Workflow definitions |
| `workflow_tasks` | Individual tasks belonging to a `WorkflowSession` (`workflow_session_id` FK with `ON DELETE CASCADE`) |
| `workflow_task_tool_bindings` | MCP tools bound to a task (`task_id` FK `ON DELETE CASCADE`, `mcp_server_id` FK `ON DELETE RESTRICT`) |
| `sessions` | Session metadata and session-level state |
| `events` | Full event history per session (JSON) |
| `app_states` | App-level shared state |
| `user_states` | Per-user state shared across sessions |

### Admin user

On startup the backend seeds two users:

- A hidden **system user** that owns the bootstrap records (it cannot log in and is excluded from the user list).
- An initial **`admin`** user, created only on the very first startup — that is, while the database has no real (non-system) user yet. Once any real user exists it is never re-created.

The `admin` user's password is read from the `ADMIN_PASSWORD` environment variable, falling back to `admin12345678` when unset:

```env
ADMIN_PASSWORD=change-me-now-123
```

The username is fixed to `admin`. Set `ADMIN_PASSWORD` before the first run, or change the password through the user API afterwards.

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

### CORS

```env
CORS_ORIGINS=http://localhost:3000
```

Comma-separated list of origins allowed to call `/chat` and `/sessions`. Defaults to `http://localhost:3000`. Add additional origins when the frontend is served from a different host or port:

```env
CORS_ORIGINS=https://app.example.com,http://localhost:3000
```

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

### Session management

Sessions are created lazily: the backend ADK session is materialized on the first `POST /agent` request that supplies a fresh `threadId`. The client picks the UUID, and that same UUID is reused on subsequent requests to preserve conversation history. There is no explicit "create session" endpoint.

The caller's identity is resolved from the authenticated session cookie (see [Authentication](#authentication)); the examples below assume a logged-in cookie jar saved with `curl -c`/`-b`.

#### `GET /sessions` — List sessions

```bash
curl -b cookies.txt "http://localhost:8000/api/v1/sessions"
```

#### `GET /sessions/{session_id}` — Get a session

```bash
curl -b cookies.txt "http://localhost:8000/api/v1/sessions/my-session"
```

Returns `404` if the session does not exist or belongs to a different user.

#### `GET /sessions/{session_id}/messages` — Get session messages

```bash
curl -b cookies.txt "http://localhost:8000/api/v1/sessions/my-session/messages"
```

#### `DELETE /sessions/{session_id}` — Delete a session

Requires the `X-CSRF-Token` header (see [Authentication](#authentication)).

```bash
curl -X DELETE -b cookies.txt -H "X-CSRF-Token: $CSRF" "http://localhost:8000/api/v1/sessions/my-session"
```

---

### Agent skills

Agent skills are reusable skill definitions (name, repository URL, description) that can be attached to workflows.

#### `POST /agent-skills` — Create an agent skill

```bash
curl -X POST http://localhost:8000/agent-skills \
  -H "Content-Type: application/json" \
  -d '{"name": "my-skill", "repo_url": "https://github.com/example/skill"}'
```

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Unique skill name |
| `repo_url` | string | Yes | Git repository URL |
| `repo_path` | string | No | Path within the repository (default: `""`) |
| `description` | string | No | Human-readable description |

#### `GET /agent-skills` — List agent skills

```bash
curl "http://localhost:8000/agent-skills?limit=20&offset=0"
```

#### `GET /agent-skills/{skill_id}` — Get an agent skill

```bash
curl http://localhost:8000/agent-skills/<id>
```

#### `PATCH /agent-skills/{skill_id}` — Update an agent skill

```bash
curl -X PATCH http://localhost:8000/agent-skills/<id> \
  -H "Content-Type: application/json" \
  -d '{"description": "updated description"}'
```

#### `DELETE /agent-skills/{skill_id}` — Delete an agent skill

Returns `204 No Content`. Returns `409 Conflict` if the skill is referenced by one or more workflows.

```bash
curl -X DELETE http://localhost:8000/agent-skills/<id>
```

---

### MCP servers

A registry of remote [MCP](https://modelcontextprotocol.io/) servers whose tools the workflow agent can bind to WorkflowTasks. Connections use **streamable HTTP** only (SSE-transport servers are not supported). The optional `headers` map (e.g. `{"Authorization": "Bearer …"}`) is sent verbatim with every request to the server and is stored **in plaintext**.

#### `POST /api/v1/mcp-servers` — Register an MCP server

```bash
curl -X POST http://localhost:8000/api/v1/mcp-servers \
  -H "Content-Type: application/json" \
  -d '{"name": "web-search", "url": "https://mcp.example.com/mcp", "headers": {"Authorization": "Bearer token"}}'
```

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Unique server name |
| `url` | string | Yes | Streamable HTTP endpoint URL |
| `headers` | object | No | HTTP headers sent with every request (default: `{}`) |

Returns `409 CONFLICT_UNIQUE` on a duplicate name.

#### `GET /api/v1/mcp-servers` — List MCP servers

```bash
curl "http://localhost:8000/api/v1/mcp-servers?limit=20&offset=0"
```

#### `GET /api/v1/mcp-servers/{server_id}` — Get an MCP server

```bash
curl http://localhost:8000/api/v1/mcp-servers/<id>
```

#### `GET /api/v1/mcp-servers/{server_id}/tools` — List the server's advertised tools

Connects to the remote server and returns the tools it advertises (`name`, `description`, `inputSchema`). Returns `502 MCP_UNREACHABLE` when the server cannot be reached within the 30-second timeout.

```bash
curl http://localhost:8000/api/v1/mcp-servers/<id>/tools
```

#### `PATCH /api/v1/mcp-servers/{server_id}` — Update an MCP server

Sending `headers` replaces the full header map; omitting it leaves the headers unchanged.

```bash
curl -X PATCH http://localhost:8000/api/v1/mcp-servers/<id> \
  -H "Content-Type: application/json" \
  -d '{"headers": {"Authorization": "Bearer new-token"}}'
```

#### `DELETE /api/v1/mcp-servers/{server_id}` — Delete an MCP server

Returns `409 CONFLICT_REFERENCED` while WorkflowTask tool bindings still reference the server.

```bash
curl -X DELETE http://localhost:8000/api/v1/mcp-servers/<id>
```

---

### Workflows

A workflow pairs a prompt with an agent skill. Each workflow references exactly one agent skill; a single agent skill may be used by multiple workflows.

#### `POST /workflows` — Create a workflow

```bash
curl -X POST http://localhost:8000/workflows \
  -H "Content-Type: application/json" \
  -d '{"name": "my-workflow", "prompt": "Do the thing", "agent_skill_id": "<skill_id>"}'
```

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Unique workflow name |
| `prompt` | string | Yes | Prompt text executed by the workflow |
| `agent_skill_id` | string | Yes | ID of the agent skill to use |
| `description` | string | No | Human-readable description |

#### `GET /workflows` — List workflows

```bash
curl "http://localhost:8000/workflows?limit=20&offset=0"
```

#### `GET /workflows/{workflow_id}` — Get a workflow

```bash
curl http://localhost:8000/workflows/<id>
```

#### `PATCH /workflows/{workflow_id}` — Update a workflow

```bash
curl -X PATCH http://localhost:8000/workflows/<id> \
  -H "Content-Type: application/json" \
  -d '{"prompt": "new prompt"}'
```

#### `DELETE /workflows/{workflow_id}` — Delete a workflow

Returns `204 No Content`.

```bash
curl -X DELETE http://localhost:8000/workflows/<id>
```

---

### Workflow sessions

A `WorkflowSession` is the snapshot record created when a workflow is executed via `POST /workflows/{id}/execute`. The chat experience is exposed at `POST /workflow-sessions/{id}/agent` (streaming) and the session metadata is fetched via `GET /workflow-sessions/{id}`. A list endpoint enables the admin UI to browse all executed sessions ordered by most recent first.

#### `GET /api/v1/workflow-sessions` — List workflow sessions

```bash
curl "http://localhost:8000/api/v1/workflow-sessions?limit=20&offset=0"
```

#### `GET /api/v1/workflow-sessions/{id}` — Get a workflow session

```bash
curl http://localhost:8000/api/v1/workflow-sessions/<id>
```

---

### Workflow tasks

A workflow task is a single actionable item belonging to a `WorkflowSession`. The skill-driven workflow agent registers and drives these tasks itself via [agent tools](#agent-task-tools); they are also exposed through the REST endpoints below. Each task carries a `status` (`pending` | `in_progress` | `completed` | `failed` | `skipped`) and an integer `position` used for stable layout ordering within a session. Deleting the parent `WorkflowSession` cascades to its tasks.

Tasks form a **directed acyclic graph (DAG)**: each task may depend on other tasks in the same session through its `dependsOnIds` list (persisted as `(task_id, depends_on_id)` rows in the `workflow_task_dependencies` join table, where `depends_on_id` must precede `task_id`). Read responses include the resolved `dependsOnIds`. Dependency targets must exist and belong to the same session, otherwise the write fails with `422 FOREIGN_KEY_VIOLATION`; edges that would introduce a cycle — including a self-dependency — fail with `409 DEPENDENCY_CYCLE`. Deleting a task cascade-deletes the edges that reference it in either direction.

Tasks may additionally bind **MCP tools** from [registered MCP servers](#mcp-servers) through their `toolBindings` list (`[{"mcpServerId": …, "toolName": …}]`, persisted in the `workflow_task_tool_bindings` join table). Read responses include the resolved `toolBindings`. Every bound `mcpServerId` must reference a registered server, otherwise the write fails with `422 FOREIGN_KEY_VIOLATION`; duplicates are deduplicated. Bindings cascade-delete with their task, while a referenced MCP server cannot be deleted (`409 CONFLICT_REFERENCED`). At execution time the agent may only invoke bound tools via the `call_mcp_tool` proxy (see [Agent task tools](#agent-task-tools)).

#### Agent task tools

When a workflow runs, the skill-bound agent is given six function tools so it can plan and drive the task DAG itself, in addition to the REST endpoints below. The agent runs a **plan-then-execute** flow: it registers the plan, waits for the user's approval, then iterates the tasks updating their status.

| Tool | Purpose |
|---|---|
| `register_workflow_tasks` | Register a whole plan as a DAG in one call (each entry has a `key`, `title`, optional `depends_on` referencing other keys, optional `tools` binding MCP tools) |
| `create_workflow_task` | Add a single task, optionally referencing existing task ids as dependencies and binding MCP tools |
| `list_workflow_tasks` | List the current session's tasks (id, title, status, `dependsOnIds`, position, `tool_bindings`) |
| `get_workflow_task` | Fetch one task in the current session |
| `update_workflow_task` | Change a task's title / description / status / position / dependencies / tool bindings |
| `delete_workflow_task` | Delete a task |
| `list_mcp_tools` | Discover the tools advertised by every [registered MCP server](#mcp-servers) (queried live and concurrently; per-server failures are isolated) |
| `call_mcp_tool` | Invoke an MCP tool bound to the task currently `in_progress`; calls to unbound tools are rejected with an error listing the allowed tools |

The tools resolve the current session by mapping the ADK session id (the AG-UI thread id, stored on `WorkflowSession.session_id`) back to the `WorkflowSession` primary key, and they reject access to tasks belonging to other sessions. They live in `infrastructure/workflow_task_tools.py` and `infrastructure/mcp_tools.py` and are attached to the agent in `infrastructure/agent.py` only when a skill is bound. `call_mcp_tool` opens one streamable HTTP connection per call (30-second timeout) through the shared adapter in `infrastructure/mcp_client.py`.

#### `POST /api/v1/workflow-tasks` — Create a workflow task

```bash
curl -X POST http://localhost:8000/api/v1/workflow-tasks \
  -H "Content-Type: application/json" \
  -d '{"workflowSessionId": "<ws_id>", "title": "Draft outline", "position": 0}'
```

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `workflowSessionId` | string | Yes | ID of the parent `WorkflowSession` |
| `title` | string | Yes | Short, human-readable task title |
| `description` | string | No | Longer-form details about the task |
| `status` | string | No | One of `pending`, `in_progress`, `completed`, `failed`, `skipped` (default: `pending`) |
| `position` | integer | No | Layout order within the session (default: `0`) |
| `dependsOnIds` | string[] | No | IDs of tasks in the same session that must precede this one (default: `[]`) |
| `toolBindings` | object[] | No | MCP tools the task may use: `[{"mcpServerId": …, "toolName": …}]` (default: `[]`) |

Returns `422 FOREIGN_KEY_VIOLATION` if `workflowSessionId` does not match an existing session, if any `dependsOnIds` entry does not exist or belongs to another session, or if any `toolBindings` entry references an unregistered MCP server. Returns `409 DEPENDENCY_CYCLE` if the dependencies would create a cycle.

#### `GET /api/v1/workflow-sessions/{session_id}/workflow-tasks` — List tasks for a session

Returns the tasks belonging to a `WorkflowSession`, ordered by `position` ASC then `created_at` ASC. Returns `404` if the session does not exist.

```bash
curl "http://localhost:8000/api/v1/workflow-sessions/<ws_id>/workflow-tasks?limit=20&offset=0"
```

#### `GET /api/v1/workflow-tasks/{task_id}` — Get a workflow task

```bash
curl http://localhost:8000/api/v1/workflow-tasks/<id>
```

#### `PATCH /api/v1/workflow-tasks/{task_id}` — Update a workflow task

`workflowSessionId` is not updatable; once a task is created it cannot be re-parented. Sending `dependsOnIds` replaces the task's full set of dependency edges, and sending `toolBindings` replaces its full set of bound MCP tools; omitting either leaves it unchanged. The same `422 FOREIGN_KEY_VIOLATION` / `409 DEPENDENCY_CYCLE` validation as create applies.

```bash
curl -X PATCH http://localhost:8000/api/v1/workflow-tasks/<id> \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress", "dependsOnIds": ["<other_task_id>"]}'
```

#### `DELETE /api/v1/workflow-tasks/{task_id}` — Delete a workflow task

```bash
curl -X DELETE http://localhost:8000/api/v1/workflow-tasks/<id>
```

---

### Notifications

Per-user notifications surfaced in the frontend's toolbar bell. Notifications are generated as a side effect of the agent's task tools — `register_workflow_tasks` raises an `approval_request`, and the final `update_workflow_task` that drives every task to a terminal state raises a one-shot `session_completed` — and are addressed to the user who started the workflow session. Both endpoints below are scoped to the authenticated user; the list never accepts a `user_id`, and reading or marking another user's notification returns `404 NOT_FOUND`.

Each notification stores a `type` (`approval_request` / `session_completed`), `title`, optional `body`, the linked `workflowSessionId`, and a `read` flag. Rows cascade-delete with their recipient user and their linked `WorkflowSession`.

#### `GET /api/v1/notifications` — List the current user's notifications

Returns the caller's notifications ordered by `created_at` DESC. Pass `unreadOnly=true` to return only unread notifications (used by the bell's unread badge).

```bash
curl "http://localhost:8000/api/v1/notifications?unreadOnly=true&limit=20&offset=0"
```

#### `PATCH /api/v1/notifications/{notification_id}` — Mark a notification read

```bash
curl -X PATCH http://localhost:8000/api/v1/notifications/<id>
```

Returns `404 NOT_FOUND` if the notification does not exist or is addressed to another user.

---

### `POST /chat`

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

### `GET /health`

Health check.

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```
