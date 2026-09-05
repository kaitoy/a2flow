---
title: Configuration reference
sidebar_position: 2
---

# Configuration reference

Every setting below is an environment variable. The backend reads them from `backend/.env` ([backend/.env.example](https://github.com/kaitoy/a2flow/blob/master/backend/.env.example) is the annotated template); the two frontend variables are read from the frontend's own process environment. The model and API-key settings have a page of their own under [LLM configuration](../getting-started/llm-configuration.md).

## Server settings

| Variable | Default | What it does |
|---|---|---|
| `HOST` | `0.0.0.0` | Address the backend binds to |
| `PORT` | `8000` | Port the backend binds to |
| `RELOAD` | `false` | uvicorn autoreload for local development. Only read when the backend is started as `python -m backend.main`; the Docker image's own start command is unaffected either way |

## Frontend settings

| Variable | Default | What it does |
|---|---|---|
| `BACKEND_BASE_URL` | `http://localhost:8000` | Where the frontend's server-side proxy forwards `/api/*`. Read once at process start. In the Docker Compose stack this is the backend's address on the internal network, not a public one |
| `FRONTEND_PORT` | `3000` | Docker Compose only: the host port the frontend is published on. The container keeps listening on 3000 internally, and the backend's `CORS_ORIGINS` follows this automatically |

## Application database

| Variable | Default | What it does |
|---|---|---|
| `DB_URL` | `sqlite:///a2flow.db` | Database URL. SQLite (relative to the working directory) and PostgreSQL are supported |

The async driver suffix (`sqlite+aiosqlite` / `postgresql+asyncpg`) is added automatically, so the plain scheme is enough:

```env
DB_URL=postgresql://user:password@localhost:5432/a2flow
```

Schema changes are tracked as versioned [Alembic](https://alembic.sqlalchemy.org/) migrations and applied automatically on startup, so redeploying the app is what brings the schema up to date. Running more than one backend replica requires PostgreSQL — see [Horizontal scaling](./scaling.md). What each table holds is in [Database](../architecture/database.md).

## Seeded users {#seeded-users}

On startup the backend seeds a hidden **system user**, plus two real accounts, each created only on the very first startup that finds its target record missing:

- An initial **`root`** user holding the **`super_admin`** role (see [Authorization](../concepts/authorization.md)), platform-scoped (`tenantId: null`). Skipped once *any* real (non-system) user already exists, so it runs only on the very first startup.
- A **Default** tenant (`slug: default`) and, inside it, an initial **`admin`** user holding the **`admin`** role. The tenant (by `slug`) and the user (by `username` scoped to that tenant) are checked independently, so either can be recreated without duplicating the other.

The hidden **system user** owns the bootstrap records (it cannot log in and is excluded from the user list).

| Variable | Default | What it does |
|---|---|---|
| `ROOT_PASSWORD` | generated | Password for the seeded `root` user |
| `ADMIN_PASSWORD` | generated | Password for the seeded `admin` user in the Default tenant |

If either is unset (or empty), a random password is generated instead and logged **once**, at `WARNING` level, when that user is created — it cannot be recovered once the log line has scrolled past. Set both explicitly before the first run for anything beyond local experimentation, or capture the generated passwords from the startup logs immediately and change them afterwards. The usernames are fixed to `root` and `admin`.

## Session lifetime

| Variable | Default | What it does |
|---|---|---|
| `SESSION_IDLE_TIMEOUT_SECONDS` | `28800` (8 hours) | Sliding idle timeout. Each authenticated request refreshes the session's last-active time; a session left idle longer than this is rejected and deleted |
| `SESSION_COOKIE_SECURE` | `false` | Marks the session and CSRF cookies `Secure` (HTTPS only). Set it to `true` for any deployment behind HTTPS |

The cookies themselves are session cookies (no `Max-Age`/`Expires`), so they are also cleared when the browser closes. The frontend reaches the backend through a same-origin rewrite (`/api/*`), so the cookies are first-party and `SameSite=Lax` applies cleanly.

## CORS

| Variable | Default | What it does |
|---|---|---|
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated list of origins allowed to call the backend API |

Add each origin the frontend is served from:

```env
CORS_ORIGINS=https://app.example.com,http://localhost:3000
```

`*` is rejected at startup — `allow_credentials=True` is always enabled, and pairing it with a wildcard origin is invalid per the CORS spec.

## Agent skill store {#agent-skill-store}

| Variable | Default | What it does |
|---|---|---|
| `SKILLS_DIR` | `backend/.skills` | Root of the store Agent Skill repositories are shallow-cloned into. Under `docker compose` it is `/var/lib/a2flow/skills`, backed by the `skills` named volume |
| `SKILLS_PRUNE_GRACE_SECONDS` | `3600` | How long a revision directory survives regardless of whether anything references it. A pull prunes revisions no execution is pinned to, and the grace window covers the gap between a run reading the current revision and inserting the row that names it |
| `SKILLS_CLONE_TIMEOUT_SECONDS` | `120` | Bounds how long a clone's individual HTTP requests may take. Without it a hanging remote stalls the clone indefinitely, leaving the skill `pending` |

The store holds one immutable directory per revision, and a revision is never modified once published, so a pull never disturbs an agent loading an existing one:

```
$SKILLS_DIR/<agent_skill_id>/<commit_sha>/
```

This is **durable state, not a cache**: a workflow execution pins the revision it started with, so wiping the directory leaves existing executions unable to load their skill (HTTP 409 `SKILL_NOT_READY`) until an admin pulls the skill again — and a pull fetches the repository's current head, not the pinned revision. Back it up ([Backup and restore](./backup.md)), and give every backend replica the same directory ([Horizontal scaling](./scaling.md)).

## Secret management {#secret-management}

| Variable | Default | What it does |
|---|---|---|
| `SECRET_ENCRYPTION_KEY` | — | Fernet key used to encrypt `local` [secrets](../guides/secrets.md) before storage |
| `SECRET_KEY_FILE` | `.secret_key` | Path to the on-disk key file, next to the SQLite database file |
| `VAULT_ADDR` | — | Address of the single HashiCorp Vault (KV v2 only) that `vault`-type secrets are read live from. Vault is disabled when unset |
| `VAULT_ROLE_ID` / `VAULT_SECRET_ID` | — | AppRole credentials, which take precedence over the static token |
| `VAULT_APPROLE_MOUNT` | `approle` | AppRole login mount path |
| `VAULT_TOKEN` | — | Static token, used when no AppRole credentials are set |

The encryption key is resolved at first use, in order:

1. `SECRET_ENCRYPTION_KEY`, which must be a valid Fernet key.
2. The key file at `SECRET_KEY_FILE`.
3. Failing both, a key is generated, saved to that file, and a WARNING is logged.

**Back the key up.** Losing it makes every stored local secret undecryptable, and the same key protects the [approval CA](../architecture/approvals.md)'s signing key.

`VAULT_ADDR` is deliberately exempt from the SSRF URL checks applied to user-supplied URLs: it is operator-set deployment configuration and typically points at a private address.

## MCP tools and approvals {#mcp-tools-and-approvals}

Every MCP tool call must present a short-lived X.509 certificate issued for the task making it — granted when the task's [approval](../guides/approvals.md#human-approval) is, or when a task nobody was asked to approve starts. The signing root is generated on first use and stored encrypted with the same key as local secrets, so nothing here needs configuring for the feature to work.

| Variable | Default | What it bounds |
|---|---|---|
| `MCP_TOOL_CERT_TTL_SECONDS` | `3600` | How long a task's certificate stays valid — the window in which it may call its tools |
| `MCP_TOOL_CERT_SIGNATURE_WINDOW_SECONDS` | `60` | Clock-skew tolerance for the proof-of-possession signature accompanying each proxied call |
| `MCP_CA_COMMON_NAME` / `MCP_CA_VALIDITY_DAYS` | `A2Flow MCP Approval CA` / `3650` | Subject and lifetime of the generated root. Read only when the root is first generated; changing them later has no effect on an existing root |
| `MCP_REGISTRY_URL` | `https://registry.modelcontextprotocol.io` | Base URL of the registry the [Browse registry](../guides/mcp-servers.md#registering-from-the-mcp-registry) dialog searches |

## MCP sandbox {#mcp-sandbox}

A registered MCP server is not A2Flow's code, so it runs [somewhere separate](../architecture/mcp-proxy.md#the-sandbox) from the agent and its secrets. The Docker Compose deployment sets all of this up; a deployment that assembles the containers itself sets it here.

Left unset — which is what a plain local run does — the agent reaches MCP servers itself, in its own process. That is convenient for development and is not what you want in an environment where anyone can register a server.

| Variable | Default | What it does |
|---|---|---|
| `MCP_PROXY_URL` | unset | Where the sandbox is. Setting it is what moves MCP servers out of the agent's process |
| `MCP_PROXY_SERVER_NAME` / `MCP_PROXY_PORT` | `mcp-proxy` / `8443` | The name the sandbox is reached by, and the port it listens on. The name is part of its certificate, so both ends have to agree |
| `MCP_PROXY_TLS_DIR` | a directory beside the application | Where the agent publishes what the sandbox needs to identify itself. The sandbox reads the same directory, read-only |
| `MCP_BACKEND_TLS_DIR` | a directory beside the application | Where the agent keeps its *own* key. Deliberately not the directory above — nothing running in the sandbox should be able to read it |
| `MCP_TRANSPORT_CERT_VALIDITY_DAYS` | `365` | Lifetime of that material. Reissued automatically once fewer than 30 days remain, so it needs no attention |

## Notification email {#notification-email}

These are the same values the admin UI edits under [System Settings](../guides/system-settings.md), settable from the environment so a deployment can ship its mail configuration rather than leaving it as a manual step.

| Variable | Default | What it does |
|---|---|---|
| `APP_BASE_URL` | — | Base URL at which users reach this deployment in a browser, e.g. `https://a2flow.example.com`. Used to build the deep links in outgoing notification email; without it, messages go out with no link back |
| `SMTP_ENABLED` | `false` | Master switch for email delivery. Must be explicitly `true`; it is never inferred from the other variables being set |
| `SMTP_HOST` / `SMTP_PORT` | — / `587` | The relay to hand messages to. A bare internal hostname is fine here — this is handed to the SMTP client, not fetched |
| `SMTP_SECURITY` | `starttls` | `none`, `starttls`, or `ssl` |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | — | SMTP AUTH credentials. The password is only ever stored as ciphertext, never logged, and never returned by any API response |
| `SMTP_FROM_EMAIL` / `SMTP_FROM_NAME` | — | Sender address, required once delivery is on, and the optional display name beside it |

Unlike everything else on this page, these are not read fresh on each use — they are written onto the single settings record. That gives them their own rules:

- **Re-applied on every startup**, not just the first, so rotating a relay password is a redeploy.
- **Only the variables you actually set are written**, so leaving one unset preserves whatever is stored — including anything an admin configured by hand in the UI.
- **A malformed value is logged as a warning and skipped entirely.** A bad port, an invalid address, or `SMTP_ENABLED=true` with no host leaves the stored configuration untouched; the app still starts.

Because the enable flag is separate, a relay's host and credentials can be staged in one deploy and delivery switched on in a later one.

## Outgoing email queue {#outgoing-email-queue}

These are the knobs for the queue that drains into the relay — see [The delivery queue](../guides/notifications.md#the-delivery-queue) for how it behaves. Nothing here needs setting for a normal deployment.

| Variable | Default | What it does |
|---|---|---|
| `EMAIL_WORKER_IN_PROCESS` | `true` | Whether the API process also runs the drain worker, so `uvicorn main:app` on its own delivers mail. Set it false when running a dedicated worker process — see [Process layout](./deployment.md#process-layout). Leaving both on is safe, just pointless: an advisory lock elects exactly one sender across the deployment |
| `EMAIL_SEND_RATE_PER_SECOND` / `EMAIL_SEND_BURST` | `5.0` / `10` | Sustained messages per second handed to the relay, and how many may go out back-to-back after an idle period before that rate applies. Lower them to sit under a stricter relay limit |
| `EMAIL_QUEUE_BATCH_SIZE` / `EMAIL_QUEUE_POLL_INTERVAL_SECONDS` | `20` / `5.0` | How many messages one drain pass claims, and how long the worker sleeps when the queue is empty. The poll interval is the floor on delivery latency for a notification produced while the worker is asleep |
| `EMAIL_MAX_ATTEMPTS` | `9` | Delivery attempts before a message becomes a dead letter. The backoff runs 15s, 30s, 1m, 2m and so on, capped at an hour, so the default rides out roughly an hour of relay downtime. A failure the relay reports as permanent is written off on the first attempt regardless |
| `EMAIL_SENT_RETENTION_DAYS` | `30` | How long delivered messages are kept before the worker purges them. They are a record of what went out, not queue state. Dead letters are never purged |

## Operations metrics

| Variable | Default | What it does |
|---|---|---|
| `METRICS_TIMEZONE` | `UTC` | IANA timezone name deciding where a calendar day starts for the [operations metrics](./metrics.md) — the "today" counts and the daily buckets of the lead-time trend |

An unrecognized name falls back to `UTC` rather than failing startup, so a typo skews a dashboard's day boundary instead of stopping the app.

## Agent

| Variable | Default | What it does |
|---|---|---|
| `ROLE_DESCRIPTION` | A generic assistant description | Role text the agent's system prompt is built around, alongside the workflow rules and the interface schema |
