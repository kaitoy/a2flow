# A2Flow Backend

A Google ADK agent with [A2UI](https://a2ui.org/) support. Accepts prompts via HTTP POST and streams responses as AG-UI SSE events. The agent can return plain text or structured A2UI surfaces for rich UI rendering.

## Requirements

Python and [uv](https://docs.astral.sh/uv/) are pinned in [mise.toml](../mise.toml) and installed by `mise install` — see [Quick start](../README.md#0-toolchain-mise). Without mise, install Python 3.11+ and uv by hand.

`uv sync` resolves the interpreter from `PATH` (`python-preference = "only-system"` in [pyproject.toml](pyproject.toml)) rather than downloading its own, so `backend/.venv` uses the Python version mise pins.

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

Every environment variable the backend reads is documented in the manual, and
[.env.example](.env.example) is the annotated template:

| | |
|---|---|
| [LLM configuration](https://kaitoy.github.io/a2flow/docs/getting-started/llm-configuration) | `LLM_MODEL` and the provider API keys |
| [Configuration reference](https://kaitoy.github.io/a2flow/docs/operations/configuration) | Server settings, the agent skill store, secret management, the database, the seeded users, session lifetime, CORS |
| [Demo data](https://kaitoy.github.io/a2flow/docs/getting-started/demo-data) | `DEMO_DATA` and the records it seeds |
| [Horizontal scaling](https://kaitoy.github.io/a2flow/docs/operations/scaling) | What running more than one replica requires |
| [Deployment](https://kaitoy.github.io/a2flow/docs/operations/deployment) | Reverse proxy and load balancer settings |

What follows is the part of the request path that is implementation detail
rather than configuration.

## Authentication

All API routes except `POST /api/v1/auth/login` and `GET /api/v1/health` require an authenticated session. Authentication is cookie-based and backed by the `auth_sessions` table.

**Flow**

1. `POST /api/v1/auth/login` with `{ "username", "password", "tenantSlug"? }`. `tenantSlug` disambiguates a tenant-scoped user's username (unique only within its tenant) and must be omitted for a platform-scoped user (e.g. `root`). On success the response sets two cookies and returns the current user (without the password hash):
   - `a2flow_session` — HttpOnly, `SameSite=Lax` opaque session token. Only its SHA-256 hash is stored server-side.
   - `a2flow_csrf` — readable (non-HttpOnly), `SameSite=Lax` CSRF token.
2. The browser sends both cookies automatically on subsequent requests. For state-changing requests (`POST`/`PUT`/`PATCH`/`DELETE`) the client must echo the CSRF cookie value in the `X-CSRF-Token` header (double-submit cookie defense). A mismatch or missing header returns `403 CSRF_FAILED`.
3. `GET /api/v1/auth/me` returns the current user; `POST /api/v1/auth/logout` revokes the session and clears the cookies.

A missing or invalid session returns `401 UNAUTHENTICATED`.

Sessions use a sliding idle timeout, and the cookies themselves are session cookies (no `Max-Age`/`Expires`), so they are also cleared when the browser closes. `SESSION_IDLE_TIMEOUT_SECONDS` and `SESSION_COOKIE_SECURE` are documented under [Session lifetime](https://kaitoy.github.io/a2flow/docs/operations/configuration#session-lifetime).

The frontend reaches the backend through a same-origin Next.js rewrite (`/api/*`), so the cookies are first-party and `SameSite=Lax` applies cleanly. Log in with the seeded `root` or Default-tenant `admin` user (see [Seeded users](https://kaitoy.github.io/a2flow/docs/operations/configuration#seeded-users)) on first run.

**Impersonation.** A signed-in `admin`/`super_admin` can act as another user via a request header, `X-Impersonate-User-Id`, rather than a second session — the real session cookie never changes, so stopping never requires re-authenticating. `get_current_user` (`dependencies/auth.py`) re-validates the header on **every** request carrying it (not just when impersonation starts): it resolves the real session identity first (`RealUserDep` / `get_session_user`), then, if the header names a user with an open, still-valid impersonation, returns that user as the *effective* identity instead — which is what `CurrentUserDep`/`CurrentUserIdDep`/`CurrentTenantIdDep` resolve to everywhere else in the app, so authorization, tenant scoping, and `createdBy`/`updatedBy` audit fields all transparently apply to the impersonated user with no other code changes. An invalid or stale header (target since disabled, promoted, or already stopped elsewhere) is never an error — it silently falls back to the real user, since the frontend attaches a persisted selection starting with the very first `/auth/me` call on page load, and failing that call would otherwise boot a legitimate admin out of the whole app over a merely stale local selection.

- `POST /api/v1/auth/impersonate` — body `{ "targetUserId" }`; starts impersonating, opening an `impersonation_events` row. A `super_admin` may target any user platform-wide; an `admin` only within their own tenant (a cross-tenant target id returns `404 NOT_FOUND`, not `403`, so its existence in another tenant is never confirmed). Targeting a `super_admin`, the caller themself, a disabled/soft-deleted user, or the seeded system user returns `403 FORBIDDEN` — as does targeting an `admin`, unless the caller is themself a `super_admin`.
- `DELETE /api/v1/auth/impersonate` — stops impersonating, closing the open `impersonation_events` row; a no-op (never an error) if nothing is open.
- `GET /api/v1/auth/me` returns `{ "user", "impersonatedBy" }`: `user` is the effective (possibly impersonated) identity, and `impersonatedBy` is the real actor whenever it differs from `user` — `null` otherwise. The frontend uses a `null` `impersonatedBy` to self-heal a stale local impersonation selection.

## Authorization (roles)

Authenticated users additionally hold **roles** (`users.roles`, a JSON list of `super_admin` / `admin` / `developer` / `requester` / `approver`) that gate the write endpoints. `super_admin` bypasses every route-level role gate; the seeded `root` user holds it. Two ownership-layer checks are a deliberate exception — see the bullet below. See the [Roles and authorization](https://kaitoy.github.io/a2flow/docs/concepts/authorization) chapter of the manual for the full matrix.

**Effective roles.** A role reaches a user either directly (the `users.roles` column) or through a [user group](#user-groups) they belong to, and authorization uses the **union** of the two. That union is resolved per request by `dependencies/auth.py`'s `get_effective_roles` (backed by `repositories/effective_roles.py`, one indexed join) and handed to `models/user.py`'s `has_any_role`. Nothing is denormalized onto `users`, so there is no cache to invalidate and a membership change cannot leave a stale grant behind — the trade the alternative would have made is a *fail-open* one, which is why it was not taken.

`has_any_role` takes a **role collection rather than a `User`** on purpose: each call site has to state whether it means the direct grants or the effective ones, and `mypy --strict` rejects passing the user object by mistake. Checks that only ask about `super_admin` deliberately keep reading `user.roles` — a group can never grant that role, so the two are equivalent there, and reading the column stays correct even if that invariant were ever weakened. Every other check uses the effective set, including the two that inspect a *third-party* user: `infrastructure/approval_tools.py`'s approver eligibility and `services/impersonation.py`'s target eligibility (where ignoring inherited roles would let a plain admin impersonate a group-inherited admin — exactly the escalation that rule exists to block).

Two enforcement points:

- **Route dependency** — `require_roles(...)` (`dependencies/authz.py`) is attached per route (e.g. `dependencies=[Depends(require_roles(Role.developer))]`) on the create/update/delete handlers and on `POST /workflows/{id}/execute`. `GET` routes are not gated. `DELETE /workflow-executions/{id}` uses this same mechanism (`require_roles(Role.admin)`), restricting deletion to admins and super admins regardless of who initiated the execution. `POST /api/v1/auth/impersonate` uses a narrower variant, `require_actor_roles(...)`, checked against the real actor (`RealUserDep`) rather than the possibly-impersonated `CurrentUserDep`: gating it the ordinary way would mean every request while impersonating — including the "stop" call itself — resolves the role check against the (deliberately non-admin) impersonation target, permanently locking an impersonating admin out of ever stopping.
- **Service layer** — ownership rules that a role cannot express: self-service user/avatar edits (`services/user.py`, `services/user_avatar.py`), the `super_admin` grant/revoke guard, the designated-approver check (`services/approval.py`), `WorkflowTaskService.update`'s status-change guard (`services/workflow_task.py`: changing a task's `status` is restricted to the execution's initiator or, when the task has a linked `Approval`, an eligible approver of it — the named user, or a member of its approver group holding `approver`), and the workflow-execution access policy (`services/workflow_execution_access.py`). That policy has two methods: `assert_access` (initiator, a designated approver of the execution, or a super admin — used to authorize driving the execution's agent and creating/updating/deleting its tasks) and `assert_read_access` (the same three plus a plain `admin`, read-only — used to authorize fetching the execution, listing/reading its tasks, and loading its chat history). Deletion is authorized separately, by the route-dependency layer above, not by this policy. The designated-approver and status-change checks intentionally exclude `super_admin` (and `admin`) — no exception, not even for a super admin who isn't the addressee. `WorkflowExecutionService.list` and `ApprovalService.list` apply the same initiator-or-designated-approver-or-super-admin-or-admin rule to `GET /workflow-executions` and `GET /approvals`, so nothing appears in a list that `assert_read_access` would then reject on the single-record read. Because `admin`, unlike `super_admin`, can be granted through a group, `assert_read_access` and both `list` methods take the caller's **effective** roles (`caller_roles: EffectiveRolesDep`) as an explicit parameter rather than reading `caller.roles` directly — see "Effective roles" above.

Both raise `ForbiddenError` → HTTP 403 `FORBIDDEN`.

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

The suite runs on in-memory SQLite by default. Setting `A2FLOW_TEST_PG_URL`
points every fixture at a real PostgreSQL server instead, which is what a
deployment runs on — worth doing for any change to a query, a model, or a
migration, since the dialects differ on native enum types, sort collation,
`jsonb`, and post-error transaction state:

```bash
docker compose -f ../compose.test.yml up -d
cd backend && A2FLOW_TEST_PG_URL=postgresql+asyncpg://a2flow:a2flow@localhost:5433/a2flow_test uv run pytest
```

`tests/_engine.py` owns that switch: `make_test_engine()` is where every fixture
gets its engine, and it hands back an empty database on whichever backend is
configured. A test that genuinely needs a specific dialect calls
`make_sqlite_engine()` / `make_postgres_engine()` and says why. See
[Testing](../README.md#running-the-backend-suite-against-postgresql) in the root
README for the isolation model and the CI wiring.

## API

All REST endpoints are documented interactively by the [Scalar API reference](http://localhost:3000/api-doc) (frontend route `/api-doc`), generated from the live OpenAPI spec — paths, request/response schemas, status codes, and a built-in "Test Request" console stay in sync with the running backend automatically. This section does not repeat those per-endpoint signatures; it covers only what the spec does not capture: the conventions shared by every endpoint, each resource's business rules, and the two surfaces intentionally **excluded** from the spec — the agent's AG-UI streaming endpoint and the agent's function tools.

### Conventions

- **Base path** — every REST endpoint is served under `/api/v1` (e.g. `GET /api/v1/agent-skills`).
- **Identity** — the caller is resolved from the authenticated `a2flow_session` cookie (see [Authentication](#authentication)); calling a protected endpoint with `curl` needs a logged-in cookie jar saved with `curl -c`/`-b`.
- **CSRF** — state-changing requests (`POST` / `PATCH` / `DELETE`) must echo the `a2flow_csrf` cookie in the `X-CSRF-Token` header.
- **List parameters** — collection endpoints accept shared `limit` / `offset` / sort (`s`) / filter (`q`) query parameters with camelCase field names. The four taggable collections additionally accept a repeatable `tag` parameter carrying tag ids; a record must carry **every** id listed to match (see [Tags](#tags)).
- **Envelope** — JSON responses are wrapped in a uniform `{meta, data, error}` shape by middleware (the `POST /agent` SSE stream and `GET /api/v1/health` are excluded).

### Session management

Sessions are created lazily: the backend ADK session is materialized on the first `POST /agent` request that supplies a fresh `threadId`. The client picks the UUID, and that same UUID is reused on subsequent requests to preserve conversation history. **There is no explicit "create session" endpoint.** The list / get / messages / delete endpoints are in the [API reference](http://localhost:3000/api-doc).

---

### Agent skills

Agent skills are reusable skill definitions that can be attached to workflows. Each record stores a unique `name`, a Git `repoUrl`, an optional `repoPath` (default `""`), and an optional `description`. Deleting a skill that is still referenced by one or more workflows returns `409 CONFLICT_REFERENCED`. CRUD endpoints are in the [API reference](http://localhost:3000/api-doc).

Private repositories are supported through the optional `repoAuthPassword` field — a `NAME/KEY` reference to one entry of a registered [secret](#secrets), whose value is used as the HTTP basic-auth password for the clone — plus `repoAuthUsername` (default `x-access-token`, which suits GitHub PATs). Create/update validates that the **name** half exists (`422 FOREIGN_KEY_VIOLATION` otherwise); the key is not checked there, since a `vault` secret's keys would need a live Vault read and the two types should behave alike. (`GET /api/v1/secrets/{id}/keys` does perform that read, but it is a picker's lookup — putting it on the save path would make every write depend on Vault being up.) The whole reference is resolved lazily at clone time: a later rename or delete of the secret, or a key that no longer exists, makes the next clone fail with `502 SECRET_RESOLUTION_FAILED`.

The content at `repoUrl`/`repoPath` (e.g. `SKILL.md`) is loaded directly into the workflow agent's LLM prompt, unsandboxed — only register repositories you trust, since their content is effectively an instruction to the agent, not inert data.

---

### Tags

A tag is a tenant-scoped label — a `name` unique within the tenant plus a `color` naming one of eight fixed palette slots — that secrets, workflows, MCP servers, and agent skills are classified by. One vocabulary serves all four. CRUD endpoints are in the [API reference](http://localhost:3000/api-doc); writes require `admin` **or** `developer`, since secrets are administered by the former and the other three by the latter.

Attachment lives in one join table per resource type (`secret_tags`, `workflow_tags`, `mcp_server_tags`, `agent_skill_tags`), each keyed by the record's id and the tag's **id** — never its name, which is what makes a rename free of any re-sync. Four tables rather than one polymorphic table because a polymorphic owner column cannot carry a real foreign key; with real ones, `ondelete="CASCADE"` on both sides cleans up an attachment when either the record or the tag is deleted. Deleting a tag therefore detaches it everywhere instead of being refused.

Tags are **not** a field of a resource's create/update payload: those table classes inherit their `...Create` schema, so a `list[str]` added there would have to become a column of the resource's own table. Attachment is written through `PUT /api/v1/{resource}/{id}/tags` (body `{"tagIds": [...]}`, replacing the set wholesale, capped at 50) and read back as `tagIds` on each resource's `...Read` projection. The sub-resource is gated by the *record's* write role, not the tag's — so a `developer` may tag an MCP server but not a secret. A tag id belonging to another tenant is reported as `422 FOREIGN_KEY_VIOLATION`, never as "exists elsewhere".

Filtering is a separate axis from `q`: `?tag=<id>` is repeatable and conjunctive, applied as one correlated `EXISTS` per tag before the page window. `q=tagIds:…` and `s=tagIds` are rejected as unknown fields — `apply_filters`/`apply_sort` resolve names against the model, and keeping tags out of that grammar is what lets the `readable=` guard stay strict.

---

### MCP servers

A registry of [MCP](https://modelcontextprotocol.io/) servers whose tools the workflow agent can bind to WorkflowTasks. Each record is discriminated by `transport`:

| `transport` | Fields | Connection |
|---|---|---|
| `streamable_http` (default) | `url`, `headers` | One streamable HTTP session per operation, 30-second timeout. SSE-transport servers are not supported. |
| `stdio` | `command`, `args`, `env` | One child process per operation, 120-second timeout — the larger budget covers a cold `npx -y pkg@version` / `uvx pkg` download. `command` is restricted to `npx`/`uvx`, the only two runtimes the backend image ships. |

Literal `headers` / `env` values are stored in plaintext; to keep a credential out of the record, embed a `${secret:NAME/KEY}` placeholder referencing a registered [secret](#secrets) — placeholders are expanded only when connecting, and a reference that no longer resolves fails the connection attempt (`502 SECRET_RESOLUTION_FAILED` on the REST path; a per-server `error` entry on the agent path, where the expansion is done by the [MCP proxy](#mcp-proxy)).

A stdio server runs its `command` inside the backend container. `args` is handed to the process as a list and never through a shell, and the child inherits only the variables `mcp.client.stdio.get_default_environment()` deems safe (`PATH`, `HOME`, …) merged with the configured `env` — the backend's own secrets are not visible to it. Writes are gated behind the same `developer` role as any other MCP server write.

An `args` entry may also embed `${env:NAME}`, referencing a key of that same server's own `env` — useful for a launcher that expects a value as a CLI flag rather than reading it from the process environment. `NAME` must be a key of `env`; the reference is checked eagerly against the *merged* result on both create (`MCPServerCreate`'s validator) and update (`MCPServerService.update`, `422 INVALID_MCP_SERVER`) — including a PATCH that removes the `env` key an existing `args` entry still names. Expansion itself happens in `resolve_connection` after `env`'s own `${secret:NAME/KEY}` placeholders resolve, so `${env:NAME}` transparently picks up a secret-backed value; `StdioConnection.label` (used in `MCP_UNREACHABLE` error details and logs) is built from the *unexpanded* `args`, so an expanded value never leaks there.

The CRUD endpoints are in the [API reference](http://localhost:3000/api-doc). On create, `name` is always required, plus `url` for `streamable_http` or `command` for `stdio`; mixing the two shapes fails Pydantic validation (`422 VALIDATION_ERROR`) and a duplicate name returns `409 CONFLICT_UNIQUE`. On update, sending `headers` / `args` / `env` replaces the whole collection while omitting it leaves it unchanged, and the *merged* per-transport shape is validated by `MCPServerService.update` (`422 INVALID_MCP_SERVER`) — switching transport clears the other shape's fields automatically. Two more behaviors are worth calling out: `GET /api/v1/mcp-servers/{id}/tools` connects to the server live and returns its advertised tools (`name`, `description`, `inputSchema`), or `502 MCP_UNREACHABLE` if it cannot be reached or launched within its timeout; and a server cannot be deleted while WorkflowTask tool bindings still reference it (`409 CONFLICT_REFERENCED`).

`GET /api/v1/mcp-registry` proxies the official [MCP registry](https://registry.modelcontextprotocol.io/) for server discovery. It accepts `search` (substring matched against server names) and `cursor` (pagination) query params and returns `{ servers, nextCursor }`, where each server is flattened to the fields A2Flow can use. A server is surfaced through its streamable-HTTP remote when it has one, otherwise through its first stdio package published to npm or PyPI — flattened to a best-effort `command`/`args`/`env` (`runtimeHint` or `npx`/`uvx`, then the rendered runtime arguments, the `identifier@version` reference, and the rendered package arguments). OCI/NuGet packages and SSE-only remotes are skipped, since nothing in the image can launch them, as is any package whose `runtimeHint` names a command other than `npx`/`uvx`, since the backend only accepts those two. The registry base URL is configurable via the `MCP_REGISTRY_URL` env var (default `https://registry.modelcontextprotocol.io`); a registry that cannot be reached returns `502 REGISTRY_UNREACHABLE`. Registration itself reuses the ordinary `POST /api/v1/mcp-servers` create flow from a pre-filled admin form.

---

### User groups

Tenant-scoped bundles of users (`user_groups`) that grant their `roles` to every member; membership lives in the `user_group_members` join table. Writes require `admin`; reads are open like every other collection.

`roles` is a JSON list with the same shape as `users.roles`, minus `super_admin`: a field validator rejects it (`422 VALIDATION_ERROR`, and the constraint lands in `openapi.yaml` so the generated frontend Zod schema rejects it client-side too) and the `ck_user_groups_no_super_admin` check constraint backs that up. Members must be usable users of the group's own tenant — a user of another tenant, a soft-deleted one, or the seeded system user is rejected as `422 FOREIGN_KEY_VIOLATION`, reported as a missing reference so membership never confirms an id exists elsewhere. Since a `super_admin` is platform-scoped (`tenant_id IS NULL`), that same check is what keeps `super_admin` un-grantable through inheritance.

`memberIds` is carried on the create/update/read models but is **not** a column, so it can be read yet never filtered or sorted on (`400 INVALID_QUERY`). Supplying it replaces membership wholesale; omitting it on a `PATCH` leaves it untouched. Names are unique per tenant (`409 CONFLICT_UNIQUE`). Deleting a group cascades its membership rows away; the user side of that join is `ON DELETE CASCADE` too, so a grouped user stays hard-deletable rather than being forced down `SqlUserRepository.delete`'s soft-delete fallback.

`PUT /api/v1/users/{user_id}/groups` is the same membership seen from the user's side, so an admin can manage it from either page. It replaces the user's group set wholesale (hence `PUT`), and returns the updated `UserRead` whose `groupRoles` already reflects the change. CRUD endpoints are in the [API reference](http://localhost:3000/api-doc).

---

### Secrets

Named bundles of key/value entries — the shape a Vault KV path has — consumed by MCP server placeholders and agent-skill repository clones. Each secret is either `local` — the submitted `entries` map is stored in the `secrets` table as `{key: Fernet ciphertext}`, encrypted with the key described in [Secret management](#secret-management), with entry keys kept in plaintext so they can be listed without decrypting — or `vault` — only a KV v2 reference (`vaultMount`, `vaultPath`) is stored and every key at that path is read from HashiCorp Vault at resolution time.

References always name one entry, as `NAME/KEY` (`${secret:NAME/KEY}` in a placeholder). The key is required even for a single-entry secret; a key-less reference raises `502 SECRET_RESOLUTION_FAILED` rather than passing through unsubstituted.

`GET /api/v1/secrets/{id}/keys` lists one secret's entry keys for both types alike — from the stored map for a `local` secret, from a live KV v2 read for a `vault` one (`502 SECRET_RESOLUTION_FAILED` when Vault is unconfigured or unreachable). It exists because the read view's `keys` field is necessarily empty for a `vault` secret, and doing that live read for every row of a list response would be far too expensive; the agent-skill auth-password picker calls it for whichever secret is selected. Only key names cross the wire.

The API is **write-only for values**: create/update accept plaintext `entries`, but every response uses a read view exposing only the sorted entry `keys`, so neither a plaintext nor a ciphertext value is ever serialized to clients. On update, omitting `entries` keeps the stored map; supplying it replaces the map wholesale (keys left out are deleted), with an **empty-string value meaning "keep the ciphertext already stored under this key"** — the only way a client can preserve a value it never receives. An empty value for a key that does not exist yet, or a map that would leave the secret with no entries, returns `422 INVALID_SECRET`; so does switching `type` into an invalid merged shape (e.g. a `vault` secret with `entries`), while a valid switch clears the other shape's fields. Names are unique (`409 CONFLICT_UNIQUE`) and entry keys and names both use the slug charset (letters, digits, `.`, `_`, `-`) — the absence of `/` is what keeps `NAME/KEY` unambiguous. Deletion is never blocked by references; dangling ones fail at their next resolution with `502 SECRET_RESOLUTION_FAILED` (the failure reason is logged server-side only). CRUD endpoints are in the [API reference](http://localhost:3000/api-doc).

---

### Workflows

A workflow pairs an agent skill with a **pre-designed task list** (its task templates). Each workflow references exactly one agent skill; a single agent skill may be used by multiple workflows. There is no bare `POST /workflows`: a workflow is born from `POST /api/v1/agent-skills/{skill_id}/workflows` ("Generate workflow", body `{name, prompt}`, developer-gated), which registers the row in `status: "generating"` together with its [design session](#design-sessions), then runs the prompt through an unattended design agent in a background job (`services/workflow_design.py`). Success summarizes the conversation into `generated_description` (one LLM call via `infrastructure/summarizer.py`, falling back to the transcript head), sets `status: "draft"`, and raises a `workflow_draft_ready` notification; any failure lands as `status: "failed"` plus `generationError` and raises a `workflow_generation_failed` notification. Note that `ADKAgent` reports an LLM failure as a `RunErrorEvent` in the event stream rather than raising, so the job inspects the events it drains — a run that errors is failed even if it registered templates first, and its `RunErrorEvent` code (e.g. `EXECUTION_TIMEOUT`) names the failure class in `generationError`. Recorded reasons are fixed summaries; the raw provider/exception text is logged server-side only. `status` and `generationError` are server-managed and cannot be written through `PATCH` (which edits `name`, `description`, and — for a super admin only — `generated_description`).

`POST /api/v1/workflows/{id}/generate-description` (developer-gated) re-runs that summarization on demand, which is the only way `generated_description` is refreshed after generation. It reads the workflow's design conversation out of the ADK session store, summarizes it, saves the result, and returns the updated workflow; a `published` workflow becomes `modified`, since a run whose `description` is empty falls back to the summary. A workflow still `generating`, or one with no design conversation to summarize, returns `409 WORKFLOW_DESCRIPTION_NOT_GENERATABLE`; a failing LLM call returns `502 SUMMARIZATION_FAILED` (the raw reason is logged server-side only).

`POST /api/v1/workflows/{id}/publish` (developer-gated) makes a workflow executable: it requires at least one task template and no generation in flight (`409 WORKFLOW_NOT_RUNNABLE` otherwise) and **freezes the design** into the workflow's `WorkflowPublishedVersion` row (name, description, and every task template with its edges and tool bindings — replacing the previous snapshot), and sets `status: "published"`. Executing a workflow — `POST /api/v1/workflows/{id}/execute`, requester-gated — accepts published, `modified`, and (developer-only) draft workflows (`409 WORKFLOW_NOT_RUNNABLE` otherwise), snapshots its configuration into a new `WorkflowExecution`, and copies its templates into the execution's tasks (see below). The remaining endpoints (list/get/patch/delete, `GET /{id}/task-templates`) are in the [API reference](http://localhost:3000/api-doc); `GET /{id}/messages` and `POST /{id}/agent` serve the workflow's [design session](#design-sessions).

Editing a published workflow does not silently change what runs. A `PATCH /workflows/{id}`, a description regeneration, or any task-template write moves a `published` workflow to **`status: "modified"`** — the first two through `WorkflowRepository.mark_modified` (called from `WorkflowService.update` and `WorkflowDesignService.generate_description`), template writes through its counterpart `mark_design_edited` (called from `WorkflowTaskTemplateService`). A `modified` workflow is still runnable, but `execute` resolves its task templates from the published snapshot instead of the live rows — name, description, and tasks all come from the version captured at publish time. Publishing again promotes the edits (and re-freezes the snapshot); `POST /api/v1/workflows/{id}/discard-changes` (developer-gated) does the opposite, rewriting the task templates from the snapshot — reusing the original template IDs, so the recorded edges stay valid — restoring the recorded name and description, and returning the workflow to `published`. Discarding anything but a `modified` workflow returns `409 WORKFLOW_NOT_MODIFIED`; a snapshot binding an MCP tool whose server has since been deleted fails the restore with `422 FOREIGN_KEY_VIOLATION`.

The design agent's tools trigger the same transition. They go straight to the repository (`infrastructure/task_template_tools.py`) rather than through `WorkflowTaskTemplateService`, so each write tool calls `mark_design_edited` itself — task templates refined by chat have drifted from the published snapshot just as much as ones edited through the REST API. During the initial background generation run the workflow is still `generating`, which the call leaves alone, so nothing special is needed there.

The two methods differ in one respect: **`mark_design_edited` also recovers a `failed` workflow to `draft`**, clearing its `generationError`. `failed` is not terminal — the design chat is where a user repairs a design run that failed, and rebuilding the task templates is what repairs it, so the recorded reason would otherwise keep describing a design that no longer exists (the generation job runs once, at creation, and there is no endpoint to re-run it). `mark_modified` deliberately does not: renaming a workflow or re-summarizing its description repairs nothing.

---

### Workflow task templates

A workflow task template is one step of a workflow's pre-designed task list, owned by the workflow (`workflow_id` FK, `ON DELETE CASCADE`). Templates mirror [workflow tasks](#workflow-tasks) structurally — `title`, optional `description`, DAG edges (`workflow_task_template_dependencies`, cycle-checked exactly like task edges), and MCP tool bindings (`workflow_task_template_tool_bindings`, server side `ON DELETE RESTRICT`) — but carry **no status**: the lifecycle belongs to a run. They are written by the design agent's tools (`infrastructure/task_template_tools.py`) and by the developer-gated manual CRUD endpoints (`POST /workflow-task-templates`, `GET`/`PATCH`/`DELETE /workflow-task-templates/{id}`, listing on `GET /workflows/{id}/task-templates`), all in the [API reference](http://localhost:3000/api-doc). At execute time the templates are copied into the new session as `pending` WorkflowTasks in dependency order, ids remapped, bindings included — so template edits never affect runs already started. Editing a template — through the CRUD endpoints or through the design agent's tools — also moves a `published` parent workflow to `modified`, after which runs use the published snapshot rather than these rows until the workflow is published again (see [Workflows](#workflows)).

---

### Design sessions

A **design session** is the chat in which a workflow's task templates are produced and refined — the design-time counterpart of a workflow session. Like a workflow session it has no record of its own: it is the ADK session named by `Workflow.session_id`, minted by the generation flow and pinned to the skill revision published at that moment (`Workflow.agentSkillCommitSha`), so the workflow's id addresses it. The workflow's `createdBy` keys the ADK session, so everyone entering the chat shares one history rather than forking a private session. The background generation run posts the prompt as its first message, so opening the chat later shows the full conversation. Like a workflow session, a design session is **shared**: every `developer` in the tenant may read and drive it (plus super admins, and the workflow's creator even if their role is later revoked — see `WorkflowService._assert_design_access`). Sharing follows from the role rather than from a per-record participant list, so unlike `WorkflowExecution` it needs no access-policy object. Because several people post into one ADK session, each message is attributed to its real sender the same way a workflow session's is: `POST /workflows/{id}/agent` snapshots the chat's attributable events inside the run lock, records the caller as the sender of any that appear afterwards (on the cancellation path too, shielded, so an abandoned run's messages aren't left ownerless), and `GET /workflows/{id}/messages` returns each message's `senderUserId`. The rows land in `message_meta` under `workflow_id`; the read/diff/merge logic itself lives in `services/session_attribution.py`, shared with `WorkflowExecutionService`. Messages the unattended generation run produced carry no sender, so the UI falls back to `createdBy`. There is no task association here — a design session edits task *templates* rather than working through status-ful tasks — so `workflowTaskId` is always null.

Endpoints: `GET /workflows/{id}/messages` (empty until the generation run starts) and the streaming `POST /workflows/{id}/agent` (excluded from the spec like the other agent endpoints) — the same `/messages` + `/agent` sub-resource pair `workflow-executions` uses for its workflow session. The agent resolved for this chat runs with the interactive **design** instruction and toolset — it edits the workflow's templates and never executes anything. The session goes away with its workflow row, and the skill-store prune keeps every revision a workflow's design session still pins.

---

### Workflow executions

A `WorkflowExecution` is the snapshot record created when a published workflow is executed via `POST /workflows/{id}/execute`, pre-filled with `pending` WorkflowTasks copied from the workflow's templates. Its **workflow session** — the chat the run happens in — has no record of its own and is addressed by the execution's id: streaming at `POST /workflow-executions/{id}/agent`, history at `GET /workflow-executions/{id}/messages`. The execution metadata is fetched via `GET /workflow-executions/{id}`, and the list endpoint (ordered most recent first) is scoped to the caller: a super admin sees every execution in the tenant, everyone else sees only executions they initiated or are a designated approver of. The run endpoint overwrites the AG-UI `context` with the workflow's summarized `description` server-side, so the execution agent receives the design intent as trusted context (and a client can never inject its own).

The list (ordered most-recent-first) and get endpoints are in the [API reference](http://localhost:3000/api-doc).

---

### Workflow tasks

A workflow task is a single actionable item belonging to a `WorkflowExecution`, copied from the workflow's task templates at execute time and driven by the execution agent via [agent tools](#agent-task-tools); they are also exposed through the REST endpoints below. Each task carries a `status` (`pending` | `in_progress` | `completed` | `failed` | `skipped`); tasks are listed in `createdAt` order. Deleting the parent `WorkflowExecution` cascades to its tasks.

Tasks form a **directed acyclic graph (DAG)**: each task may depend on other tasks in the same session through its `dependsOnIds` list (persisted as `(task_id, depends_on_id)` rows in the `workflow_task_dependencies` join table, where `depends_on_id` must precede `task_id`). Read responses include the resolved `dependsOnIds`. Dependency targets must exist and belong to the same session, otherwise the write fails with `422 FOREIGN_KEY_VIOLATION`; edges that would introduce a cycle — including a self-dependency — fail with `409 DEPENDENCY_CYCLE`. Deleting a task cascade-deletes the edges that reference it in either direction.

Tasks may additionally bind **MCP tools** from [registered MCP servers](#mcp-servers) through their `toolBindings` list (`[{"mcpServerId": …, "toolName": …}]`, persisted in the `workflow_task_tool_bindings` join table). Read responses include the resolved `toolBindings`. Every bound `mcpServerId` must reference a registered server, otherwise the write fails with `422 FOREIGN_KEY_VIOLATION`; duplicates are deduplicated. Bindings cascade-delete with their task, while a referenced MCP server cannot be deleted (`409 CONFLICT_REFERENCED`). At execution time the agent may only invoke bound tools via the `call_mcp_tool` proxy (see [Agent task tools](#agent-task-tools)).

#### Agent task tools

Skill-bound agents are built in one of three roles (`AgentKind` in `infrastructure/agent.py`), each with its own instruction and toolset, and the `AgentRegistry` caches one agent per `(skill_id, commit_sha, kind)`:

- **`initial_design`** — the unattended background run of "Generate workflow". No A2UI toolset (no client is connected); tools: `register_task_templates`, `list_task_templates`, `list_mcp_tools`.
- **`design`** — the interactive [design session](#design-sessions) chat. Tools: the full task-template set plus `list_mcp_tools`; never executes, and has no approval or MCP-invocation tools.
- **`execution`** — a workflow execution's session. The tasks come pre-copied from the templates, so there is no bulk registration and no design-approval wait: the instruction says to **begin executing immediately**. Tools: task inspection (`list`/`get`) and status advancement (`update_workflow_task`) — it cannot add, remove, or restructure the run's tasks — plus the approval tools and the MCP proxies.

| Tool | Kind | Purpose |
|---|---|---|
| `register_task_templates` | design | Register a whole set of task templates as a DAG in one call (each entry has a `key`, `title`, optional `depends_on` referencing other keys, optional `tools` binding MCP tools) |
| `create_task_template` / `list_task_templates` / `get_task_template` / `update_task_template` / `delete_task_template` | design | Refine the workflow's task templates (no status field) |
| `list_workflow_tasks` | execution | List the current session's tasks (id, title, status, `dependsOnIds`, `tool_bindings`), in creation order |
| `get_workflow_task` | execution | Fetch one task in the current session |
| `update_workflow_task` | execution | Advance a task's status (`pending` → `in_progress` → `completed`/`failed`/`skipped`); on `failed`, also record `errorKind` / `errorMessage`. Status is the only field a run may change |
| `request_approval` | execution | Create a `pending` [Approval](#approvals) for the current session, linked to the task the approval takes effect from (`workflow_task_id`, required — it covers that task and everything downstream of it up to the next approval, see [MCP tool certificates](#mcp-tool-certificates)), addressed to exactly one of `approver` (a user) or `approver_group_id` (a user group), and raise an `approval_request` notification per eligible recipient; returns the `approval_id` to pass to the client-side `render_approval` tool |
| `get_approval` | execution | Fetch the current state of an approval in the current session (to re-check a decision) |
| `list_users` | execution | List the registered users (id, username, name, email; system and soft-deleted users excluded) so the agent can choose an `approver` id for `request_approval` |
| `list_user_groups` | execution | List the tenant's user groups that have at least one member able to approve (id, name, description, `eligible_approver_count`) so the agent can choose an `approver_group_id` for `request_approval` |
| `list_mcp_tools` | design + execution | Discover the tools advertised by every [registered MCP server](#mcp-servers) (queried live and concurrently; per-server failures are isolated) |
| `call_mcp_tool` | execution | Invoke an MCP tool bound to the task currently `in_progress`; calls to unbound tools are rejected with an error listing the allowed tools |

`request_approval` and `call_mcp_tool` are the two tools a draft run may **mock** — see [Tool mocks](#tool-mocks). A mocked call returns the configured result with `"mocked": true` and performs none of the tool's side effects. It is still authorized first: a mocked `call_mcp_tool` targeting an unbound tool is rejected exactly like a real one.

The task tools resolve the current run by mapping the ADK session id (the AG-UI thread id) back to the owning record — the `WorkflowExecution` primary key for execution tools, the `Workflow` (matched on its design session's `session_id`) for design tools — and reject access to records belonging to other sessions. The two MCP proxies split along the same line: `list_mcp_tools` serves both kinds, so it resolves only the tenant and accepts either record, while `call_mcp_tool` has to check the run's in-progress tasks and therefore still requires a `WorkflowExecution` (a task template may bind tools, but only a run may invoke them). They live in `infrastructure/workflow_task_tools.py`, `infrastructure/task_template_tools.py`, `infrastructure/approval_tools.py`, and `infrastructure/mcp_tools.py` and are attached to the agent in `infrastructure/agent.py` only when a skill is bound. Neither MCP tool reaches a server itself: both hand a request to the [MCP proxy](#mcp-proxy), which resolves the caller, runs its policy chain, expands the server's secrets, and only then opens one connection per call through the shared adapter in `infrastructure/mcp_client.py` — a streamable HTTP session (30-second timeout) or a freshly spawned child process (120-second timeout), depending on the server's transport.

The approver's actual approve/reject decision is written from the frontend via `PATCH /api/v1/approvals/{id}` (not an agent tool), and surfaces to the agent as the result of the client-side `render_approval` tool. See [Approvals](#approvals).

The task CRUD endpoints — create, list-for-an-execution (ordered `created_at` ASC then `id` ASC), get, update, delete — are in the [API reference](http://localhost:3000/api-doc). A few rules the spec does not spell out: `workflowExecutionId` is fixed at creation and a task cannot be re-parented; sending `dependsOnIds` or `toolBindings` replaces that full set while omitting either leaves it unchanged; and the `422 FOREIGN_KEY_VIOLATION` (unknown execution, cross-execution dependency, or unregistered MCP server) / `409 DEPENDENCY_CYCLE` validation applies to both create and update.

#### MCP proxy

`infrastructure/mcp_proxy.py` is the single gateway through which the agent reaches a tenant's [registered MCP servers](#mcp-servers). It owns the four things the two ADK tools each used to own a copy of: **authentication** (which tenant and which run is calling), **authorization** (a chain of policies consulted before every operation), **stubbing** (answering an authorized call from the run's [tool mocks](#tool-mocks)), and **credential injection** (expanding the server's `${secret:NAME/KEY}` placeholders). Only the transport is left to `mcp_client.py`.

It is an internal layer — no endpoint, no container of its own — but everything on its public surface is a plain serializable value object or an MCP wire type, with no `ToolContext`, `AsyncSession`, or ORM row crossing it. Re-exposing it as an MCP/HTTP endpoint therefore means parsing a request body into a `CallToolRequest` and replacing the authenticator's body; that is also when the `McpProxyError` hierarchy earns rows in `routers/exception_handlers.py`.

- **Authentication** is the `McpAuthenticator` protocol. The only implementation, `AgentRunAuthenticator`, trusts the caller's ADK session id without verification — the caller is a run this very process is driving, so the id has no channel to be forged over — and maps it to a tenant (and, for an execution run rather than a design session, to a `WorkflowExecution`) through `repositories/tenant_bootstrap.py`. What it *does* verify is the [tool certificate](#mcp-tool-certificates), when one is presented: the chain back to this deployment's root, the validity window, and the certificate's shape. This is still the seam a transport-level mTLS check lands in; the certificate handling already produces the same verified credential either way.
- **Authorization** is the `McpPolicy` protocol: veto-only (allow by returning, refuse by raising `McpPolicyDeniedError`), consulted in registration order, short-circuiting on the first denial. Policies live in `infrastructure/mcp_policies.py` and are registered in `default_policies()`. There is one `authorize` method rather than one per operation so that a policy cannot accidentally guard only half the surface — skipping an operation is an explicit early return.
- **The first policy** is `InProgressToolBindingPolicy`, which carries the rule described above: a call may only target a tool bound to a task currently `in_progress` in the run. It deliberately does not restrict *listing*, since design is where bindings are decided. It runs **before** the server row is loaded, so a call naming an unregistered and unbound server is reported as unbound rather than as unregistered.
- **The second policy** is `TaskCertificatePolicy`, the [certificate gate](#mcp-tool-certificates): **every** call must present a valid certificate issued for one of the `in_progress` tasks binding the target tool, prove it holds that certificate's key, and the certificate's own signed grant must cover the tool. There is no exemption — a task nobody approved presents the grant its run's initiator took out for it. Registered after the binding policy so the cheaper denial short-circuits first.
- **Stubbing** is the `McpToolStub` protocol, consulted for `call_tool` only, and only *after* the chain has allowed it — so a [mocked](#tool-mocks) run rehearses the same authorization a real one faces. The implementation, `WorkflowExecutionToolStub`, answers from the run's snapshot. It has two methods rather than one: `stubs` reports whether a call is stubbed without side effects (the proxy asks before the chain runs, since the answer decides whether a refusal is audited), and `answer` consumes one of the run's ordered responses. Unlike an audit failure, an exception here is *not* swallowed — falling through to the real tool is the one outcome a stub must never produce.
- **Every call that reaches a server is audited.** The `McpAuditSink` protocol receives each `call_tool` verdict, allowed or refused; `infrastructure/mcp_audit.py` appends it to `mcp_tool_invocations`. Two things are deliberately absent: listings, which have no side effect and would bury the calls that do, and stubbed calls in either direction, which were never going to reach a server. A sink that raises is logged and swallowed: auditing must never turn an allowed call into a refused one.
- **The proxy owns the database session** and closes it before any network or subprocess call — a stdio spawn can hold the caller for two minutes, which must not pin a database connection. A policy's `db` is valid only while its `authorize` runs.

`GET /api/v1/mcp-servers/{id}/tools` — the admin tool catalog — is deliberately **not** proxied yet and still calls `mcp_client.py` directly.

The run's own audit trail is readable at `GET /api/v1/workflow-executions/{id}/tool-invocations`, gated by the same read access as the run's tasks. It lists exactly what the proxy decided on — the raw arguments are never stored, only their digest.

---

### Tool mocks

A **tool mock** stands in for one tool during a **draft** workflow run: the tool is not called, a configured result is returned instead, and none of its side effects happen. This is what makes a pre-publish test run safe to repeat — no request reaches the external MCP server, no `approvals` row is written, and nobody is emailed.

Mocking is **per tool**, not per run. A workflow that searches a system and then writes to it can stub only the write, so the dry run still exercises the real read and the agent still reasons over real data.

- **The definitions live in `mcp_tool_mocks`** (`models/mcp_tool_mock.py`), managed at `/api/v1/mcp-tool-mocks` — writes need `developer`, the same role that registers MCP servers. A mock names its target as `(mcpServerId, toolName)`; `mcpServerId` is `null` for a built-in A2Flow tool, of which `request_approval` is currently the only mockable one.
- **`responses` is ordered by call ordinal.** The first entry answers the run's first call to that tool, the second its second, and so on; past the end the last entry repeats, so a single-entry mock behaves as a constant. That ordering is what lets one mock express a scenario — approve the first request, reject the second. Each entry is `structured` (a JSON object placed in the result's `structuredContent`), `text`, or `error`.
- **A run snapshots the mocks it uses.** `POST /api/v1/workflows/{id}/execute` takes an optional `toolMockIds`, accepted only while the workflow is `draft` (`409 WORKFLOW_NOT_RUNNABLE` otherwise), and copies what each mock currently says onto `workflow_executions.tool_mocks`. Editing or deleting a mock afterwards cannot change how an existing run behaves — and, more to the point, cannot silently turn a stubbed call back into a real one.
- **For MCP tools the stub sits inside the proxy, behind the policy chain.** `WorkflowExecutionToolStub` (`infrastructure/tool_mocks.py`) implements the proxy's `McpToolStub` hook, which `call_tool` consults only *after* the [policy chain](#mcp-proxy) has allowed the call. A stubbed run therefore rehearses the real one: the tool must still be bound to a task the run has in progress, and the call must still present that task's certificate. What the mock skips is the one thing with an effect outside A2Flow — the upstream call. The built-in `request_approval` calls `resolve_mock` directly instead, since it writes to `approvals` rather than reaching a server.
- **A stubbed call leaves no `mcp_tool_invocations` row, allowed or refused.** That table records the calls that reached (or were stopped on their way to) a real MCP server; a row for a call that was always going to be answered from a snapshot would misread in either direction. This is why the stub hook has two methods — the proxy must know whether a call is stubbed *before* deciding whether to audit a refusal, and finding that out must not consume one of the run's ordered responses.
- **A mocked result is marked.** Every stubbed payload carries `"mocked": true`, which is what the execution agent's instruction keys on (trust the result, follow its `note`) and what the chat UI shows as a `Mocked` badge. `request_approval`'s mocked result adds a `note` telling the agent not to call `render_approval` and not to poll `get_approval`, so a test run reaches a decision without a human.
- **Validation still runs.** A mocked `request_approval` still checks that the destination is a real, eligible approver and that the named task belongs to the current run — a mock skips the side effects, not the checks — so a misconfigured workflow fails in a dry run the same way it would for real.

Because a mocked call is invisible to the audit table, the place to inspect one is the run's chat transcript: every tool line there expands to show the call's arguments and its result.

---

### MCP tool certificates

**Every** proxied `call_tool` must present a short-lived X.509 certificate issued for the task making it; `TaskCertificatePolicy` refuses the call otherwise. A task gets one through exactly one of two paths, recorded in the row's `grant_kind`:

| `grant_kind` | Issued when | `granted_by` | `approval_id` |
|---|---|---|---|
| `approval` | the task goes `in_progress` and every approval **governing** it is granted | the approver who decided | the governing approval |
| `initiator` | the task goes `in_progress` and no approval governs it | the run's `initiator_id` | `NULL` |

The second path is what "the applicant approved it themselves" means in the schema: nobody was asked to weigh the task, so the person who executed the workflow authorizes its bound tools, and the audit trail says so in as many words. A governed task still **closes** until its approval is granted — the grants already held by the tasks a new approval covers are revoked (`superseded_by_approval`) when it is requested, and the policy refuses an initiator grant for any governed task regardless, so a run cannot start a task, pocket its certificate, and only then ask for the decision it was supposed to wait for.

Both paths issue at the moment the task starts, not at the moment of the decision. That is what lets one approval cover a chain of tasks: each gets its own validity window, so the chain does not have to finish inside the one opened by the approver's click. `McpToolCertificateService.issue` covers the other end of the same rule — when an approval is granted, any task it governs that is *already* `in_progress` (typically the step that asked and is waiting) is issued its certificate there and then, since nothing else will start it again.

The point is not the transport. The proxy is still in-process, so the presenter (`infrastructure/mcp_credentials.py`) and the verifier (`infrastructure/mcp_proxy.py`) share a process and a database, and the proof-of-possession signature proves nothing an attacker who already owns the backend could not forge. What it buys today is three concrete things, plus the shape the system needs later:

1. **A fail-closed enforcement point.** The approval gate used to consist of the LLM's system instruction and the frontend declining to resume the run. Neither is a server rule. This is.
2. **A frozen grant.** The certificate's `subjectAltName` carries the tools the task had bound *at the moment it was issued* — when the approver decided, or when the task went `in_progress`. A run's tasks and their `tool_bindings` are copied from the workflow's published templates at execute time and the execution agent cannot edit them, but a rule that re-read the bindings at call time would still trust whatever the row said then — a later re-publish or a `discard-changes` restore, say — so it could be widened out from under the approver. The signed grant cannot: it is never re-signed. This closes a real escalation path, and it closes it on both grant kinds. The practical consequence, spelled out in the agent-facing docs of `register_task_templates` / `update_task_template`: **bind a task's tools into the template before the workflow is published**, because a run cannot add them afterwards.
3. **A verifiable audit trail.** Each decided call records the certificate serial together with the exact bytes signed for it, so `mcp_tool_invocations` can be re-verified later against the root's public half alone.
4. **The mTLS seam.** Certificates carry `clientAuth`, so the same material works unchanged as TLS client certificates once the proxy becomes an HTTP endpoint; only the authenticator changes.

**Which tasks an approval covers** is the nearest-approval rule in `infrastructure/approval_scope.py`, a pure module both the gate and the grant read: a task is governed by the first approval found at or above it in the run's `depends_on` graph. An approval therefore covers the task it names **and every task downstream of it, up to the next approval**.

```
approval A                     approval B
    |                              |
    v                              v
[ask] --> [launch] --> [tag] --> [ask] --> [delete]
 {A}        {A}         {A}       {B}        {B}
```

That is why `request_approval`'s `workflow_task_id` is required but no longer has to name the acting task: a design agent naturally emits the request as a step of its own ("Request approval" → "Launch instance"), and naming that step is now the intended shape — the decision reaches the steps that follow it. Three consequences:

- **A merge is fail-closed.** A task reachable from two gated branches is governed by both approvals, and *every* one of them must be `approved` before it may call anything. One approver clearing their own branch does not speak for the other's.
- **The graph is re-read on every call**, not trusted from the certificate. An approval requested *after* a certificate was issued takes its task over immediately, and the outer approval's grant is refused from that moment (`the approval this tool certificate carries no longer governs this task`).
- **A covered task's `tool_bindings` are frozen.** Because a certificate is signed when the task *starts* rather than when the approval was decided, an edit in between would widen what the decision goes on to authorize — so `WorkflowTaskService.update` refuses to change the bindings of a task an approval covers, decided or not.

One row gates one task: a task carrying several `Approval` rows (a rejection followed by a re-request) is gated by the unresolved one, or by the most recent when none is unresolved — the same rule `SqlApprovalRepository.get_for_task` applies, so a rejection cannot wedge a task that has already been re-asked.

| Piece | Where |
|---|---|
| Root CA — generation, loading, leaf signing | `infrastructure/mcp_ca.py`, table `mcp_certificate_authorities` |
| Certificate grammar, digest, verification (all pure) | `infrastructure/mcp_certificate.py` |
| Which approval governs which task (pure) | `infrastructure/approval_scope.py` |
| Issuing and revoking | `services/mcp_tool_certificate.py`, table `mcp_tool_certificates` |
| Presenting (the caller side) | `infrastructure/mcp_credentials.py` |
| Enforcing | `TaskCertificatePolicy` in `infrastructure/mcp_policies.py` |
| Auditing | `infrastructure/mcp_audit.py`, table `mcp_tool_invocations` |

**One root for the whole platform.** A per-tenant CA would add key material without adding a boundary: verification compares the tenant in the certificate's binding URN against the tenant the proxy derived independently from the session id, so a certificate minted for tenant A is refused in tenant B regardless of which key signed it. The root's private key is stored as Fernet ciphertext under the same key as [local secrets](#secrets); losing that key stops new certificates from being issued.

**What a certificate claims** is carried entirely in `subjectAltName` URI entries — A2Flow holds no private enterprise OID arc, and inventing one would be indistinguishable from someone else's. Exactly one binding URN — `urn:a2flow:binding:tenant/T/execution/E/task/K/approval/A` for an approver's grant, `.../initiator/U` for the run initiator's own — plus one grant URN per tool (`urn:a2flow:tool:SERVER/TOOL`). Both are percent-encoded, because `ToolName` places no character restriction on a tool name.

**Revocation is not the only stop.** Verification also re-reads the grantor on every call — which approvals now govern the task and whether all of them are still `approved`, or the run's current `initiator_id` and whether an approval has since claimed the task — so a grant that stopped applying after issuance is refused even if nothing stamped `revoked_at`. There is no scheduler in this codebase, so nothing here depends on a timer.

`GET /api/v1/approvals/{id}/certificates` reports what an approval authorized (approval-backed grants only; `GET /api/v1/mcp-tool-certificates` spans both kinds) — one row per covered task, each with its serial, validity window, revocation state, and the granted tools parsed back out of the signed certificate. The private key and the certificate body are never serialized. The list grows as the run advances and is legitimately empty until the first covered task starts, so it returns `[]` rather than a 404.

---

### Audit read APIs

Three admin-gated, read-only surfaces back the frontend's `/admin/audit` section. All of them use `require_roles(Role.admin)` (so `super_admin` passes through `has_role`'s bypass) on **every** route, reads included — unlike most resource routers, which leave `GET` open to any authenticated caller. Each spans every record in the acting tenant, so the participant-level access that gates the narrower per-record views is not sufficient here.

| Routes | Returns | Repository |
|---|---|---|
| `GET /api/v1/mcp-tool-invocations`, `.../{id}` | `MCPToolInvocation` | `repositories/mcp_tool_invocation.py` |
| `GET /api/v1/mcp-tool-certificates`, `.../{id}` | `McpToolCertificateRead` | `repositories/mcp_tool_certificate.py` |
| `GET /api/v1/impersonation-events`, `.../{id}` | `ImpersonationEventRead` | `repositories/impersonation_event.py` |

None of the three has a Create, Update, or Delete route, which is what keeps the trails append-only. All accept the shared pagination / sort / filter query params and are built on `CurrentTenantScopeDep`, so a platform-scoped `super_admin` may send `X-Tenant-Id: __all__` to read across every tenant.

The narrower views they complement are unchanged: `GET /workflow-executions/{id}/tool-invocations` (one run, open to that run's participants) and `GET /approvals/{id}/certificates` (one approval's covered tasks, open to any authenticated caller — it reaches only approval-backed certificates, never the ones a run's initiator granted itself).

**`mcp_tool_certificates` list.** `SqlMcpToolCertificateRepository.list` passes `readable=McpToolCertificateRead` so `certificate_pem` and `private_key_encrypted` resolve as unknown fields — a client cannot use "which rows match" as a blind oracle on key material it never receives. `McpToolCertificateService.list` parses each row's grants back out of its PEM, the same as the single read, so a page costs a page of X.509 parses and the response can never report a grant that differs from what was signed.

**`impersonation_events` scoping.** This table has no `tenant_id` — it references users, which are platform-scoped — so the audit reads scope rows by an `IN` subquery over `users` on `target_user_id`, filtering the *impersonated* user's tenant. Filtering on the target rather than the actor is what makes a platform-scoped `super_admin`'s session visible to the tenant whose data it touched: the actor carries no `tenant_id` at all. The subquery is used in place of a join so the statement stays a scalar `select`, which is what `apply_filters`/`apply_sort` resolve field names against; the target's tenant is then attached in one further query and surfaced as `ImpersonationEventRead.target_tenant_id`. That field has no column behind it, so it is not filterable or sortable. The three write methods stay unscoped as they always were, so this is not a fourth entry in the audited list of tenant-unscoped repositories.

`ImpersonationEventRead` exists because `ImpersonationEvent` inherits plain `SQLModel` rather than `BaseEntity`: it carries neither the camelCase alias generator nor the `Z`-suffixed datetime serialization the generated frontend Zod schemas require.

**Outgoing email.** `GET /api/v1/outbound-emails` and `.../{id}` moved from `super_admin` to `admin` alongside these three, since the queue is part of the same audit trail. `DELETE` stays at `super_admin`: discarding a dead letter destroys evidence. See [Outgoing email queue](#outgoing-email-queue).

---

### Notifications

Per-user notifications surfaced in the frontend's toolbar bell. Notifications are generated as side effects of workflow activity — the generation job raises a `workflow_draft_ready` when the initial task templates land, `request_approval` raises an `approval_request` addressed to the designated approver — or one per eligible member when the request is addressed to a group, and the final `update_workflow_task` that drives every task to a terminal state raises a one-shot `execution_completed` addressed to the user who started the run. Both endpoints below are scoped to the authenticated user; the list never accepts a `user_id`, and reading or marking another user's notification returns `404 NOT_FOUND`.

Each notification stores a `type` (`workflow_draft_ready` / `workflow_generation_failed` / `approval_request` / `execution_completed`), `title`, optional `body`, the linked `workflowExecutionId` or `workflowId`, and a `read` flag. Rows cascade-delete with their recipient user and their linked `WorkflowExecution` or `Workflow`.

Every one of those producers writes through `services/notification_dispatch.py::NotificationDispatcher` rather than calling `NotificationRepository.create` directly. The dispatcher persists the row and, when [system settings](#system-settings) have SMTP enabled, queues an email for the recipient — **in the same transaction** (see [Outgoing email queue](#outgoing-email-queue)). It skips recipients there is no point mailing — the seeded system user, disabled or soft-deleted accounts, accounts whose address is unverified, and accounts with no address — before anything is queued. Everything on the email side is wrapped in a blanket `except Exception` and logged, so a misconfigured deployment degrades the feature to in-app notifications instead of breaking the workflow operation that raised one.

The dispatcher is the one service in this codebase that holds an `AsyncSession` as well as its repositories. That is deliberate: writing the notification and its email in two commits would leave a window where a crash produces a notification whose email was never queued, which is the exact failure the queue exists to remove. `NotificationRepository.stage` and `OutboundEmailRepository.stage` both add without committing, and the dispatcher's single commit decides that either both rows exist or neither does.

The dispatcher also exposes `exists_for_session` as a pass-through, which is what lets it stand in for the repository inside `services/workflow_execution_completion.py::evaluate_completion`. Callers running outside FastAPI's request scope (the ADK tools in `infrastructure/workflow_task_tools.py` and `infrastructure/approval_tools.py`, and the design job in `services/workflow_design.py`) build one with `build_notification_dispatcher(db, tenant_id=...)`; request-scoped callers inject `NotificationDispatcherDep`. The two `infrastructure/*_tools.py` modules import it lazily, for the same reason they already defer `evaluate_completion`: touching `services` at import time closes a cycle back through `infrastructure.agent`.

---

### System settings

`GET` / `PATCH /api/v1/system-settings` plus `POST /api/v1/system-settings/smtp/test`, all gated behind `super_admin` — reads included, like [tenants](#tenants). The routes deliberately do **not** depend on `CurrentTenantIdDep`: a super admin is platform-scoped, so that dependency would raise `ForbiddenError` unless a tenant happened to be selected, locking out the only callers allowed here.

`SystemSettings` is a singleton table (`BaseEntity` only, no `TenantScoped`) whose primary key is pinned to `SYSTEM_SETTINGS_ID` by `ck_system_settings_singleton`, and whose row is seeded at startup by `infrastructure/bootstrap.py::seed_system_settings`. Seeding it up front rather than lazily is what lets every reader assume it exists.

`smtp_password` is write-only: `SystemSettingsService` encrypts it with the shared `SecretCipher` before it reaches the repository, and responses use `SystemSettingsRead`, which drops it in favor of a `smtpPasswordSet` flag — the same pattern as `SecretRead.keys` and `User.password`. An empty submitted value means "keep the stored ciphertext", so a blank field in the admin form is non-destructive. The cross-field rules (a host and sender address are required once `smtp_enabled` is true; a username needs a password) are checked against the *merged* result in the service and raise `422 INVALID_SYSTEM_SETTINGS`, since a PATCH body alone cannot know the effective configuration.

`infrastructure/email_sender.py` is the adapter. It uses the standard library's blocking `smtplib` on a worker thread (`asyncio.to_thread`) rather than adding an async SMTP dependency, selects `SMTP_SSL` / `SMTP` + `STARTTLS` / plain per `smtp_security`, and wraps every transport failure in `EmailSendError` — whose reason is logged server-side and never returned to a client, mirroring `McpConnectionError`. `SmtpEmailSender.session()` keeps one connection open across a batch of messages (what makes draining the queue cheap) and reconnects once if an idle relay hung up; `SmtpEmailSender.send()` is the one-shot form the test-send endpoint uses. `EmailSendError.permanent`, set from the `smtplib` exception type by `is_permanent_failure`, is what tells the queue worker whether retrying could ever help — note that `SMTPAuthenticationError` counts as *transient* despite its 5xx code, because an admin fixing the password makes the message deliverable again.

`smtp_host` and `app_base_url` use their own constraint aliases rather than `HttpUrl`, whose `assert_public_http_url` SSRF guard would reject exactly the values these fields legitimately hold: a relay on `localhost` or a private subnet, and the app's own address in development. Neither is fetched server-side on a caller's behalf.

---

### Outgoing email queue

Notification email is delivered asynchronously through the `outbound_emails` table, not inline on the request that produced the notification. Three reasons: a relay that is down for a minute used to lose the message for good, a burst of approval requests used to hit the relay all at once, and a 30-second SMTP timeout used to be charged to a workflow operation.

**The message is rendered at enqueue time.** `to_email`, `subject`, and `body` are frozen from what was true when the notification was produced — who the recipient was, whether their address was verified, what `app_base_url` said. The worker therefore knows nothing about tenants, users, or notification kinds; it sends what the row says.

**The repository is split in two, and the split is a tenant-isolation decision.** `repositories/outbound_email.py` is the tenant-scoped write and reporting half. `repositories/outbound_email_queue.py` is deliberately tenant-*unscoped* — the third such audited module, alongside `tenant_bootstrap.py` and `effective_roles.py`. A deployment has one relay (`SystemSettings` is platform-scoped), so it has one sender; scoping the drain per tenant would mean N pollers contending for it, which is precisely what the rate limiter exists to prevent.

**One sender at a time.** `services/email_queue_worker.py::EmailQueueWorker.run_forever` holds the `email-queue` advisory lock (`infrastructure/locks.py::email_queue_key`) and waits when another replica has it. Two things fall out of that, and both are why the design is shaped this way: the rate limiter can be an in-memory `TokenBucket` (`infrastructure/rate_limit.py`) rather than something shared through the database, and the claim can be a plain read-then-update instead of `SELECT ... FOR UPDATE SKIP LOCKED` — so one code path works on both PostgreSQL and SQLite. `lease_expires_at` covers what the lock cannot: a sender that dies mid-batch leaves rows in `sending`, and the next pass reclaims them without spending an attempt.

**One pass** is `run_once`, which is also what the tests drive: reclaim expired leases, resolve the SMTP configuration afresh (an admin may have just fixed it), claim a batch, send it one message at a time through the rate limiter over a single connection, then purge delivered messages past their retention. `run_forever` is that in a loop with a sleep.

**Failure handling.** A failure the relay reports as permanent goes straight to `status=failed`. A transient one is rescheduled by `backoff_delay(attempts, rng=...)` — `min(15s · 2ⁿ, 1h)` times a ±20% jitter, so an outage's backlog does not all land on the relay in the same second when it recovers. The jitter is multiplicative and never reaches zero on purpose: an immediate retry the instant a relay comes back is how you knock it over again. `rng` is a parameter so the delay is reproducible under test. Once `EMAIL_MAX_ATTEMPTS` is spent the message becomes a dead letter with its last error on the row; `sent` rows are purged after `EMAIL_SENT_RETENTION_DAYS`, `failed` rows never.

**Where it runs.** `EMAIL_WORKER_IN_PROCESS` (default true) starts the worker from `main.py`'s lifespan, so a bare `uvicorn main:app` delivers mail. `compose.yml` instead runs `backend/worker.py` as its own service and turns the in-process one off. The worker process deliberately does **not** run migrations — `main.py` owns that, and compose gates the worker on the backend's healthcheck.

`services/metrics.py` exports the backlog as `a2flow_email_queue_depth{tenant,status}` and `a2flow_email_queue_oldest_pending_age_seconds{tenant}`; the depth gauge reports every status including zeros, so a queue that drains does not make its series disappear from the exposition.

---

### Approvals

A human-in-the-loop decision the workflow agent asks for mid-execution. The agent creates a `pending` Approval with the `request_approval` [agent tool](#agent-task-tools) (which also raises the `approval_request` notifications), then calls the client-side `render_approval` tool to show Approve / Reject controls. The frontend writes the decision back via `PATCH /api/v1/approvals/{approval_id}`, which records the requesting user in the audit fields and in `decidedBy`.

A request carries **exactly one destination**, enforced by `request_approval` and mirrored in the database by `ck_approvals_single_destination` (which only forbids naming *both*, so pre-existing destination-less rows stay readable):

- `approver` — one user id. Only that user may resolve it.
- `approverGroupId` — one [user group](#user-groups) id. Any member whose **effective** roles include `approver` may resolve it, and the first decision settles the request. `request_approval` refuses a group with no such member, since nobody could ever resolve it.

`services/approver_groups.py::ApproverGroupResolver` is the single place that answers "which groups does this caller count as an approver for", and it applies the role gate. Every consumer — `ApprovalService.resolve` / `.list`, `WorkflowExecutionAccessPolicy`, and `WorkflowTaskService`'s status guard — goes through it, so a plain member of an approver group gains nothing from the membership. It reads **effective** roles, like every other non-`super_admin` role check.

Each approval stores `workflowExecutionId` (FK, `ON DELETE CASCADE`), an optional `workflowTaskId` (FK, `ON DELETE SET NULL`) marking where the approval takes effect rather than the single task it authorizes — see [MCP tool certificates](#mcp-tool-certificates) — one of `approver` / `approverGroupId` (both FKs, `ON DELETE RESTRICT` — a destination that could vanish would strand the request), a `title`, optional `description`, a `status` (`pending` / `approved` / `rejected` / `returned`), an optional `response` comment, and the server-managed `decidedAt` / `decidedBy`. The latter two are declared on the table class only, so no client payload can write them; both are stamped once, on the write that first leaves `pending`. `decidedBy` is what identifies the actual decider for a group destination. Because `approverGroupId` restricts, deleting a group an approval is still addressed to returns `409 CONFLICT_REFERENCED`.

A decision is final: a `PATCH` that would *change* an already-recorded `status` returns `409 APPROVAL_ALREADY_RESOLVED` rather than overwriting it, which is what keeps two racing members of one approver group from clobbering each other. Editing only the `response` comment afterwards is still allowed and moves neither stamp.

`GET /api/v1/approvals` (list, with the shared pagination / sort / filter query params) is scoped like the workflow-executions list: a super admin sees every approval in the tenant, everyone else sees only approvals addressed to them — directly, or through a group they may approve for — or belonging to a WorkflowExecution they initiated. `GET` / `PATCH /api/v1/approvals/{id}` remain unscoped by id. All three are in the [API reference](http://localhost:3000/api-doc). Fetching a missing approval returns `404 NOT_FOUND`.

Both endpoints — list (ordered `created_at` DESC, `?unreadOnly=true` for the bell's unread badge) and mark-read — are in the [API reference](http://localhost:3000/api-doc). Reading or marking another user's notification returns `404 NOT_FOUND`.

---

### Agent streaming — `POST /api/v1/agent`

This endpoint and its per-execution variant `POST /api/v1/workflow-executions/{id}/agent` are marked `include_in_schema=False`, so they are **not** in the [API reference](http://localhost:3000/api-doc) and are documented here instead.

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
