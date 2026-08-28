---
title: Database
sidebar_position: 2
---

# Database

All persistent data — REST API records and ADK session storage — lives in one relational database selected by `DB_URL` in `backend/.env`:

| Backend | `DB_URL` | Notes |
|---|---|---|
| SQLite (default) | `sqlite:///a2flow.db` | Zero-config local file |
| PostgreSQL | `postgresql://user:password@host:5432/a2flow` | Used by the Docker Compose stack |

The async driver suffix (`aiosqlite` / `asyncpg`) is added automatically. Schema changes are tracked as versioned [Alembic](https://alembic.sqlalchemy.org/) migrations (`backend/alembic/versions/`) and applied automatically on startup — redeploying the app (a container restart) is what runs any pending migrations, so no separate migration step is needed.

The database is also what coordinates a multi-replica backend: an agent run holds a PostgreSQL advisory lock on its ADK session for the length of its SSE stream, so one conversation is never driven by two replicas at once. See [Horizontal scaling](https://github.com/kaitoy/a2flow/blob/master/backend/README.md#horizontal-scaling) for what that protects and the constraint it places on connection pooling.
