---
title: Deployment
sidebar_position: 2
---

# Deployment

A deployment is the backend, the frontend, and one relational database; [Run with Docker Compose](../getting-started/docker-compose.md) is the shortest path to all three. What follows is what changes once the stack sits behind a proxy and holds data worth keeping.

## Reverse proxy and load balancer

**Sticky sessions / session affinity are not required.** See "Horizontal
scaling" above — the PostgreSQL advisory lock, not routing affinity, is what
keeps one ADK session pinned to one driver at a time, and only for the
duration of a single SSE stream.

The two SSE routes (`POST /api/v1/agent`, `POST /api/v1/workflow-executions/{id}/agent`)
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

## State that has to persist

Three things outlive a container and have to sit on durable storage — or be restorable from a backup — for a deployment to come back up intact:

- **The database** — every REST record and the ADK session store both live in the database named by `DB_URL`. See [Database](../architecture/database.md).
- **The agent skill store** — `SKILLS_DIR` is durable state, not a cache: a workflow execution pins the skill revision it started with. See [Agent skill store](./configuration.md#agent-skill-store).
- **The secret encryption key** — losing it makes every stored local secret undecryptable. See [Secret management](./configuration.md#secret-management).
