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

### Session storage

```env
SESSION_DB_URL=sqlite:///sessions.db
```

SQLite URL for session persistence via `SqliteSessionService`. Supports SQLAlchemy-style URLs (`sqlite:///relative.db` or `sqlite:////absolute/path.db`). Defaults to `sqlite:///sessions.db` (relative to the working directory).

### Application database

```env
DB_URL=sqlite+aiosqlite:///a2flow.db
```

SQLite URL (async, aiosqlite) for agent skills and workflows. Defaults to `sqlite+aiosqlite:///a2flow.db`. The database and tables are created automatically on first run.

The database is created automatically on first run with the following tables:

| Table | Description |
|---|---|
| `app_states` | App-level shared state |
| `user_states` | Per-user state shared across sessions |
| `sessions` | Session metadata and session-level state |
| `events` | Full event history per session (JSON) |

### CORS

```env
CORS_ORIGINS=http://localhost:3000
```

Comma-separated list of origins allowed to call `/chat` and `/sessions`. Defaults to `http://localhost:3000`. Add additional origins when the frontend is served from a different host or port:

```env
CORS_ORIGINS=https://app.example.com,http://localhost:3000
```

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

A session must be created before starting a chat.

#### `POST /sessions` — Create a session

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `user_id` | string | Yes | User ID |
| `session_id` | string | No | Session ID (auto-generated UUID if omitted) |

```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice"}'
# {"session_id": "...", "user_id": "alice", "last_update_time": 0.0}
```

#### `GET /sessions?user_id=<user_id>` — List sessions

```bash
curl "http://localhost:8000/sessions?user_id=alice"
```

#### `DELETE /sessions/{session_id}?user_id=<user_id>` — Delete a session

```bash
curl -X DELETE "http://localhost:8000/sessions/my-session?user_id=alice"
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

### `POST /chat`

Send an [AG-UI `RunAgentInput`](https://docs.ag-ui.com/concepts/events) to a session and receive the agent's response as an SSE stream. A session must be created beforehand.

**Request body** (AG-UI standard format, camelCase)

| Field | Type | Required | Description |
|---|---|---|---|
| `threadId` | string | Yes | Session ID (obtained from `POST /sessions`) |
| `messages` | array | Yes | Message list; the last `role: "user"` entry is used as the prompt |
| `runId` | string | No | Run ID (auto-generated UUID if omitted) |
| `forwardedProps.userId` | string | No | User ID (default: `"user"`) |
| `tools` | array | No | Tool definitions (currently unused) |
| `context` | array | No | Context items (currently unused) |
| `state` | any | No | Agent state (currently unused) |

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
# 1. Create a session
SESSION=$(curl -s -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice"}' | python -c "import sys,json; print(json.load(sys.stdin)['session_id'])")

# 2. Chat
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"threadId\": \"$SESSION\", \"runId\": \"$(python -c 'import uuid; print(uuid.uuid4())')\", \"state\": {}, \"tools\": [], \"context\": [], \"messages\": [{\"id\": \"m1\", \"role\": \"user\", \"content\": \"What is Python?\"}], \"forwardedProps\": {\"userId\": \"alice\"}}"
```

---

### `GET /health`

Health check.

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```
