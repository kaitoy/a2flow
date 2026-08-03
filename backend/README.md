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
| `users` | Application users (soft-deleted via `deleted_at`; `roles` holds their granted roles); see [Seeded users](#seeded-users) and [Authorization](#authorization-roles) |
| `auth_sessions` | Server-side login sessions (hashed cookie token + CSRF token); see [Authentication](#authentication) |
| `impersonation_events` | Audit trail of impersonation sessions (`impersonator_id`, `target_user_id`, `started_at`, `ended_at`); see [Authentication](#authentication) |
| `agent_skills` | Agent skill definitions (incl. optional `repo_auth_password` / `repo_auth_username` for private-repo clones) |
| `mcp_servers` | Registered MCP servers (name, `transport`, then either streamable HTTP URL + request headers or stdio command + args + env — header and env values may embed `${secret:NAME/KEY}` placeholders) |
| `secrets` | Named key/value credential bundles: an `entries` map of Fernet-encrypted local values, or a HashiCorp Vault KV v2 path reference; see [Secrets](#secrets) |
| `workflows` | Workflow definitions (name, skill reference, lifecycle `status`, AI-summarized `generatedDescription`, user-editable `description`) |
| `workflow_task_templates` | The pre-designed task list of a workflow (`workflow_id` FK with `ON DELETE CASCADE`; dependency edges and MCP tool bindings live in their own `workflow_task_template_*` join tables) |
| `workflow_published_versions` | At most one per workflow: the name, description, and task templates (as JSON) frozen at publish time, which a `modified` workflow runs against; see [Workflows](#workflows) |
| `design_sessions` | One per workflow: the chat in which its task templates are produced and refined |
| `workflow_tasks` | Individual tasks belonging to a `WorkflowSession`, copied from the templates at execute time (`workflow_session_id` FK with `ON DELETE CASCADE`) |
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

### Seeded users

On startup the backend seeds a hidden **system user**, plus two real accounts, each created only on the very first startup that finds its target record missing:

- An initial **`root`** user holding the **`super_admin`** role (see [Authorization](#authorization-roles)), platform-scoped (`tenantId: null`). Skipped once *any* real (non-system) user already exists, so it runs only on the very first startup.
- A **Default** tenant (`slug: default`) and, inside it, an initial **`admin`** user holding the **`admin`** role. The tenant (by `slug`) and the user (by `username` scoped to that tenant) are checked independently, so either can be recreated without duplicating the other.

The hidden **system user** owns the bootstrap records (it cannot log in and is excluded from the user list).

Passwords are read from environment variables, with the same generate-and-log-once fallback for each:

```env
ROOT_PASSWORD=change-me-now-123
ADMIN_PASSWORD=change-me-now-123
```

If either is unset (or empty), a random password is generated instead and logged **once**, at `WARNING` level, when that user is created — it cannot be recovered once the log line has scrolled past. Set both explicitly before the first run for anything beyond local experimentation, or capture the generated passwords from the startup logs immediately and change them through the user API afterwards. The usernames are fixed to `root` and `admin`.

### Demo data

`DEMO_DATA=true` registers a ready-made example of the approval-gated "launch an EC2 instance" workflow on startup, so a fresh install has something to run without registering every piece by hand. Everything lands in the seeded **Default** tenant:

| Resource | Name | Details |
|---|---|---|
| Secret | `demo-aws-credentials` | `local` type with two entries, `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, each Fernet-encrypted like any other secret |
| MCP server | `AWS MCP Server` | `stdio` transport, `uvx mcp-proxy-for-aws@1.6.4 https://aws-mcp.us-east-1.api.aws/mcp --region us-east-1 --metadata AWS_REGION=${env:AWS_REGION}`; its `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` env vars are `${secret:demo-aws-credentials/…}` references to the two entries above, and its `AWS_REGION` env var (from `DEMO_AWS_REGION`) is what the `--metadata AWS_REGION=${env:AWS_REGION}` argument expands to at connection time |
| Agent skill | `Demo AWS EC2 Launch` | `sample_skills/aws-ec2-launch` in this repository (see [Agent skills](#agent-skills)) |
| User | `demo-approver` | holds `approver` — the manager the sample skill routes its approval request to |
| User | `demo-requester` | holds `requester` — may execute the workflow |

The Workflow itself is deliberately not seeded: these records are the ingredients you assemble one from.

```env
DEMO_DATA=true
DEMO_PASSWORD=change-me-now-123
DEMO_AWS_ACCESS_KEY_ID=AKIA...
DEMO_AWS_SECRET_ACCESS_KEY=...
DEMO_AWS_REGION=us-east-1
```

- `DEMO_PASSWORD` is shared by both demo users and has the same generate-and-log-once fallback as `ROOT_PASSWORD` / `ADMIN_PASSWORD`. It is only consulted while one of the accounts is missing.
- **AWS MCP Server** is a managed remote server AWS hosts, not something this project runs, so the registered `stdio` server actually launches [`mcp-proxy-for-aws`](https://github.com/aws/mcp-proxy-for-aws) — a thin bridge that SigV4-signs each request with the credentials it finds in its environment and forwards it to the endpoint. It supersedes the deprecated self-hosted `awslabs.aws-api-mcp-server`; see the upstream [migration guide](https://github.com/awslabs/mcp/blob/main/src/aws-api-mcp-server/MIGRATION.md).

  The two regions in the arguments are not the same knob. `--region us-east-1` is the region the *signature* is computed for and is fixed to wherever the endpoint lives, while `--metadata AWS_REGION=${env:AWS_REGION}` (which expands to `DEMO_AWS_REGION`, carried in the row's own `env` — see [`${env:NAME}`](#mcp-servers)) is the region the server's *tools* act on. The proxy does not infer the signing region from the endpoint URL, so it stays explicit.

- The AWS credentials are optional. Left unset, a `REPLACE_ME` placeholder is stored instead, so the demo is complete in shape and you fill the real values in from the Secrets page. Set them here to have the demo reach AWS straight after startup. They need permission to call the managed endpoint (the `aws-mcp` service) on top of the permissions for whatever the tools go on to do.

  > **The demo MCP server is not restricted to read-only operations.** Whatever credentials you give it can create, modify, and delete real resources — including running instances that cost money. Point it at a throwaway account, or scope the IAM policy down. (`mcp-proxy-for-aws` has a `--read-only` flag, but the sample workflow launches an instance, so the demo deliberately does not pass it.)

- The agent skill's repository is cloned in the background after startup, so a slow or unreachable remote never delays the server coming up. The skill shows as `pending` until the clone lands, exactly as a skill registered through the API does; a failure is recorded on the skill row with its reason.

Turning the flag off (`DEMO_DATA=false`, or removing it) **removes those records again** on the next startup — the flag is declarative in both directions. Each record is tracked by a fixed id, not by name, so renaming one in the admin UI does not strand it.

Two things survive that removal by design:

- A demo record something else has come to depend on — a Workflow built on the demo skill, a task tool binding on the demo MCP server — cannot be deleted. That is logged at `WARNING` and skipped; the remaining demo records are still removed, and the app starts normally.
- A demo user who has signed in and created records is **soft-deleted** (disabled, `deletedAt` set) rather than removed, so their name still resolves on those records. Re-enabling `DEMO_DATA` revives such an account instead of leaving it disabled.

### Authentication

All API routes except `POST /api/v1/auth/login` and `GET /api/v1/health` require an authenticated session. Authentication is cookie-based and backed by the `auth_sessions` table.

**Flow**

1. `POST /api/v1/auth/login` with `{ "username", "password", "tenantSlug"? }`. `tenantSlug` disambiguates a tenant-scoped user's username (unique only within its tenant) and must be omitted for a platform-scoped user (e.g. `root`). On success the response sets two cookies and returns the current user (without the password hash):
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

The frontend reaches the backend through a same-origin Next.js rewrite (`/api/*`), so the cookies are first-party and `SameSite=Lax` applies cleanly. Log in with the seeded `root` or Default-tenant `admin` user (see [Seeded users](#seeded-users)) on first run.

**Impersonation.** A signed-in `admin`/`super_admin` can act as another user via a request header, `X-Impersonate-User-Id`, rather than a second session — the real session cookie never changes, so stopping never requires re-authenticating. `get_current_user` (`dependencies/auth.py`) re-validates the header on **every** request carrying it (not just when impersonation starts): it resolves the real session identity first (`RealUserDep` / `get_session_user`), then, if the header names a user with an open, still-valid impersonation, returns that user as the *effective* identity instead — which is what `CurrentUserDep`/`CurrentUserIdDep`/`CurrentTenantIdDep` resolve to everywhere else in the app, so authorization, tenant scoping, and `createdBy`/`updatedBy` audit fields all transparently apply to the impersonated user with no other code changes. An invalid or stale header (target since disabled, promoted, or already stopped elsewhere) is never an error — it silently falls back to the real user, since the frontend attaches a persisted selection starting with the very first `/auth/me` call on page load, and failing that call would otherwise boot a legitimate admin out of the whole app over a merely stale local selection.

- `POST /api/v1/auth/impersonate` — body `{ "targetUserId" }`; starts impersonating, opening an `impersonation_events` row. A `super_admin` may target any user platform-wide; an `admin` only within their own tenant (a cross-tenant target id returns `404 NOT_FOUND`, not `403`, so its existence in another tenant is never confirmed). Targeting a `super_admin`, the caller themself, a disabled/soft-deleted user, or the seeded system user returns `403 FORBIDDEN` — as does targeting an `admin`, unless the caller is themself a `super_admin`.
- `DELETE /api/v1/auth/impersonate` — stops impersonating, closing the open `impersonation_events` row; a no-op (never an error) if nothing is open.
- `GET /api/v1/auth/me` returns `{ "user", "impersonatedBy" }`: `user` is the effective (possibly impersonated) identity, and `impersonatedBy` is the real actor whenever it differs from `user` — `null` otherwise. The frontend uses a `null` `impersonatedBy` to self-heal a stale local impersonation selection.

### Authorization (roles)

Authenticated users additionally hold **roles** (`users.roles`, a JSON list of `super_admin` / `admin` / `developer` / `requester` / `approver`) that gate the write endpoints. `super_admin` bypasses every route-level role gate; the seeded `root` user holds it. Two ownership-layer checks are a deliberate exception — see the bullet below. See the [Roles and authorization](../README.md#roles-and-authorization) section of the root README for the full matrix.

Two enforcement points:

- **Route dependency** — `require_roles(...)` (`dependencies/authz.py`) is attached per route (e.g. `dependencies=[Depends(require_roles(Role.developer))]`) on the create/update/delete handlers and on `POST /workflows/{id}/execute`. `GET` routes are not gated. `POST /api/v1/auth/impersonate` uses a narrower variant, `require_actor_roles(...)`, checked against the real actor (`RealUserDep`) rather than the possibly-impersonated `CurrentUserDep`: gating it the ordinary way would mean every request while impersonating — including the "stop" call itself — resolves the role check against the (deliberately non-admin) impersonation target, permanently locking an impersonating admin out of ever stopping.
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

Tests run in parallel across CPU cores by default via `pytest-xdist` (`-n auto`, set in `pyproject.toml`'s `addopts`). Worker count is capped at 50% of the host's CPU cores by a `pytest_xdist_auto_num_workers` hook in `tests/conftest.py` (mirroring `frontend/vitest.config.ts`'s `maxWorkers: "50%"`) — this leaves cores free for `frontend` tooling (e.g. `vitest`) running alongside it, since backend and frontend changes are often made together. No LLM API keys are required to run the tests. Pass `-v` for verbose output:

```bash
cd backend && uv run pytest -v
```

`-n auto` is incompatible with `--pdb`/`-s`/`--trace` (pytest-xdist errors out since those need a single process). Disable parallelism for a debugging session with `-n0` (note: `-p no:xdist` alone does *not* work here, since `addopts` still passes `-n auto` and the plugin that understands `-n` would be disabled):

```bash
cd backend && uv run pytest -n0 -k some_test --pdb
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

Private repositories are supported through the optional `repoAuthPassword` field — a `NAME/KEY` reference to one entry of a registered [secret](#secrets), whose value is used as the HTTP basic-auth password for the clone — plus `repoAuthUsername` (default `x-access-token`, which suits GitHub PATs). Create/update validates that the **name** half exists (`422 FOREIGN_KEY_VIOLATION` otherwise); the key is not checked there, since a `vault` secret's keys would need a live Vault read and the two types should behave alike. (`GET /api/v1/secrets/{id}/keys` does perform that read, but it is a picker's lookup — putting it on the save path would make every write depend on Vault being up.) The whole reference is resolved lazily at clone time: a later rename or delete of the secret, or a key that no longer exists, makes the next clone fail with `502 SECRET_RESOLUTION_FAILED`.

The content at `repoUrl`/`repoPath` (e.g. `SKILL.md`) is loaded directly into the workflow agent's LLM prompt, unsandboxed — only register repositories you trust, since their content is effectively an instruction to the agent, not inert data.

---

### MCP servers

A registry of [MCP](https://modelcontextprotocol.io/) servers whose tools the workflow agent can bind to WorkflowTasks. Each record is discriminated by `transport`:

| `transport` | Fields | Connection |
|---|---|---|
| `streamable_http` (default) | `url`, `headers` | One streamable HTTP session per operation, 30-second timeout. SSE-transport servers are not supported. |
| `stdio` | `command`, `args`, `env` | One child process per operation, 120-second timeout — the larger budget covers a cold `npx -y pkg@version` / `uvx pkg` download. `command` is restricted to `npx`/`uvx`, the only two runtimes the backend image ships. |

Literal `headers` / `env` values are stored in plaintext; to keep a credential out of the record, embed a `${secret:NAME/KEY}` placeholder referencing a registered [secret](#secrets) — placeholders are expanded only when connecting, and a reference that no longer resolves fails the connection attempt (`502 SECRET_RESOLUTION_FAILED` on the REST path; a per-server `error` entry for the agent's `list_mcp_tools`/`call_mcp_tool` proxies).

A stdio server runs its `command` inside the backend container. `args` is handed to the process as a list and never through a shell, and the child inherits only the variables `mcp.client.stdio.get_default_environment()` deems safe (`PATH`, `HOME`, …) merged with the configured `env` — the backend's own secrets are not visible to it. Writes are gated behind the same `developer` role as any other MCP server write.

An `args` entry may also embed `${env:NAME}`, referencing a key of that same server's own `env` — useful for a launcher that expects a value as a CLI flag rather than reading it from the process environment. `NAME` must be a key of `env`; the reference is checked eagerly against the *merged* result on both create (`MCPServerCreate`'s validator) and update (`MCPServerService.update`, `422 INVALID_MCP_SERVER`) — including a PATCH that removes the `env` key an existing `args` entry still names. Expansion itself happens in `resolve_connection` after `env`'s own `${secret:NAME/KEY}` placeholders resolve, so `${env:NAME}` transparently picks up a secret-backed value; `StdioConnection.label` (used in `MCP_UNREACHABLE` error details and logs) is built from the *unexpanded* `args`, so an expanded value never leaks there.

The CRUD endpoints are in the [API reference](http://localhost:3000/api-doc). On create, `name` is always required, plus `url` for `streamable_http` or `command` for `stdio`; mixing the two shapes fails Pydantic validation (`422 VALIDATION_ERROR`) and a duplicate name returns `409 CONFLICT_UNIQUE`. On update, sending `headers` / `args` / `env` replaces the whole collection while omitting it leaves it unchanged, and the *merged* per-transport shape is validated by `MCPServerService.update` (`422 INVALID_MCP_SERVER`) — switching transport clears the other shape's fields automatically. Two more behaviors are worth calling out: `GET /api/v1/mcp-servers/{id}/tools` connects to the server live and returns its advertised tools (`name`, `description`, `inputSchema`), or `502 MCP_UNREACHABLE` if it cannot be reached or launched within its timeout; and a server cannot be deleted while WorkflowTask tool bindings still reference it (`409 CONFLICT_REFERENCED`).

`GET /api/v1/mcp-registry` proxies the official [MCP registry](https://registry.modelcontextprotocol.io/) for server discovery. It accepts `search` (substring matched against server names) and `cursor` (pagination) query params and returns `{ servers, nextCursor }`, where each server is flattened to the fields A2Flow can use. A server is surfaced through its streamable-HTTP remote when it has one, otherwise through its first stdio package published to npm or PyPI — flattened to a best-effort `command`/`args`/`env` (`runtimeHint` or `npx`/`uvx`, then the rendered runtime arguments, the `identifier@version` reference, and the rendered package arguments). OCI/NuGet packages and SSE-only remotes are skipped, since nothing in the image can launch them, as is any package whose `runtimeHint` names a command other than `npx`/`uvx`, since the backend only accepts those two. The registry base URL is configurable via the `MCP_REGISTRY_URL` env var (default `https://registry.modelcontextprotocol.io`); a registry that cannot be reached returns `502 REGISTRY_UNREACHABLE`. Registration itself reuses the ordinary `POST /api/v1/mcp-servers` create flow from a pre-filled admin form.

---

### Secrets

Named bundles of key/value entries — the shape a Vault KV path has — consumed by MCP server placeholders and agent-skill repository clones. Each secret is either `local` — the submitted `entries` map is stored in the `secrets` table as `{key: Fernet ciphertext}`, encrypted with the key described in [Secret management](#secret-management), with entry keys kept in plaintext so they can be listed without decrypting — or `vault` — only a KV v2 reference (`vaultMount`, `vaultPath`) is stored and every key at that path is read from HashiCorp Vault at resolution time.

References always name one entry, as `NAME/KEY` (`${secret:NAME/KEY}` in a placeholder). The key is required even for a single-entry secret; a key-less reference raises `502 SECRET_RESOLUTION_FAILED` rather than passing through unsubstituted.

`GET /api/v1/secrets/{id}/keys` lists one secret's entry keys for both types alike — from the stored map for a `local` secret, from a live KV v2 read for a `vault` one (`502 SECRET_RESOLUTION_FAILED` when Vault is unconfigured or unreachable). It exists because the read view's `keys` field is necessarily empty for a `vault` secret, and doing that live read for every row of a list response would be far too expensive; the agent-skill auth-password picker calls it for whichever secret is selected. Only key names cross the wire.

The API is **write-only for values**: create/update accept plaintext `entries`, but every response uses a read view exposing only the sorted entry `keys`, so neither a plaintext nor a ciphertext value is ever serialized to clients. On update, omitting `entries` keeps the stored map; supplying it replaces the map wholesale (keys left out are deleted), with an **empty-string value meaning "keep the ciphertext already stored under this key"** — the only way a client can preserve a value it never receives. An empty value for a key that does not exist yet, or a map that would leave the secret with no entries, returns `422 INVALID_SECRET`; so does switching `type` into an invalid merged shape (e.g. a `vault` secret with `entries`), while a valid switch clears the other shape's fields. Names are unique (`409 CONFLICT_UNIQUE`) and entry keys and names both use the slug charset (letters, digits, `.`, `_`, `-`) — the absence of `/` is what keeps `NAME/KEY` unambiguous. Deletion is never blocked by references; dangling ones fail at their next resolution with `502 SECRET_RESOLUTION_FAILED` (the failure reason is logged server-side only). CRUD endpoints are in the [API reference](http://localhost:3000/api-doc).

---

### Workflows

A workflow pairs an agent skill with a **pre-designed task list** (its task templates). Each workflow references exactly one agent skill; a single agent skill may be used by multiple workflows. There is no bare `POST /workflows`: a workflow is born from `POST /api/v1/agent-skills/{skill_id}/workflows` ("Generate workflow", body `{name, prompt}`, developer-gated), which registers the row in `status: "generating"` together with its [design session](#design-sessions), then runs the prompt through an unattended design agent in a background job (`services/workflow_design.py`). Success summarizes the conversation into `generated_description` (one LLM call via `infrastructure/summarizer.py`, falling back to the transcript head), sets `status: "draft"`, and raises a `workflow_draft_ready` notification; any failure lands as `status: "failed"` plus `generationError`. `status` and `generationError` are server-managed and cannot be written through `PATCH` (which edits `name`, `description`, and — for a super admin only — `generated_description`).

`POST /api/v1/workflows/{id}/generate-description` (developer-gated) re-runs that summarization on demand, which is the only way `generated_description` is refreshed after generation. It reads the workflow's design conversation out of the ADK session store, summarizes it, saves the result, and returns the updated workflow; a `published` workflow becomes `modified`, since a run whose `description` is empty falls back to the summary. A workflow still `generating`, or one with no design conversation to summarize, returns `409 WORKFLOW_DESCRIPTION_NOT_GENERATABLE`; a failing LLM call returns `502 SUMMARIZATION_FAILED` (the raw reason is logged server-side only).

`POST /api/v1/workflows/{id}/publish` (developer-gated) makes a workflow executable: it requires at least one task template and no generation in flight (`409 WORKFLOW_NOT_RUNNABLE` otherwise) and **freezes the design** into the workflow's `WorkflowPublishedVersion` row (name, description, and every task template with its edges and tool bindings — replacing the previous snapshot), and sets `status: "published"`. Executing a workflow — `POST /api/v1/workflows/{id}/execute`, requester-gated — accepts published, `modified`, and (developer-only) draft workflows (`409 WORKFLOW_NOT_RUNNABLE` otherwise), snapshots its configuration into a new `WorkflowSession`, and copies its templates into the session's tasks (see below). The remaining endpoints (list/get/patch/delete, `GET /{id}/task-templates`, `GET /{id}/design-session`) are in the [API reference](http://localhost:3000/api-doc).

Editing a published workflow does not silently change what runs. A `PATCH /workflows/{id}`, a description regeneration, or any task-template write moves a `published` workflow to **`status: "modified"`** (`WorkflowRepository.mark_modified`, called from `WorkflowService.update`, `WorkflowDesignService.generate_description`, and `WorkflowTaskTemplateService`). A `modified` workflow is still runnable, but `execute` resolves its task templates from the published snapshot instead of the live rows — name, description, and tasks all come from the version captured at publish time. Publishing again promotes the edits (and re-freezes the snapshot); `POST /api/v1/workflows/{id}/discard-changes` (developer-gated) does the opposite, rewriting the task templates from the snapshot — reusing the original template IDs, so the recorded edges stay valid — restoring the recorded name and description, and returning the workflow to `published`. Discarding anything but a `modified` workflow returns `409 WORKFLOW_NOT_MODIFIED`; a snapshot binding an MCP tool whose server has since been deleted fails the restore with `422 FOREIGN_KEY_VIOLATION`.

The design agent's tools trigger the same transition. They go straight to the repository (`infrastructure/design_task_tools.py`) rather than through `WorkflowTaskTemplateService`, so each write tool calls `mark_modified` itself — task templates refined by chat have drifted from the published snapshot just as much as ones edited through the REST API. During the initial background generation run the workflow is still `generating`, which `mark_modified` leaves alone, so nothing special is needed there.

---

### Workflow task templates

A workflow task template is one step of a workflow's pre-designed task list, owned by the workflow (`workflow_id` FK, `ON DELETE CASCADE`). Templates mirror [workflow tasks](#workflow-tasks) structurally — `title`, optional `description`, `position`, DAG edges (`workflow_task_template_dependencies`, cycle-checked exactly like task edges), and MCP tool bindings (`workflow_task_template_tool_bindings`, server side `ON DELETE RESTRICT`) — but carry **no status**: the lifecycle belongs to a run. They are written by the design agent's tools (`infrastructure/design_task_tools.py`) and by the developer-gated manual CRUD endpoints (`POST /workflow-task-templates`, `GET`/`PATCH`/`DELETE /workflow-task-templates/{id}`, listing on `GET /workflows/{id}/task-templates`), all in the [API reference](http://localhost:3000/api-doc). At execute time the templates are copied into the new session as `pending` WorkflowTasks in dependency order, ids remapped, bindings included — so template edits never affect runs already started. Editing a template — through the CRUD endpoints or through the design agent's tools — also moves a `published` parent workflow to `modified`, after which runs use the published snapshot rather than these rows until the workflow is published again (see [Workflows](#workflows)).

---

### Design sessions

A `DesignSession` is the chat in which a workflow's task templates are produced and refined — a separate entity from `WorkflowSession`, created 1:1 with its workflow by the generation flow and pinned to the skill revision published at that moment (`agentSkillCommitSha`). The background generation run posts the prompt as its first message, so opening the chat later shows the full conversation. Unlike workflow sessions, design sessions are **owner-only** (plus Super Admins): there is no approver sharing and no sender-attribution bookkeeping.

Endpoints: `GET /design-sessions/{id}`, `GET /design-sessions/{id}/messages` (empty until the generation run starts), and the streaming `POST /design-sessions/{id}/agent` (excluded from the spec like the other agent endpoints). The agent resolved for this chat runs with the interactive **design** instruction and toolset — it edits the workflow's templates and never executes anything. The session cascade-deletes with its workflow, and the skill-store prune keeps every revision a design session still pins.

---

### Workflow sessions

A `WorkflowSession` is the snapshot record created when a published workflow is executed via `POST /workflows/{id}/execute`, pre-filled with `pending` WorkflowTasks copied from the workflow's templates. The chat experience is exposed at `POST /workflow-sessions/{id}/agent` (streaming) and the session metadata is fetched via `GET /workflow-sessions/{id}`. A list endpoint enables the admin UI to browse all executed sessions ordered by most recent first. The run endpoint overwrites the AG-UI `context` with the workflow's summarized `description` server-side, so the execution agent receives the design intent as trusted context (and a client can never inject its own).

The list (ordered most-recent-first) and get endpoints are in the [API reference](http://localhost:3000/api-doc).

---

### Workflow tasks

A workflow task is a single actionable item belonging to a `WorkflowSession`, copied from the workflow's task templates at execute time and driven by the execution agent via [agent tools](#agent-task-tools); they are also exposed through the REST endpoints below. Each task carries a `status` (`pending` | `in_progress` | `completed` | `failed` | `skipped`) and an integer `position` used for stable layout ordering within a session. Deleting the parent `WorkflowSession` cascades to its tasks.

Tasks form a **directed acyclic graph (DAG)**: each task may depend on other tasks in the same session through its `dependsOnIds` list (persisted as `(task_id, depends_on_id)` rows in the `workflow_task_dependencies` join table, where `depends_on_id` must precede `task_id`). Read responses include the resolved `dependsOnIds`. Dependency targets must exist and belong to the same session, otherwise the write fails with `422 FOREIGN_KEY_VIOLATION`; edges that would introduce a cycle — including a self-dependency — fail with `409 DEPENDENCY_CYCLE`. Deleting a task cascade-deletes the edges that reference it in either direction.

Tasks may additionally bind **MCP tools** from [registered MCP servers](#mcp-servers) through their `toolBindings` list (`[{"mcpServerId": …, "toolName": …}]`, persisted in the `workflow_task_tool_bindings` join table). Read responses include the resolved `toolBindings`. Every bound `mcpServerId` must reference a registered server, otherwise the write fails with `422 FOREIGN_KEY_VIOLATION`; duplicates are deduplicated. Bindings cascade-delete with their task, while a referenced MCP server cannot be deleted (`409 CONFLICT_REFERENCED`). At execution time the agent may only invoke bound tools via the `call_mcp_tool` proxy (see [Agent task tools](#agent-task-tools)).

#### Agent task tools

Skill-bound agents are built in one of three roles (`AgentKind` in `infrastructure/agent.py`), each with its own instruction and toolset, and the `AgentRegistry` caches one agent per `(skill_id, commit_sha, kind)`:

- **`initial_design`** — the unattended background run of "Generate workflow". No A2UI toolset (no client is connected); tools: `register_design_tasks`, `list_design_tasks`, `list_mcp_tools`.
- **`design`** — the interactive [design session](#design-sessions) chat. Tools: the full design-task set plus `list_mcp_tools`; never executes, and has no approval or MCP-invocation tools.
- **`execution`** — a workflow session run. The tasks come pre-copied from the templates, so there is no bulk registration and no design-approval wait: the instruction says to **begin executing immediately**. Tools: single-task CRUD, the approval tools, and the MCP proxies.

| Tool | Kind | Purpose |
|---|---|---|
| `register_design_tasks` | design | Register a whole set of task templates as a DAG in one call (each entry has a `key`, `title`, optional `depends_on` referencing other keys, optional `tools` binding MCP tools) |
| `create_design_task` / `list_design_tasks` / `get_design_task` / `update_design_task` / `delete_design_task` | design | Refine the workflow's task templates (no status field) |
| `create_workflow_task` | execution | Add a single task mid-run, optionally referencing existing task ids as dependencies and binding MCP tools |
| `list_workflow_tasks` | execution | List the current session's tasks (id, title, status, `dependsOnIds`, position, `tool_bindings`) |
| `get_workflow_task` | execution | Fetch one task in the current session |
| `update_workflow_task` | execution | Change a task's title / description / status / position / dependencies / tool bindings |
| `delete_workflow_task` | execution | Delete a task |
| `request_approval` | execution | Create a `pending` [Approval](#approvals) for the current session (optionally linked to a task) and raise an `approval_request` notification; returns the `approval_id` to pass to the client-side `render_approval` tool |
| `get_approval` | execution | Fetch the current state of an approval in the current session (to re-check a decision) |
| `list_users` | execution | List the registered users (id, username, name, email; system and soft-deleted users excluded) so the agent can choose an `approver` id for `request_approval` |
| `list_mcp_tools` | design + execution | Discover the tools advertised by every [registered MCP server](#mcp-servers) (queried live and concurrently; per-server failures are isolated) |
| `call_mcp_tool` | execution | Invoke an MCP tool bound to the task currently `in_progress`; calls to unbound tools are rejected with an error listing the allowed tools |

The task tools resolve the current session by mapping the ADK session id (the AG-UI thread id) back to the owning record — the `WorkflowSession` primary key for execution tools, the `DesignSession` (and through it the workflow) for design tools — and reject access to records belonging to other sessions. The two MCP proxies split along the same line: `list_mcp_tools` serves both kinds, so it resolves only the tenant and accepts either record, while `call_mcp_tool` has to check the run's in-progress tasks and therefore still requires a `WorkflowSession` (a task template may bind tools, but only a run may invoke them). They live in `infrastructure/workflow_task_tools.py`, `infrastructure/design_task_tools.py`, `infrastructure/approval_tools.py`, and `infrastructure/mcp_tools.py` and are attached to the agent in `infrastructure/agent.py` only when a skill is bound. `call_mcp_tool` opens one connection per call through the shared adapter in `infrastructure/mcp_client.py` — a streamable HTTP session (30-second timeout) or a freshly spawned child process (120-second timeout), depending on the server's transport.

The approver's actual approve/reject decision is written from the frontend via `PATCH /api/v1/approvals/{id}` (not an agent tool), and surfaces to the agent as the result of the client-side `render_approval` tool. See [Approvals](#approvals).

The task CRUD endpoints — create, list-for-a-session (ordered `position` ASC then `created_at` ASC), get, update, delete — are in the [API reference](http://localhost:3000/api-doc). A few rules the spec does not spell out: `workflowSessionId` is fixed at creation and a task cannot be re-parented; sending `dependsOnIds` or `toolBindings` replaces that full set while omitting either leaves it unchanged; and the `422 FOREIGN_KEY_VIOLATION` (unknown session, cross-session dependency, or unregistered MCP server) / `409 DEPENDENCY_CYCLE` validation applies to both create and update.

---

### Notifications

Per-user notifications surfaced in the frontend's toolbar bell. Notifications are generated as side effects of workflow activity — the generation job raises a `workflow_draft_ready` when the initial task templates land, `request_approval` raises an `approval_request` addressed to the designated approver, and the final `update_workflow_task` that drives every task to a terminal state raises a one-shot `session_completed` addressed to the user who started the session. Both endpoints below are scoped to the authenticated user; the list never accepts a `user_id`, and reading or marking another user's notification returns `404 NOT_FOUND`.

Each notification stores a `type` (`workflow_draft_ready` / `approval_request` / `session_completed`), `title`, optional `body`, the linked `workflowSessionId` or `workflowId`, and a `read` flag. Rows cascade-delete with their recipient user and their linked `WorkflowSession` or `Workflow`.

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
