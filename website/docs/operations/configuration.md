---
title: Configuration reference
sidebar_position: 1
---

# Configuration reference

Every setting below is an environment variable the backend reads from `backend/.env`. [backend/.env.example](https://github.com/kaitoy/a2flow/blob/master/backend/.env.example) is the annotated template, and the model and API-key settings have a page of their own under [LLM configuration](../getting-started/llm-configuration.md).

## Server settings

```env
HOST=0.0.0.0
PORT=8000
# RELOAD=true
```

Defaults to `HOST=0.0.0.0` and `PORT=8000` if omitted. `RELOAD` (default `false`) enables uvicorn autoreload; it only affects `python -m backend.main` — the `uv run uvicorn main:app --reload` command in [Quick start](../getting-started/quick-start.md) and the Dockerfile's startup path are unaffected either way.

## Operations metrics

```env
# METRICS_TIMEZONE=Asia/Tokyo
```

IANA timezone name deciding where a calendar day starts for the workflow operations metrics — the "today" counts on `GET /api/v1/metrics` and the daily buckets of the lead-time trend. Defaults to `UTC`; an unrecognized name falls back to `UTC` rather than failing startup, so a typo skews a dashboard's day boundary instead of stopping the app. The metrics themselves are described under [Operations metrics](./metrics.md).

## Agent skill store

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

`SKILLS_PRUNE_GRACE_SECONDS` (default 3600) is how long a revision directory survives regardless of whether anything references it. A pull prunes revisions that no workflow execution is pinned to, and the grace window covers the gap between a run reading the skill's current revision and inserting the execution row that names it.

`SKILLS_CLONE_TIMEOUT_SECONDS` (default 120) bounds how long a clone's individual HTTP requests may take. Without it, a slow or hanging remote could stall a clone indefinitely — and with it, the skill's sync advisory lock, leaving the skill `pending` and making a pull of it on another replica silently skip rather than wait.

Defaults to `backend/.skills` (relative to the working directory). Under `docker compose` it is `/var/lib/a2flow/skills`, backed by the `skills` named volume.

This is **durable state, not a cache**: a `WorkflowExecution` pins the revision it started with, so wiping the directory leaves existing executions unable to load their skill (HTTP 409 `SKILL_NOT_READY`) until an admin pulls the skill again. Running more than one backend replica requires all of them to mount this same directory.

## Secret management

```env
# SECRET_ENCRYPTION_KEY=
# SECRET_KEY_FILE=.secret_key
# VAULT_ADDR=https://vault.example.com
# VAULT_TOKEN=hvs.xxxxxxxx
# VAULT_ROLE_ID=...
# VAULT_SECRET_ID=...
# VAULT_APPROLE_MOUNT=approle
```

`local`-type [secrets](../guides/secrets.md) are Fernet-encrypted before storage. The key is resolved at first use: `SECRET_ENCRYPTION_KEY` (must be a valid Fernet key) takes precedence; otherwise the key file at `SECRET_KEY_FILE` (default `.secret_key` next to the SQLite database file) is read; otherwise a key is generated, saved to that file, and a WARNING is logged. Back the key up — losing it makes every stored local secret undecryptable.

`vault`-type secrets are read live from a single HashiCorp Vault (KV v2 only) selected by `VAULT_ADDR`. Authentication uses AppRole (`VAULT_ROLE_ID` + `VAULT_SECRET_ID`, login mount from `VAULT_APPROLE_MOUNT`) when set, else the static `VAULT_TOKEN`. `VAULT_ADDR` is deliberately exempt from the SSRF URL checks applied to user-supplied URLs: it is operator-set deployment configuration and typically points at a private address.

## Application database

```env
DB_URL=sqlite:///a2flow.db
# DB_URL=postgresql://user:password@localhost:5432/a2flow
```

Database URL for REST API data and ADK session storage — both live in the same database. SQLite (the default, relative to the working directory) and PostgreSQL are supported; the async driver suffix (`sqlite+aiosqlite` / `postgresql+asyncpg`) is added automatically, so the plain scheme is enough. With SQLite the ADK session store uses `SqliteSessionService`; any other URL switches it to the SQLAlchemy-based `DatabaseSessionService`. Schema changes are tracked as versioned [Alembic](https://alembic.sqlalchemy.org/) migrations under `alembic/versions/` and applied automatically (`alembic upgrade head`) on startup, so redeploying the app is what brings the schema up to date. To add a migration after changing a model, run `uv run alembic revision --autogenerate -m "..."` and review the generated file before committing.

| Table | Description |
|---|---|
| `users` | Application users (soft-deleted via `deleted_at`; `roles` holds their granted roles); see [Seeded users](./configuration.md#seeded-users) and [Authorization](../concepts/authorization.md) |
| `auth_sessions` | Server-side login sessions (hashed cookie token + CSRF token); see [Authentication](../concepts/authentication.md) |
| `impersonation_events` | Audit trail of impersonation sessions (`impersonator_id`, `target_user_id`, `started_at`, `ended_at`); see [Authentication](../concepts/authentication.md) |
| `agent_skills` | Agent skill definitions (incl. optional `repo_auth_password` / `repo_auth_username` for private-repo clones) |
| `mcp_servers` | Registered MCP servers (name, `transport`, then either streamable HTTP URL + request headers or stdio command + args + env — header and env values may embed `${secret:NAME/KEY}` placeholders) |
| `secrets` | Named key/value credential bundles: an `entries` map of Fernet-encrypted local values, or a HashiCorp Vault KV v2 path reference; see [Secrets](../guides/secrets.md) |
| `workflows` | Workflow definitions (name, skill reference, lifecycle `status`, AI-summarized `generatedDescription`, user-editable `description`), plus the `session_id` of the design session (the ADK chat) its task templates are designed in and the `agent_skill_commit_sha` that chat is pinned to |
| `workflow_task_templates` | The pre-designed task list of a workflow (`workflow_id` FK with `ON DELETE CASCADE`; dependency edges and MCP tool bindings live in their own `workflow_task_template_*` join tables) |
| `workflow_published_versions` | At most one per workflow: the name, description, and task templates (as JSON) frozen at publish time, which a `modified` workflow runs against; see [Workflows](../guides/workflows.md) |
| `workflow_executions` | One row per run of a workflow: the workflow and skill metadata snapshotted at execute time, plus the `session_id` of the workflow session (the ADK chat) the run happens in (`workflow_id` FK with `ON DELETE SET NULL`, so a run outlives its design) |
| `workflow_tasks` | Individual tasks belonging to a `WorkflowExecution`, copied from the templates at execute time (`workflow_execution_id` FK with `ON DELETE CASCADE`) |
| `workflow_task_tool_bindings` | MCP tools bound to a task (`task_id` FK `ON DELETE CASCADE`, `mcp_server_id` FK `ON DELETE RESTRICT`) |
| `message_meta` | Per-message side-channel facts for the two shared session chats: who sent a message (`sender_user_id`) and which task was in progress (`workflow_task_id`, workflow sessions only). Neither chat has a table of its own, so a row names its parent through exactly one of `workflow_execution_id` (workflow session) / `workflow_id` (design session) — a `CHECK` enforces it, both cascade on delete |
| `sessions` | Session metadata and session-level state |
| `events` | Full event history per session (JSON) |
| `app_states` | App-level shared state |
| `user_states` | Per-user state shared across sessions |

## Seeded users

On startup the backend seeds a hidden **system user**, plus two real accounts, each created only on the very first startup that finds its target record missing:

- An initial **`root`** user holding the **`super_admin`** role (see [Authorization](../concepts/authorization.md)), platform-scoped (`tenantId: null`). Skipped once *any* real (non-system) user already exists, so it runs only on the very first startup.
- A **Default** tenant (`slug: default`) and, inside it, an initial **`admin`** user holding the **`admin`** role. The tenant (by `slug`) and the user (by `username` scoped to that tenant) are checked independently, so either can be recreated without duplicating the other.

The hidden **system user** owns the bootstrap records (it cannot log in and is excluded from the user list).

Passwords are read from environment variables, with the same generate-and-log-once fallback for each:

```env
ROOT_PASSWORD=change-me-now-123
ADMIN_PASSWORD=change-me-now-123
```

If either is unset (or empty), a random password is generated instead and logged **once**, at `WARNING` level, when that user is created — it cannot be recovered once the log line has scrolled past. Set both explicitly before the first run for anything beyond local experimentation, or capture the generated passwords from the startup logs immediately and change them through the user API afterwards. The usernames are fixed to `root` and `admin`.

## Session lifetime

Sessions use a sliding idle timeout: each authenticated request refreshes the session's last-active time, and a session left idle longer than `SESSION_IDLE_TIMEOUT_SECONDS` (default `28800`, 8 hours) is rejected and deleted. The cookies themselves are session cookies (no `Max-Age`/`Expires`), so they are also cleared when the browser closes.

```env
# Sliding idle timeout in seconds (default 28800 = 8 hours)
SESSION_IDLE_TIMEOUT_SECONDS=28800
# Mark cookies Secure (HTTPS only); leave false for local HTTP dev (default false)
SESSION_COOKIE_SECURE=false
```

The frontend reaches the backend through a same-origin Next.js rewrite (`/api/*`), so the cookies are first-party and `SameSite=Lax` applies cleanly. Log in with the seeded `root` or Default-tenant `admin` user (see [Seeded users](./configuration.md#seeded-users)) on first run.

## CORS

```env
CORS_ORIGINS=http://localhost:3000
```

Comma-separated list of origins allowed to call `/chat` and `/sessions`. Defaults to `http://localhost:3000`. Add additional origins when the frontend is served from a different host or port:

```env
CORS_ORIGINS=https://app.example.com,http://localhost:3000
```

`*` is rejected at startup — `allow_credentials=True` is always enabled, and pairing it with a wildcard origin is invalid per the CORS spec.
