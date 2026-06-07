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
| `agent_skills` | Agent skill definitions |
| `workflows` | Workflow definitions |
| `workflow_tasks` | Individual tasks belonging to a `WorkflowSession` (`workflow_session_id` FK with `ON DELETE CASCADE`) |
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

#### `GET /sessions` — List sessions

The caller's identity is read from the `X-User-Id` request header (set by all frontend requests via the axios interceptor).

```bash
curl -H "X-User-Id: alice" "http://localhost:8000/api/v1/sessions"
```

#### `GET /sessions/{session_id}` — Get a session

```bash
curl -H "X-User-Id: alice" "http://localhost:8000/api/v1/sessions/my-session"
```

Returns `404` if the session does not exist or belongs to a different user.

#### `GET /sessions/{session_id}/messages` — Get session messages

```bash
curl -H "X-User-Id: alice" "http://localhost:8000/api/v1/sessions/my-session/messages"
```

#### `DELETE /sessions/{session_id}` — Delete a session

```bash
curl -X DELETE -H "X-User-Id: alice" "http://localhost:8000/api/v1/sessions/my-session"
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

#### Agent task tools

When a workflow runs, the skill-bound agent is given six function tools so it can plan and drive the task DAG itself, in addition to the REST endpoints below. The agent runs a **plan-then-execute** flow: it registers the plan, waits for the user's approval, then iterates the tasks updating their status.

| Tool | Purpose |
|---|---|
| `register_workflow_tasks` | Register a whole plan as a DAG in one call (each entry has a `key`, `title`, optional `depends_on` referencing other keys) |
| `create_workflow_task` | Add a single task, optionally referencing existing task ids as dependencies |
| `list_workflow_tasks` | List the current session's tasks (id, title, status, `dependsOnIds`, position) |
| `get_workflow_task` | Fetch one task in the current session |
| `update_workflow_task` | Change a task's title / description / status / position / dependencies |
| `delete_workflow_task` | Delete a task |

The tools resolve the current session by mapping the ADK session id (the AG-UI thread id, stored on `WorkflowSession.session_id`) back to the `WorkflowSession` primary key, and they reject access to tasks belonging to other sessions. They live in `infrastructure/workflow_task_tools.py` and are attached to the agent in `infrastructure/agent.py` only when a skill is bound.

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

Returns `422 FOREIGN_KEY_VIOLATION` if `workflowSessionId` does not match an existing session, or if any `dependsOnIds` entry does not exist or belongs to another session. Returns `409 DEPENDENCY_CYCLE` if the dependencies would create a cycle.

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

`workflowSessionId` is not updatable; once a task is created it cannot be re-parented. Sending `dependsOnIds` replaces the task's full set of dependency edges; omitting it leaves the edges unchanged. The same `422 FOREIGN_KEY_VIOLATION` / `409 DEPENDENCY_CYCLE` validation as create applies.

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

The caller's identity is read from the `X-User-Id` request header (same convention as the REST endpoints).

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
  -H "X-User-Id: alice" \
  -d "{\"threadId\": \"$SESSION\", \"runId\": \"$(python -c 'import uuid; print(uuid.uuid4())')\", \"state\": {}, \"tools\": [], \"context\": [], \"messages\": [{\"id\": \"m1\", \"role\": \"user\", \"content\": \"What is Python?\"}], \"forwardedProps\": {}}"
```

---

### `GET /health`

Health check.

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```
