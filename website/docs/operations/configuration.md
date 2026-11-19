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
| `TIMEZONE` | `UTC` | IANA name of the deployment's local time zone. It decides where a calendar day starts for the [operations metrics](./metrics.md) — the "today" counts and the daily buckets of the lead-time trend — and is the zone the workflow agent reads a task's time requirement in when the requirement names no time zone. An unrecognized name falls back to `UTC` rather than failing startup, so a typo skews local times instead of stopping the app |
| `APP_BASE_URL` | — | The address users open this deployment at in a browser — scheme, host and an optional port, with no path, e.g. `https://a2flow.example.com`. Notification email links to the recipient's tenant address under it, [single sign-on](#single-sign-on) builds its **Redirect URI** from it, and it sets the defaults of `CORS_ORIGINS` and `SESSION_COOKIE_SECURE`. Any other shape stops the backend at startup. Without it, messages go out with no link back and single sign-on is unavailable. Each tenant can also be opened at its own address under it — the tenant name, a dot, then the host, such as `acme.a2flow.example.com` — once DNS and a TLS certificate cover every name under the host (`*.a2flow.example.com`); see [At your tenant's address](../guides/single-sign-on.md#tenant-address). Not when the host is an IP address |

## Frontend settings

| Variable | Default | What it does |
|---|---|---|
| `BACKEND_BASE_URL` | `http://localhost:8000` | Where the frontend forwards `/api/*` when no reverse proxy routes it to the backend first (a run without containers), and where the API documentation page checks the signed-in session. Read once at process start. In the Docker Compose stack this is the backend's address on the internal network, not a public one |
| `APP_PORT` | `3000` | Docker Compose only: the host port the app is published on — the port of the `ingress` service, which serves both the screens and the API. Unless `.env` sets `APP_BASE_URL`, the stack passes `http://localhost:` followed by this port as the base URL |
| `OPENBAO_PORT` | `8200` | Docker Compose only, with `--profile openbao`: the host port OpenBao's UI is published on — see [Try Vault secrets with OpenBao](../getting-started/docker-compose.md#openbao). A2Flow reaches it on the internal network regardless |

## Application database

| Variable | Default | What it does |
|---|---|---|
| `DB_URL` | `sqlite:///a2flow.db` | Database URL. SQLite (relative to the working directory) and PostgreSQL are supported |
| `DB_POOL_SIZE` | `5` | PostgreSQL only. Connections each of a backend process's two connection pools keeps open. At least `1`. See [Connection pooling](./scaling.md#connection-pooling) for how this adds up across replicas |
| `DB_MAX_OVERFLOW` | `10` | PostgreSQL only. Extra connections each pool may open on top of `DB_POOL_SIZE` under load, closed again once the load passes. At least `0` |

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

If either is unset (or empty), a random password is generated instead and logged **once**, at `WARNING` level, when that user is created — it cannot be recovered once the log line has scrolled past. Set both explicitly before the first run for anything beyond local experimentation, or capture the generated passwords from the startup logs immediately and change them afterwards from the **Password** card on the **Profile** page. Unlike a password an admin sets for someone, these are not forced to change at the first sign-in. The usernames are fixed to `root` and `admin`.

## Sign-up {#sign-up}

| Variable | Default | What it does |
|---|---|---|
| `SIGNUP_ENABLED` | `false` | Lets visitors create a tenant of their own from the sign-in page and become its Admin — see [Signing up](../getting-started/sign-up.md). The link appears only at the main address, not at a tenant's own address |

Sign-up mails each visitor a confirmation link, so it also needs `APP_BASE_URL` (the link is built from it) and email delivery switched on with **Send notifications by email** in [System Settings](../guides/system-settings.md) or the [notification email](#notification-email) variables. Until all three are in place, the sign-in page offers no sign-up.

Anyone who can reach the deployment and receive mail can then create tenants. One address gets at most one confirmation email a minute, which keeps the form from being used to flood someone's inbox, but the only other limit is the **Maximum Number of Tenants** in [System Settings](../guides/system-settings.md#tenant-limit). It is empty by default, meaning no limit, so set one before turning sign-up on anywhere an unbounded number of tenants would be a problem.

## Session lifetime

| Variable | Default | What it does |
|---|---|---|
| `SESSION_IDLE_TIMEOUT_SECONDS` | `28800` (8 hours) | Sliding idle timeout. Authenticated requests refresh the session's last-active time, at most once every 5 minutes (or half this value, if shorter), so a session may end up to that much early; a session left idle longer than this is rejected and deleted |
| `SESSION_COOKIE_SECURE` | `true` when `APP_BASE_URL` starts with `https://`, else `false` | Marks the session and CSRF cookies `Secure` (HTTPS only). Set it only to override that default |

The cookies themselves are session cookies (no `Max-Age`/`Expires`), so they are also cleared when the browser closes. The browser reaches the backend on the same origin as the frontend — `/api/*` is routed to it by path, either at the reverse proxy or by the frontend itself — so the cookies are first-party and `SameSite=Lax` applies cleanly.

## CORS

| Variable | Default | What it does |
|---|---|---|
| `CORS_ORIGINS` | `APP_BASE_URL`, or `http://localhost:3000` without it | Comma-separated list of origins allowed to call the backend API |

Add each origin the frontend is served from:

```env
CORS_ORIGINS=https://app.example.com,http://localhost:3000
```

`*` is rejected at startup — `allow_credentials=True` is always enabled, and pairing it with a wildcard origin is invalid per the CORS spec.

## Single sign-on {#single-sign-on}

| Variable | Default | What it does |
|---|---|---|
| `OIDC_ALLOWED_PRIVATE_HOSTS` | empty | Comma-separated host names, such as `keycloak.internal,localhost`, that a tenant's [single sign-on](../guides/single-sign-on.md) issuer URL may have even though they resolve to a private address — for an on-premises identity provider. Every other issuer must resolve to a public address |

Single sign-on also depends on the deployment's base URL, `APP_BASE_URL` (see [Server settings](#server-settings)). Without it, single sign-on is unavailable and **Admin Settings** shows a warning instead of the **Redirect URI**. Two requirements:

- **The base URL is the origin only** — scheme, host and an optional port, such as `https://a2flow.example.com`, with no path. The backend refuses to start with any other value.
- **The backend should see the public origin.** Behind a reverse proxy, have the proxy keep the original `Host` header when it forwards a request and set `X-Forwarded-Proto` to the original scheme, and let the backend trust the proxy by listing the proxy's address in `FORWARDED_ALLOW_IPS` (by default only `127.0.0.1` is trusted). Otherwise every SSO sign-in takes one extra redirect.

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

## Knowledge bases {#knowledge-bases}

| Variable | Default | What it does |
|---|---|---|
| `KNOWLEDGE_SOURCE_MAX_BYTES` | `20971520` (20 MiB) | Largest document that may be uploaded to a [knowledge base](../guides/knowledge-bases.md), and largest web page fetched for one. A larger upload is refused as soon as it passes this |
| `KNOWLEDGE_INGEST_CHUNK_CHARS` | `40000` | Characters of a source the LLM reads at a time. A longer source is read in parts, one after another. Lower it for a model with a small context window |
| `KNOWLEDGE_FETCH_TIMEOUT_SECONDS` | `30` | How long fetching a web page source may take per request |

Sources and pages are stored in the database, like session files, so they need no volume of their own. Reading a source calls the LLM configured for the agents ([LLM configuration](../getting-started/llm-configuration.md)), several times for a large document.

## Session files {#session-files}

| Variable | Default | What it does |
|---|---|---|
| `SESSION_FILE_MAX_BYTES` | `20971520` (20 MiB) | Largest single file that may be attached to a [workflow session](../guides/workflow-executions.md#files-in-the-session). An upload is refused as soon as it passes this, so a larger body is never held whole |
| `SESSION_FILES_MAX_TOTAL_BYTES` | `209715200` (200 MiB) | Combined size of everything one session holds. Files are removed only when their run is deleted, so this is what bounds a long-running session |

Session files are stored in the database rather than on disk, so they need no directory of their own, no shared volume across replicas, and no backup step beyond the database's own ([Backup and restore](./backup.md)). Raising these limits raises how much of the database one run can occupy, and how much memory a single upload or download takes — the bytes are read whole.

## Secret management {#secret-management}

| Variable | Default | What it does |
|---|---|---|
| `SECRET_ENCRYPTION_KEY` | — | The master key. It encrypts each tenant's own data key, which in turn encrypts that tenant's `local` [secrets](../guides/secrets.md) and stored credentials (see [Secret storage](../architecture/secrets.md#local-secrets)) |
| `SECRET_KEY_FILE` | `.secret_key` | Path to the on-disk key file, next to the SQLite database file. Under `docker compose` it is `/var/lib/a2flow/secret-key/.secret_key`, backed by the `secret-key` named volume that the backend and the email worker share |
| `SECRET_ENCRYPTION_KEY_FALLBACKS` | — | Previous master keys, comma-separated. Used only to decrypt, while a [rotation](#rotating-the-master-key) is under way |

The encryption key is resolved at first use, in order:

1. `SECRET_ENCRYPTION_KEY`, which must be a valid Fernet key.
2. The key file at `SECRET_KEY_FILE`.
3. Failing both, a key is generated, saved to that file, and a WARNING is logged.

**Back the key up.** Losing it makes every tenant's data key undecryptable, and with them every stored local secret and credential. The same key protects the [approval CA](../architecture/approvals.md)'s signing key.

There is no environment variable for HashiCorp Vault: a tenant's own Vault is set by its admin under [Admin Settings](../guides/users-and-groups.md#tenant-vault), and the global Vault's address by a Super Admin under [System Settings](../guides/system-settings.md#global-vault), with each tenant's [credential for it](../guides/users-and-groups.md#global-vault-credential) on the tenant's page. A tenant's own Vault address goes through the same SSRF checks as other user-supplied URLs, so it must be public. The global Vault address is exempt, since only a Super Admin can set it and a Vault typically lives on a private address.

### Rotating the master key

1. Generate a new key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
2. Make it the master key — set it as `SECRET_ENCRYPTION_KEY`, or write it into the key file — and put the old key in `SECRET_ENCRYPTION_KEY_FALLBACKS`. Set both on the backend and on the email worker.
3. Restart. At startup the backend re-encrypts everything under the new key and logs a WARNING with the number of values it re-encrypted. Values still under the old key keep decrypting until then, so nothing stops working along the way.
4. Once every replica runs with the new key, remove `SECRET_ENCRYPTION_KEY_FALLBACKS` and restart again.

Back up the new key, and keep the old one for as long as you keep database backups taken before the rotation: those still need it. A rotation takes seconds however many secrets there are, because the tenants' data keys stay the same — only their encryption changes.

## MCP tools and approvals {#mcp-tools-and-approvals}

Every MCP tool call must present a short-lived X.509 certificate issued for the task making it — granted when the task's [approval](../guides/approvals.md#human-approval) is, or when a task nobody was asked to approve starts. The signing root is generated on first use and stored encrypted with the master key above, so nothing here needs configuring for the feature to work.

| Variable | Default | What it bounds |
|---|---|---|
| `MCP_TOOL_CERT_TTL_SECONDS` | `3600` | How long a task's certificate stays valid — the window in which it may call its tools |
| `MCP_TOOL_CERT_SIGNATURE_WINDOW_SECONDS` | `60` | Clock-skew tolerance for the proof-of-possession signature accompanying each proxied call |
| `MCP_CA_COMMON_NAME` / `MCP_CA_VALIDITY_DAYS` | `A2Flow MCP Approval CA` / `3650` | Subject and lifetime of the generated root. Read only when the root is first generated; changing them later has no effect on an existing root |
| `MCP_REGISTRY_URL` | `https://registry.modelcontextprotocol.io` | Base URL of the registry the [Browse registry](../guides/mcp-servers.md#registering-from-the-mcp-registry) dialog searches |
| `MCP_ELICITATION_TIMEOUT_SECONDS` | `900` | How long a tool call waits for the run's initiator to answer an MCP server's [confirmation](../guides/workflow-executions.md#mcp-server-confirmations) before the question expires. The initiator has just resumed the task, so this bounds only a question left behind |
| `AGENT_TURN_TIMEOUT_SECONDS` | `3600` | The longest one agent turn of a run may last, waiting included. Keep it well above `MCP_ELICITATION_TIMEOUT_SECONDS`, since a turn whose tool call is waiting on a person is still running |

## MCP proxy {#mcp-sandbox}

A registered MCP server is not A2Flow's code, so it runs [somewhere separate](../architecture/mcp-gateway-and-proxy.md#the-sandbox) from the agent and its secrets. The Docker Compose deployment sets all of this up; a deployment that assembles the containers itself sets it here.

Left unset — which is what a plain local run does — the agent reaches MCP servers itself, in its own process. That is convenient for development and is not what you want in an environment where anyone can register a server.

| Variable | Default | What it does |
|---|---|---|
| `MCP_PROXY_URL` | unset | Where the proxy is. Setting it is what moves MCP servers out of the agent's process |
| `MCP_PROXY_SERVER_NAME` / `MCP_PROXY_PORT` | `mcp-proxy` / `8443` | The name the proxy is reached by, and the port it listens on. The name is part of its certificate, so both ends have to agree |
| `MCP_PROXY_TLS_DIR` | a directory beside the application | Where the agent publishes what the proxy needs to identify itself. The proxy reads the same directory, read-only |
| `MCP_BACKEND_TLS_DIR` | a directory beside the application | Where the agent keeps its *own* key. Deliberately not the directory above — nothing running in the proxy should be able to read it |
| `MCP_TRANSPORT_CERT_VALIDITY_DAYS` | `365` | Lifetime of that material. Reissued automatically once fewer than 30 days remain, so it needs no attention |
| `MCP_SANDBOX_DIR` | unset | Where each tenant's home directory for [sandboxed server launches](../architecture/mcp-gateway-and-proxy.md#per-launch-sandbox) lives — the packages a tenant's servers download are kept here, one directory per tenant. Set, every locally started server runs in its own sandbox; the proxy refuses to start without it. Unset on a plain local run, where servers start unsandboxed |

## LLM {#llm}

The system's default LLM — the model every tenant's agents run on, and the key it is reached with — is edited on the [System Settings](../guides/system-settings.md#llm) screen. These two variables set it from the environment instead, like the mail settings below. Setting up a provider is covered in [LLM configuration](../getting-started/llm-configuration.md).

| Variable | Default | What it does |
|---|---|---|
| `SYSTEM_DEFAULT_LLM_MODEL` | — | A Gemini model name, or `litellm:<provider>/<model>` for any other provider. When neither this nor the screen sets one, the built-in default `gemini-3.8-flash` is used |
| `SYSTEM_DEFAULT_LLM_API_KEY` | — | The API key for that provider. Stored encrypted, never logged, and never returned by any API response |

Like the mail settings below, these are **re-applied on every startup**:

- **Applied when the backend starts**, into System Settings. A variable that is set overwrites what an admin saved on the screen, so changing it and restarting is how the key is rotated. A variable left unset or blank leaves its field alone, for the screen to manage.
- **A malformed value is logged as a warning and skipped**, for example a model name over 200 characters. The mail settings are still applied, and the app still starts.
- **Left unset, the provider's own variable is read as before** — `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` or `AWS_BEARER_TOKEN_BEDROCK` — for as long as no key is stored. That is also how credentials that are not a single key, such as Vertex AI's, are supplied.

## Notification email {#notification-email}

These are the same values the admin UI edits under [System Settings](../guides/system-settings.md), settable from the environment so a deployment can ship its mail configuration rather than leaving it as a manual step.

| Variable | Default | What it does |
|---|---|---|
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
| `EMAIL_SEND_RATE_PER_SECOND` | `5.0` | Messages per second handed to the relay; the worker pauses `1 / rate` before each send. Lower it to sit under a stricter relay limit |
| `EMAIL_QUEUE_BATCH_SIZE` / `EMAIL_QUEUE_POLL_INTERVAL_SECONDS` | `20` / `5.0` | How many messages one drain pass claims, and how long the worker sleeps when the queue is empty. The poll interval is the floor on delivery latency for a notification produced while the worker is asleep |
| `EMAIL_MAX_ATTEMPTS` | `9` | Delivery attempts before a message becomes a dead letter. The backoff runs 15s, 30s, 1m, 2m and so on, capped at an hour, so the default rides out roughly an hour of relay downtime. A failure the relay reports as permanent is written off on the first attempt regardless |
| `EMAIL_SENT_RETENTION_DAYS` | `30` | How long delivered messages are kept before the worker purges them. They are a record of what went out, not queue state. Dead letters are never purged |

## Agent

| Variable | Default | What it does |
|---|---|---|
| `EXECUTION_MAX_PARALLEL_SESSIONS` | `4` | Most sessions one workflow run works in at once — its main session plus the branch sessions forked when its task graph branches. At the limit, a ready task waits for its session instead of forking another. `1` turns forking off. At least `1` |
| `ROLE_DESCRIPTION` | A generic assistant description | Role text the agent's system prompt is built around, alongside the workflow rules and the interface schema |
| `SESSION_RUNNER_CONCURRENCY` | `4` | How many turns one replica runs at once on a run's own behalf — kickoffs, and resumptions after an approval is decided. Each is a live conversation with the model, so this bounds a replica's model calls for runs nobody is watching. At least `1` |
