# A2Flow

![A2Flow](frontend/assets/logo.png)

A chat application that connects a [Google ADK](https://google.github.io/adk-docs/) agent to a Next.js UI using the [AG-UI protocol](https://docs.ag-ui.com/concepts/events). The agent supports [A2UI](https://a2ui.org/) — when it needs input from the user it renders interactive A2UI input components (text fields, choice pickers, buttons) so the user can see exactly what to provide, while purely informational replies stream token-by-token as Markdown-rendered text so the user never waits on a tool call.

The frontend uses a **glassmorphism** visual style with a **light/dark theme toggle** (persisted in `localStorage`, defaults to the OS preference). See [DESIGN.md](DESIGN.md) for the full design system reference. A **notification center** in the top toolbar surfaces workflow events such as plan approval requests (see [Notifications](#notifications)).

```
┌──────────────────────────────────┐    AG-UI RunAgentInput (JSON)    ┌──────────────────────┐
│   Next.js frontend               │  (render_a2ui tool injected by   │  FastAPI backend     │
│   @ag-ui/client                  │ ───────────────────────────────► │  Google ADK agent    │
│   @ag-ui/a2ui-middleware         │   A2UIMiddleware)                 │  AGUIToolset         │
│   Redux Toolkit                  │                                   │  DB SessionService   │
│   Admin UI (/admin)              │ ◄─────────────────────────────── │  SQLite/PostgreSQL   │
└──────────────────────────────────┘  AG-UI events (SSE) incl.        └──────────────────────┘
     :3000                            A2UI (TOOL_CALL_*)                    :8000
```

## Project homepage

A single-page static homepage lives in [homepage/](homepage/) and is published to GitHub Pages at <https://kaitoy.github.io/a2flow/> by the [pages.yml](.github/workflows/pages.yml) workflow, which runs on every push to `master` that touches `homepage/**`. One-time setup: in the repository **Settings → Pages**, set **Source** to **GitHub Actions**.

To preview it locally, serve the directory with Python's built-in HTTP server and open the printed URL:

```bash
cd homepage
python -m http.server
```

Open [http://localhost:8000](http://localhost:8000).

## Repository layout

```
a2flow/
├── backend/   # FastAPI + Google ADK agent
├── frontend/  # Next.js 16 chat UI
└── homepage/  # Static project homepage (GitHub Pages)
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

The async driver suffix (`aiosqlite` / `asyncpg`) is added automatically. Schema changes are tracked as versioned [Alembic](https://alembic.sqlalchemy.org/) migrations (`backend/alembic/versions/`) and applied automatically on startup — redeploying the app (a container restart) is what runs any pending migrations, so no separate migration step is needed.

The database is also what coordinates a multi-replica backend: an agent run holds a PostgreSQL advisory lock on its ADK session for the length of its SSE stream, so one conversation is never driven by two replicas at once. See [Horizontal scaling](backend/README.md#horizontal-scaling) for what that protects and the constraint it places on connection pooling.

## Authentication

The app requires sign-in. Visiting any page while logged out redirects to `/login`. On first run, log in with the seeded **`admin`** user: set `ADMIN_PASSWORD` before the first startup, or, if left unset, read the randomly generated password from `docker compose logs backend` (printed once and not recoverable afterwards). Manage additional users from the [admin UI](#users). After signing in the user lands on the [welcome page](#welcome-page).

- **Session** — login creates a server-side session (`auth_sessions` table) and sets an HttpOnly `a2flow_session` cookie holding an opaque token (only its hash is stored). Sessions use a sliding **idle timeout** (`SESSION_IDLE_TIMEOUT_SECONDS`, default 8 hours).
- **CSRF** — login also sets a readable `a2flow_csrf` cookie; the frontend echoes it in the `X-CSRF-Token` header on every state-changing request (double-submit cookie). The backend rejects mismatches with `403`.
- **Same-origin proxy** — the browser calls the frontend origin (`:3000`); Next.js rewrites `/api/*` to the backend (`:8000`), so the auth cookies are first-party and `SameSite=Lax` works. Point the proxy elsewhere with `BACKEND_BASE_URL`.

See [backend/README.md](backend/README.md#authentication) for the endpoint and cookie details.

## Roles and authorization

Every user holds a set of **roles** granting the operations they may perform. Roles are **independent** — there is no hierarchy, and a user may hold any combination of them — with one exception: **Super Admin bypasses every check**. A user with **no roles at all** is valid: they can still use the regular chat and manage their own [account](#users) (avatar), but nothing else.

| Role | Grants |
|---|---|
| `super_admin` | Everything (bypasses every role and ownership check) |
| `admin` | User CRUD, secrets CRUD |
| `developer` | MCP server CRUD, workflow CRUD, agent-skill CRUD |
| `requester` | Running workflows (`POST /workflows/{id}/execute`) |
| `approver` | Eligibility to be a workflow approval's designated approver, and resolving their own approvals |

**Reads stay open.** Only writes, workflow execution, and approvals are role-gated; every authenticated user may `GET` the collections (the UI needs them to resolve names, pick approvers, and list workflows). Secret *values* are never returned by the API regardless of role. Roles are assigned from the [Users](#users) admin page; only a Super Admin may grant or revoke `super_admin`. A rejected request returns HTTP 403 (`FORBIDDEN`), and the admin UI hides the actions and nav entries a user's roles do not allow.

The initial seeded **`admin`** user holds `super_admin`. Upgrading an existing deployment grants `super_admin` to that user automatically (Alembic data migration); every other existing user starts with no roles.

**Workflow session access.** Beyond roles, each operation on a workflow session — reading it, loading its chat history, listing or editing its tasks, and driving its agent — requires the caller to be the session's **owner** (the user who ran the workflow) or a **designated approver of one of its approvals** (see [Human approval](#human-approval)); unrelated users get HTTP 403. This preserves the approver-sharing design (the approver joins the owner's chat) while keeping third parties out. **Deleting** a session is stricter still: owner (or Super Admin) only.

⚠️ Approver eligibility is validated when the approval is created: the agent's `list_users` tool only offers users holding `approver`, and `request_approval` rejects anyone else. Revoking the `approver` role later does **not** invalidate approvals already addressed to that user — they can still resolve them, so an in-flight workflow never gets stuck.

## Admin UI

The admin area lives at [http://localhost:3000/admin](http://localhost:3000/admin).

### Welcome page

[http://localhost:3000/admin](http://localhost:3000/admin) is the welcome landing page. It renders inside the admin shell (sidebar + app bar) and greets the user with quick-action cards that link to a new chat and each admin section. This is where the user lands when visiting the site root (`/`), after signing in, and when clicking the **A2Flow** logo in the app bar from any screen.

Every admin list table shares interactive features: **per-column sorting and filtering** (applied server-side via the list APIs' `s` and `q` query parameters, so they cover the whole dataset rather than just the current page), **drag-to-resize column widths** (kept for the session, not persisted), and **hover tooltips** that reveal the full text of any cell clipped to its column width.

### Users

Navigate to [http://localhost:3000/admin/users](http://localhost:3000/admin/users) to manage application users.

| Operation | Path |
|-----------|------|
| List all users | `GET /admin/users` |
| Create a new user | `GET /admin/users/new` |
| Edit / delete a user | `GET /admin/users/{id}` |

Each user record stores a username (unique), first name, last name, email, an `enabled` flag, an `emailVerified` flag, and the user's [roles](#roles-and-authorization). Passwords are hashed with [bcrypt](https://pypi.org/project/bcrypt/) before persistence and are never returned by the API. On edit, leaving the password field blank keeps the existing password. Users are persisted in `a2flow.db`.

**Roles.** The create and edit forms include a roles picker (one checkbox per role); the list shows each user's roles in a **Roles** column. Roles are stored as a JSON list, so they cannot be sorted or filtered server-side via the list API's `s` / `q` parameters. The **Super Admin** checkbox is disabled unless the signed-in user is a Super Admin — the backend rejects granting or revoking it otherwise.

**Avatars.** Every user has an avatar shown on the toolbar account button and in the admin user list and editor. By default it is a deterministic illustration generated client-side from the username with [Humation](https://github.com/humation-labs/humation) — no image is stored and no network call is made. A signed-in user manages their own avatar from the self-service account page (toolbar account menu → **Account**, at `/account`): **upload** a custom image (PNG, JPEG, WebP, or GIF, up to 2 MB) or remove it, and **customize** the generated avatar by picking a part per group, overriding colors, and choosing a background. The customization is stored as `UserRead.avatarConfig` (part `selections`, `colors`, and `background`) and applied wherever the avatar renders; unspecified parts stay seeded from the username. Avatar editing is self-service only — the admin user editor shows the avatar read-only, with no upload or customization controls. An uploaded image is stored in a dedicated `user_avatars` table and served from `GET /api/v1/users/{id}/avatar`, with `UserRead.avatarUpdatedAt` acting as a presence marker and cache-busting key; uploading or removing it refreshes the signed-in user everywhere, so the toolbar account button updates immediately. Precedence is **uploaded image → customized Humation → username-seeded Humation**; removing the image or resetting the customization falls back to the next option.

**Audit ownership.** Every persistent record stores `createdBy` / `updatedBy` as a foreign key to `users.id`, populated from the **authenticated session** (see [Authentication](#authentication)). A write whose acting user does not exist is rejected with HTTP 422 (`FOREIGN_KEY_VIOLATION`). To resolve the bootstrap "who creates the first user" problem, a hidden, login-disabled **system user** is seeded on startup when the `users` table is empty, and it owns the initial seeded `admin` user. In the admin UI the raw IDs are never shown — each detail page resolves `createdBy` / `updatedBy` to the user's `first last` name, and list views resolve user IDs the same way.

**Deleting a user.** If no other record references the user, it is hard-deleted from the database. If it is still referenced (via any `createdBy` / `updatedBy`), it is instead **soft-deleted**: `deletedAt` is set and the account is disabled, so existing references stay valid and the name still resolves. Soft-deleted users (and the system user) are hidden from the user list but remain fetchable by id.

### Agent Skills

Navigate to [http://localhost:3000/admin/agent-skills](http://localhost:3000/admin/agent-skills) to manage the Agent Skills registry — a catalog of AI agent skills stored in Git repositories.

| Operation | Path |
|-----------|------|
| List all skills | `GET /admin/agent-skills` |
| Register a new skill | `GET /admin/agent-skills/new` |
| Edit / delete a skill | `GET /admin/agent-skills/{id}` |

| Pull a skill's repository | `POST /api/v1/agent-skills/{id}/pull` |

Skills are persisted in a SQLite database (`a2flow.db` by default, configurable via `DB_URL` in `backend/.env`). Each record stores the skill name, repository URL, repository path, and description.

#### The skill store

Registering a skill returns immediately and **shallow-clones its repository in the background** using [Dulwich](https://www.dulwich.io/) — no external `git` CLI required. The clone is published into the skill store under `SKILLS_DIR` as one immutable directory per revision:

```
$SKILLS_DIR/<agent_skill_id>/<commit_sha>/
```

The clone is staged in a temporary sibling directory and moved into place with a single atomic rename, so a replica reading the store never sees a half-written revision. A published revision is then **never modified** — a pull only ever adds a sibling.

The list and edit pages show each skill's **Status** (`Cloning` / `ready` / `failed`, with the failure reason) and the short **Revision** it has published. Two fields carry that state, and they mean different things:

- **`commitSha`** — the published revision. A skill is runnable **only** once this is set; a workflow started against a skill with no revision is rejected with HTTP 409 (`SKILL_NOT_READY`).
- **`syncStatus`** — how the *last* clone or pull went. A pull that fails does **not** clear `commitSha`, so a skill that was working keeps working at its previous revision; only the status and the error change.

**Pull** re-clones the repository at its current remote HEAD. It is how a skill picks up upstream changes, and how a failed registration clone is retried after fixing the URL or the credentials. Concurrent clones of one skill are serialized across replicas by the advisory lock in `backend/infrastructure/locks.py`; a replica that finds another already cloning the skill skips the work instead of duplicating it. After a successful pull, revisions that no longer back any workflow session are pruned.

Under `docker compose`, `SKILLS_DIR` is `/var/lib/a2flow/skills`, persisted in the `skills` Docker volume so the store survives container recreation. It is **durable state, not a cache**: a workflow session pins the revision it started with, so wiping the directory leaves existing sessions unable to load their skill until an admin pulls again. Scaling the backend past one replica requires every replica to mount this same volume.

Private repositories are supported through the optional **Auth Secret** field: set it to the name of a registered [Secret](#secrets) and its value is used as the HTTP basic-auth password (typically a personal access token) when the repository is cloned. The **Auth Username** field defaults to `x-access-token` (suitable for GitHub PATs); set it explicitly for hosts that require a real account name. The secret is resolved at clone time, so deleting or renaming it later makes the next pull fail and record the reason on the skill.

### MCP Servers

Navigate to [http://localhost:3000/admin/mcp-servers](http://localhost:3000/admin/mcp-servers) to manage the registry of remote [MCP](https://modelcontextprotocol.io/) servers whose tools the workflow agent can bind to WorkflowTasks (see [MCP tools for tasks](#mcp-tools-for-tasks)).

| Operation | Path |
|-----------|------|
| List all servers | `GET /admin/mcp-servers` |
| Register a new server | `GET /admin/mcp-servers/new` |
| Edit / delete a server | `GET /admin/mcp-servers/{id}` |

Each record stores a unique name, the server's **streamable HTTP** endpoint URL (SSE-only servers are not supported), and an optional set of HTTP headers sent with every request — typically `Authorization: Bearer …` for servers that require auth. ⚠️ Literal header values are stored **in plaintext** in `a2flow.db` and returned by the API; instead of embedding a credential directly, reference a registered [Secret](#secrets) with the `${secret:name}` placeholder syntax (e.g. `Authorization: Bearer ${secret:github-token}`) — placeholders are expanded only at connect time and the credential never appears in the stored record or any API response.

The list page's **Browse registry** button opens a search dialog backed by the official [MCP registry](https://registry.modelcontextprotocol.io/) (`GET /api/v1/mcp-registry`). It searches servers by name and lists only those reachable over streamable HTTP (the only transport A2Flow supports). Picking a result opens the create form pre-filled with the server's name, URL, and required header keys, so you only fill in secret header values before saving. The registry base URL is configurable via the `MCP_REGISTRY_URL` env var; an unreachable registry yields HTTP 502 (`REGISTRY_UNREACHABLE`).

`GET /api/v1/mcp-servers/{id}/tools` queries the live server and returns the tools it advertises (name, description, input schema); the admin task forms use it to populate the tool picker. An unreachable server yields HTTP 502 (`MCP_UNREACHABLE`). A server cannot be deleted while WorkflowTask tool bindings still reference it (HTTP 409 `CONFLICT_REFERENCED`).

### Secrets

Navigate to [http://localhost:3000/admin/secrets](http://localhost:3000/admin/secrets) to manage named credentials used for authentication elsewhere in the app:

- **MCP server headers** — any header value may embed `${secret:name}` placeholders, expanded when connecting (see [MCP Servers](#mcp-servers)).
- **Agent Skill repository clones** — a skill's **Auth Secret** names the secret whose value is used as the git basic-auth password (see [Agent Skills](#agent-skills)).

| Operation | Path |
|-----------|------|
| List all secrets | `GET /admin/secrets` |
| Register a new secret | `GET /admin/secrets/new` |
| Edit / delete a secret | `GET /admin/secrets/{id}` |

A secret has one of two types:

- **Local (encrypted)** — the value is submitted once and stored in `a2flow.db` encrypted with [Fernet](https://cryptography.io/en/latest/fernet/) (AES-128-CBC + HMAC). The API is **write-only**: no response ever contains the value (neither plaintext nor ciphertext); the edit form leaves the value blank, and leaving it blank on save keeps the stored value.
- **HashiCorp Vault** — only a [KV v2](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2) reference (mount, path, key) is stored; the value is read live from Vault each time the secret is resolved.

Secrets are referenced **by name** and resolved lazily: renaming or deleting a secret that something still references does not fail at edit time, but the next use fails with HTTP 502 (`SECRET_RESOLUTION_FAILED`) naming the missing secret.

#### Encryption key

The Fernet key for local secrets is resolved at first use with the following precedence:

1. `SECRET_ENCRYPTION_KEY` env var (must be a valid Fernet key; generate one with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
2. The key file at `SECRET_KEY_FILE` (default: `.secret_key` next to the SQLite database file, or the working directory for other databases).
3. A fresh key is generated, saved to that file, and a WARNING is logged.

⚠️ Back the key up — losing it makes every stored local secret undecryptable.

#### HashiCorp Vault connection

A single global Vault connection is configured through env vars (see `backend/.env.example`): `VAULT_ADDR` selects the server, and either a static `VAULT_TOKEN` or **AppRole** credentials (`VAULT_ROLE_ID` + `VAULT_SECRET_ID`, login mount configurable via `VAULT_APPROLE_MOUNT`, default `approle`) authenticate. AppRole takes precedence when both are set; its client token is cached and refreshed automatically when its lease expires. Only the KV v2 secrets engine is supported. When Vault is not configured, `vault`-type secrets fail to resolve with `SECRET_RESOLUTION_FAILED`.

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

1. The backend checks that the linked [Agent Skill](#agent-skills) has a published revision (`commitSha`) — the repository was cloned when the skill was registered, so **nothing is cloned here**. A skill whose clone has not published a revision yet, or whose clone failed, is rejected with HTTP 409 (`SKILL_NOT_READY`).
2. A `WorkflowSession` record is persisted to the database, capturing the workflow name, prompt, skill details, the ADK session ID, and the skill revision the run is **pinned** to (`agentSkillCommitSha`). Because revision directories are immutable, a later pull of that skill cannot swap the code out from under a conversation already in progress — and because the store is shared, any replica resolves the same code. The ADK session itself is created lazily on the first agent call.
3. The backend returns the `WorkflowSession` (HTTP 201). The frontend redirects to `/workflow-sessions/{workflowSession.id}`.
4. On mount, the `/workflow-sessions/{id}` page fetches the `WorkflowSession`, and if no prior messages exist for the session, it automatically sends `workflow.prompt` as the first user message via `POST /workflow-sessions/{id}/agent`. The page renders the same shared app bar as the regular chat (notification bell, theme toggle, and account menu), with the workflow name shown beside the title; its **A2Flow** logo links to the [welcome page](#welcome-page).
5. The `/workflow-sessions/{id}/agent` endpoint loads the skill-bound `ADKAgent` (keyed by `agent_skill_id` **and** the pinned revision) and streams AG-UI SSE events back, identical to the regular `POST /agent` endpoint. The agent runs under a **plan-then-execute** workflow instruction and is equipped with WorkflowTask management tools (see below).
6. Subsequent user messages continue to flow through `POST /workflow-sessions/{id}/agent`, so A2UI rendering, A2UI user actions (e.g. clicking a rendered button), and the full chat experience work normally.

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

1. The agent calls the `request_approval` backend tool, which persists a `pending` **Approval** record for the current session (optionally linked to a `WorkflowTask`) addressed to a specific **`approver`** user — the agent looks one up with the `list_users` tool (which lists only users holding the [`approver` role](#roles-and-authorization)), and the approver is **required**. It raises an **approval-request notification** addressed to that approver, so only they are alerted.
2. The agent explains the request in plain text and then calls **`render_approval`** — an AG-UI **frontend tool** (declared by the client via `RunAgentInput.tools`, distinct from A2UI). Like `render_a2ui`, the bridge exposes it as a long-running client tool: the run pauses and the frontend renders **Approve / Reject** controls, plus an optional **comment** field, in the chat. The controls are shown **only to the designated approver**; everyone else sees a read-only "waiting for the approver" message.
3. Clicking a button writes the decision (and any comment) **directly** to the backend via `PATCH /api/v1/approvals/{id}` (recording the resolving user in the audit fields), then returns the decision as the tool result so the agent run resumes. Only the designated approver (or a Super Admin) may resolve a request — a `PATCH` from any other user is rejected with HTTP 403 (`FORBIDDEN`).
4. On `approved` the agent proceeds; on `rejected` it marks the task `failed` (or `skipped`). The agent can re-check a decision with the `get_approval` tool.

Approvals are persisted in `a2flow.db` and cascade-delete with their `WorkflowSession` (the optional `WorkflowTask` link is set to `NULL` when that task is deleted). Browse them in the [Approvals](#approvals) admin view.

A workflow session's underlying ADK chat session is keyed by the session's **owner** (the user who started it), not by whoever is currently viewing it. So when a designated approver — a different user — opens the workflow session chat, they share the **same** ADK session: they see the owner's full conversation and state, and approving resumes the original run rather than starting a fresh, empty session. Both the agent stream (`POST /workflow-sessions/{id}/agent`) and the history load (`GET /workflow-sessions/{id}/messages`) resolve the owner from the `WorkflowSession` record. (Regular, non-workflow chat sessions remain keyed per user.) Sharing is limited to those participants: any other user is rejected with HTTP 403 — see [Roles and authorization](#roles-and-authorization).

Because that one chat is shared, several people (the **applicant**/owner, designated **approvers**, and the **agent**) post into it, so each message carries a **sender avatar** to show who sent it — the applicant's or approver's avatar beside their messages, and an agent badge (hover shows the workflow name) beside the agent's. Clicking a button inside a rendered A2UI surface is attributed the same way: it shows the acting user's avatar beside that surface once resolved. ADK records every human message under the author `user`, and A2UI action acknowledgements as tool-response (function-response) events, so the backend attributes both to their real sender: the agent run endpoint snapshots the session's existing `user` events and tool-response `tool_call_id`s, then records the current user as the sender of any new ones once the run ends, and `GET /workflow-sessions/{id}/messages` returns each message's `senderUserId`. That includes a run that ends badly: a client disconnecting mid-stream (tab closed, page reloaded) cancels the run, but the messages it already appended are attributed on the way out rather than silently left ownerless. Tool-response messages are keyed by `tool_call_id` rather than their own id, since the AG-UI/ADK bridge regenerates a fresh id for them on every read. Messages with no recorded sender (history sent before attribution existed) fall back to the owner. Hovering an avatar reveals the sender's name.

Per-message side-channel facts like this live in a single **`message_meta`** table keyed by `(workflow_session_id, adk_event_id)`, with nullable columns the run-completion step upserts independently — currently `sender_user_id` (above) and `workflow_task_id` (below).

Because the chat is shared, the page **polls `GET /workflow-sessions/{id}/messages` every 10 seconds** so each participant sees the others' messages (and the agent's progress) without reloading. Polling pauses while the viewer's own agent run is in flight (so it never clobbers the live stream), skips re-applying an unchanged history, and the view follows new messages to the bottom only when the viewer is already scrolled near the bottom.

The chat screen also shows a collapsible **task timeline** down the left edge: the session's `WorkflowTask`s in order, each with a numbered, status-coloured badge, with the in-progress task highlighted. The agent drives the task lifecycle by calling `update_workflow_task(status="in_progress")` before working on a task, so after each run the backend walks the session's events in order, tracks the most recent such transition, and records the in-progress task for every following message as that message's `workflow_task_id`. `GET /workflow-sessions/{id}/messages` returns each message's `workflowTaskId`, and the chat wraps each run of consecutive same-task messages in a **task group** — a status-coloured left rail with a numbered heading whose number matches the timeline badge — so the boundary of each task is obvious at a glance. The timeline and chat are linked both ways: scrolling the chat highlights the task at the top of the viewport in the timeline (scroll-spy), hovering either a timeline entry or a chat group highlights its counterpart, and clicking a timeline entry scrolls the chat to that task's group.

### Workflow Sessions

Navigate to [http://localhost:3000/admin/workflow-sessions](http://localhost:3000/admin/workflow-sessions) to browse every executed `WorkflowSession`. Each row links to the chat UI (`/workflow-sessions/{id}`) and to the nested **Workflow Tasks** admin page (`/admin/workflow-sessions/{id}/workflow-tasks`) where individual tasks belonging to that session can be created, edited, deleted, and have their status updated inline. A row's **Delete** action removes the `WorkflowSession` after a confirmation prompt: the record, its tasks (cascade), and the underlying ADK chat session are all deleted. The create and edit forms include a **Depends on** picker for selecting which other tasks in the same session a task depends on (its DAG edges); dependencies are shown as a column on the list, and edges that would form a cycle are rejected by the server. The Workflow Tasks page offers a **Table / Graph** toggle: the Graph view renders the task DAG with [React Flow](https://reactflow.dev/), auto-laid-out top-to-bottom with [dagre](https://github.com/dagrejs/dagre) so prerequisites sit above the tasks that depend on them. The graph is read-only (pan / zoom / fit) — dependencies are edited from the task forms.

| Operation | Path |
|-----------|------|
| List all sessions | `GET /admin/workflow-sessions` |
| Delete a session | `DELETE /api/v1/workflow-sessions/{id}` |
| List a session's tasks | `GET /admin/workflow-sessions/{id}/workflow-tasks` |
| Create a task | `GET /admin/workflow-sessions/{id}/workflow-tasks/new` |
| Edit / delete a task | `GET /admin/workflow-sessions/{id}/workflow-tasks/{taskId}` |

### Approvals

Navigate to [http://localhost:3000/admin/approvals](http://localhost:3000/admin/approvals) to browse every **Approval** request (see [Human approval](#human-approval)). The list shows the title, status (`pending` / `approved` / `rejected`), the designated approver, the approver's comment, a link to the originating `/workflow-sessions/{id}` chat, and the creation time, with sort and filter controls. Decisions are normally made from the in-chat Approve / Reject controls; this view is read-only browsing. The `GET`/`PATCH /api/v1/approvals` endpoints are documented in the [API reference](http://localhost:3000/api-doc).

## Notifications

A **bell icon** in the top toolbar (present on both the chat header and the admin sidebar) opens a notification center with an unread-count badge. Notifications are **per-user**, persisted in `a2flow.db`, and delivered by **polling** (the frontend refreshes every 30 seconds).

Two workflow events generate a notification, both raised by the agent's task tools. The recipient depends on the event: a `request_approval` notification is addressed to that approval's **designated approver**, while a `register_workflow_tasks` plan-approval notification and the `session_completed` notification are addressed to the **user who started the session**:

| Type | Raised when |
|---|---|
| `approval_request` | The agent registers a plan (`register_workflow_tasks`) and waits for the session owner's approval, or requests a mid-execution decision (`request_approval`) and waits for the designated approver. |
| `session_completed` | Every `WorkflowTask` in the session has reached a terminal state (`completed` / `failed` / `skipped`) — emitted once per session. |

Clicking a notification marks it read and deep-links to the relevant `/workflow-sessions/{id}` chat. Each row also has a **dismiss (✕)** button that permanently deletes that notification, and the panel header offers a **"Mark all read"** action (shown only while unread items remain) that clears every unread notification at once.

The list (`?unreadOnly=true` for unread), mark-read, mark-all-read, and delete endpoints are documented in the [API reference](http://localhost:3000/api-doc); all are scoped to the authenticated user, so reading, updating, or deleting another user's notification returns HTTP 404. Notifications cascade-delete with their recipient user and their linked `WorkflowSession`.

## Agent activity in the chat

So you can see what the agent is doing between replies, its intermediate work is
surfaced inline in the chat stream:

- **Working indicator** — while a run is in flight but nothing is on screen yet, a
  subtle "考えています…" pulse appears at the bottom of the message list.
- **Tool-call lines** — every backend tool call (e.g. `create_workflow_task`,
  `list_workflow_tasks`) becomes a compact status line that transitions from a
  spinner (`running…`) to a check (`done`). Calls routed through the
  `call_mcp_tool` proxy are shown under the **real MCP tool name** with an `MCP`
  tag. The `render_a2ui` / `render_approval` client tools keep their dedicated UI
  and are not shown as tool lines.
- **Reasoning** — when a thinking-capable model emits `REASONING_*` events, the
  streamed thoughts render as a muted "Thinking" panel. The default
  `gemini-3.5-flash` reasons internally but does not stream thought summaries
  unless they are enabled, so the panel only appears with a model configured to
  emit them.

On session resume, only **MCP tool calls** (`call_mcp_tool`) are reconstructed
from history; internal A2Flow tool calls and reasoning are live-only.

## How it works

1. When the user clicks "+ New session", the frontend navigates to `/newSession` without contacting the backend. The session ID (`threadId`) is generated by the frontend (`crypto.randomUUID()`) at the moment the user submits the first message; the ADK session is created implicitly by the backend on the first `POST /agent` request that references it. The page URL is then replaced with `/sessions/{id}` so the streamed response continues under the canonical session route.
2. When the user submits a message, `createChatAgent()` creates an `HttpAgent` (from `@ag-ui/client`) that sends the auth session cookie (`credentials: "include"`) and the `X-CSRF-Token` header, with `A2UIMiddleware` (from `@ag-ui/a2ui-middleware`) applied. Before each request reaches the backend, the middleware injects the `render_a2ui` tool into `RunAgentInput.tools` and the A2UI Basic Catalog schema (downloaded from `https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json` at build time) into `RunAgentInput.context`.
3. The backend's `ADKAgent` (from `ag-ui-adk`) bridges the AG-UI protocol to a Google ADK `LlmAgent` — translating events, managing sessions, and streaming AG-UI SSE events back to the client. The agent uses `AGUIToolset`, which the bridge replaces at runtime with a `ClientProxyToolset` built from `RunAgentInput.tools` — making the frontend-injected `render_a2ui` tool callable by the LLM.
4. When the LLM calls `render_a2ui`, the `ADKAgent` streams `TOOL_CALL_*` events. The `A2UIMiddleware` intercepts these, reconstructs the A2UI operations, and emits `ACTIVITY_SNAPSHOT` events (one per surface, `activityType: "a2ui-surface"`). No tool execution happens on the backend.
5. The frontend's `AgentSubscriber` (built by `createAgentSubscriber` in `src/lib/agentSubscriber.ts`, shared by both chat surfaces) dispatches each event to a Redux store. Text events update the chat incrementally; assistant text is rendered as Markdown (`marked`, styled by the `markdown-body` utility). `TOOL_CALL_*` events for non-rendering tools and `REASONING_*` events are mapped to `activity` messages (`activityType: "tool_call"` / `"reasoning"`) and rendered inline by `ToolActivityBubble` / `ReasoningBubble` (see [Agent activity in the chat](#agent-activity-in-the-chat)). `ACTIVITY_SNAPSHOT` events carry A2UI operations under the `a2ui_operations` key, which are stored in Redux. `A2uiRenderer` feeds the operations to `MessageProcessor` (from `@a2ui/web_core/v0_9`) and renders surfaces via `<A2uiSurface>`. Component rendering uses `tailwindCatalog` — a custom `Catalog<ReactComponentImplementation>` in `src/components/a2uiCatalog.tsx` that provides Tailwind CSS–styled versions of `Text`, `Button`, `Card`, `Row`, `Column`, `TextField`, and `ChoicePicker`. `marked` is used as the markdown renderer via `MarkdownContext`.
6. When the LLM calls `render_a2ui`, `useChat` captures the tool call ID via `onToolCallEndEvent` and stores it in `pendingRenderCalls`. When the user triggers an action on the rendered surface (e.g. clicking a `Button`), `sendA2uiAction` sends a tool result message for that `render_a2ui` call directly to `POST /agent`. This lets the backend match the result against the pending `render_a2ui` tool call and forward it to the LLM, which then responds to the user's action. `forwardedProps.a2uiAction` / `A2UIMiddleware.processUserAction` is not used. The tool result is a **JSON object** carrying the surface's entire data model under `values` — every value the user typed or selected. It is JSON rather than prose because `ag-ui-adk` wraps any tool result it cannot parse as JSON before persisting it, which would change its shape on reload; and it carries the whole data model rather than the action's `context` because `context` holds only the bindings the agent chose to declare on the acted-on component. Together these let the agent read the real input, and let a reloaded session redisplay an answered surface pre-filled with what the user submitted instead of the agent's defaults (see [docs/a2ui-flow.md](docs/a2ui-flow.md)).
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

The AG-UI streaming endpoint (`POST /agent`) is marked `include_in_schema=False` and is intentionally excluded from the spec — its events are typed by `@ag-ui/core`. The `{meta, data, error}` response envelope is built by the routes themselves (each declares `response_model=ApiResponse[T]` and returns `ApiResponse(meta=…, data=…)`) and by the exception handlers for errors, so its shape **is** part of the spec. The generated Zod schemas therefore describe the whole envelope; the frontend's internal `fetchEnvelope()` helper parses it and returns the inner `data` (throwing `ApiClientError` if the envelope carries an error body).

`pnpm generate:api` (frontend) runs the backend export step via `uv` first, then the Zod codegen — so a single command keeps both layers in sync. The frontend's `predev` and `prebuild` hooks invoke it automatically, so `pnpm dev` and `pnpm build` regenerate the spec and schemas on every run. `uv` must be available on `PATH`.

### Interactive API reference

An interactive [Scalar](https://scalar.com/) reference is served at [http://localhost:3000/api-doc](http://localhost:3000/api-doc). It loads the FastAPI app's live OpenAPI document (`/openapi.json`, proxied to the backend by `next.config.ts`), so it always reflects the running backend. The page is behind the same login gate as the rest of the app.

## List query parameters

Every collection endpoint accepts a shared set of `limit` / `offset` / sort (`s`) / filter (`q`) query parameters, with camelCase field names. See [.claude/rules/api-conventions.md](.claude/rules/api-conventions.md) for the full reference.

## LLM configuration

Set `LLM_MODEL` in `backend/.env`:

| Provider | Value |
|---|---|
| Google Gemini (default) | `gemini-3.5-flash` |
| OpenAI via LiteLLM | `litellm:openai/gpt-4o` |
| Anthropic via LiteLLM | `litellm:anthropic/claude-3-5-sonnet-20241022` |

See [backend/README.md](backend/README.md) for the full configuration reference.

## Further reading

- [backend/README.md](backend/README.md) — API reference, environment variables, running options
- [frontend/README.md](frontend/README.md) — project structure, component overview, environment variables
