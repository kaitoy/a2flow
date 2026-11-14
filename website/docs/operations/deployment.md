---
title: Deployment
sidebar_position: 1
---

# Deployment

A deployment is the frontend, the backend, and one relational database; [Run with Docker Compose](../getting-started/docker-compose.md) is the shortest path to all three. What follows is what changes once the stack sits behind a proxy and holds data worth keeping.

![Architecture diagram showing the browser reaching a reverse proxy that routes API requests (/api/*) straight to the backend API and page requests to the frontend, and the backend API — which also runs the email worker — reaching durable state (database, skill store, secret key), external services (LLM provider, MCP servers), and an SMTP relay.](./img/deployment-topology.svg#gh-light-mode-only)
![Architecture diagram showing the browser reaching a reverse proxy that routes API requests (/api/*) straight to the backend API and page requests to the frontend, and the backend API — which also runs the email worker — reaching durable state (database, skill store, secret key), external services (LLM provider, MCP servers), and an SMTP relay.](./img/deployment-topology-dark.svg#gh-dark-mode-only)

The browser talks to one origin, and the reverse proxy routes it by path: `/api/*` and `/openapi.json` to the backend, everything else to the frontend. Both sit on the same domain, so the auth cookies stay first-party — and the long-lived streams of every open chat go straight to the backend instead of through the frontend. The `ingress` service in `compose.yml` (Envoy) is a working example of this routing.

Without that route the frontend forwards `/api/*` to the backend itself, which is how a run without containers works. It behaves the same, but every open chat then also holds a connection on the frontend, so the frontend has to be scaled with the number of concurrent chats as well. Every variable named here is described under [Configuration reference](./configuration.md).

## Reverse proxy and load balancer

**Sticky sessions / session affinity are not required.** See [Horizontal scaling](./scaling.md) — a PostgreSQL advisory lock, not routing affinity, is what keeps one conversation pinned to one driver at a time, and only for the duration of a single SSE stream.

The SSE agent routes (`POST /api/v1/workflow-executions/{id}/agent` and `POST /api/v1/workflows/{id}/agent`) need the following at the reverse proxy that routes them to the backend:

| Setting | Required value | Why |
|---|---|---|
| Response buffering | Off for those two paths | The app sends `X-Accel-Buffering: no`, which nginx honors per-response even with buffering on globally. Every other proxy needs it disabled in its own config |
| Compression | Never applied to `text/event-stream` | The app never compresses a response, so any compression the client sees comes from this layer |
| Read / idle timeout | Well above the longest agent run you expect | An agent run has no server-side time limit, so a proxy read timeout is the only thing that can end a stream — and a low one silently truncates a legitimate long response. Size it against your longest run, not a typical request |

A rolling deploy forcibly ends any SSE stream still open 30 seconds after the container receives SIGTERM (`--timeout-graceful-shutdown 30`, set in the backend `Dockerfile`'s `CMD`). That is safe: the advisory lock releases with the connection and the client resumes with a fresh request, exactly as an abandoned stream already behaves.

## Behind HTTPS

Three settings default to values that only suit local HTTP development. Change all three before a deployment faces real users:

| Variable | Set it to | Left at the default |
|---|---|---|
| `SESSION_COOKIE_SECURE` | `true` | Session and CSRF cookies go out without `Secure`, so a browser will also send them over plain HTTP |
| `CORS_ORIGINS` | The browser-facing origin, e.g. `https://a2flow.example.com` | Only `http://localhost:3000` is allowed to call the API |
| `APP_BASE_URL` | The same origin | Notification email is sent without the deep links back into the app — see [Notification email](./configuration.md#notification-email) |

The Docker Compose stack has a working example: [Serve over HTTPS](../getting-started/docker-compose.md#https) puts a TLS-terminating proxy in front of the `ingress` service and sets all three.

## Process layout

Alongside the API, a deployment runs the [MCP proxy](../architecture/mcp-gateway-and-proxy.md#the-sandbox): the process that actually starts or connects to the MCP servers a tenant has registered. Keeping it separate is the point — it is where third-party code runs, so it holds no database access, no secret encryption key and no LLM API key. `compose.yml` runs it as the `mcp-proxy` container, on a network it shares only with the API, so it cannot reach the database at all; a deployment that assembles its own containers should keep the proxy off the database's network the same way, and configure it under [MCP proxy](./configuration.md#mcp-sandbox).

Two things to get right:

- **The API has to start first.** It issues the material both ends identify each other with, so the proxy will not accept anything until that has been written. Gate the proxy on the API's health check, as `compose.yml` does.
- **They need a shared directory.** `MCP_PROXY_TLS_DIR` has to be the same storage on both sides — writable by the API, read-only for the proxy. Nothing durable is kept there: it is rewritten whenever it is missing or close to expiring.
- **The proxy has to be able to build sandboxes.** It starts every server in a [sandbox of its own](../architecture/mcp-gateway-and-proxy.md#per-launch-sandbox), and checks at startup that it can — if it cannot, it stops with an error rather than running servers unsandboxed. Inside a container this takes three security options, which `compose.yml` gives the `mcp-proxy` service and only that service: `seccomp=unconfined`, `apparmor=unconfined`, and `systempaths=unconfined`. On an Ubuntu 24.04 or later host, unprivileged user namespaces must also be allowed: `sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`.

Skipping the proxy is possible — leave `MCP_PROXY_URL` unset and the API reaches MCP servers itself, which is what a local development run does. It means a registered server runs beside the deployment's credentials, so it is not a choice to make for an environment where anyone can register one.

The backend also ships as two entry points against the same database. Which one you run decides where notification email is delivered from:

| Layout | How | Use it when |
|---|---|---|
| API only | The default — `EMAIL_WORKER_IN_PROCESS` is `true`, so `uvicorn main:app` also drains the email queue | A single-process deployment, or one small enough that a stalled relay on the request path is acceptable |
| API + worker | Run `python -m worker` alongside the API and set `EMAIL_WORKER_IN_PROCESS=false` on it | Anything where a hung relay must not cost anything that serves requests. This is what `compose.yml` does |

Two things about the worker process:

- **It does not migrate or seed.** The API's startup owns both, so the worker has to start after the API is up — `compose.yml` gates it on the API's health check.
- **More than one replica buys failover, not throughput.** They contend on the `email-queue` advisory lock and all but one sit idle by design, which is what keeps the send rate exact.

## Health checks

Point your orchestrator or load balancer at `GET /api/v1/health`. See [Health checks](./health.md).

## State that has to persist

Three things outlive a container and have to sit on durable storage for a deployment to come back up intact:

| What | Where it lives | Losing it means |
|---|---|---|
| **The database** | The database named by `DB_URL` | Everything — every record lives there. See [Database](../architecture/database.md) |
| **The agent skill store** | `SKILLS_DIR` | Executions cannot load the skill revision they are pinned to (HTTP 409 `SKILL_NOT_READY`). It is durable state, not a cache — see [Agent skill store](./configuration.md#agent-skill-store) |
| **The secret encryption key** | `SECRET_ENCRYPTION_KEY`, or the file at `SECRET_KEY_FILE` | Every stored local secret becomes undecryptable, and the certificate authority can no longer issue or verify the certificates every MCP tool call needs. See [Secret management](./configuration.md#secret-management) |

How to take and restore each of them is in [Backup and restore](./backup.md).
