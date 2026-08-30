---
title: Database
sidebar_position: 7
---

# Database

All persistent data lives in one relational database selected by `DB_URL` in `backend/.env`:

| Backend | `DB_URL` | Notes |
|---|---|---|
| SQLite (default) | `sqlite:///a2flow.db` | Zero-config local file |
| PostgreSQL | `postgresql://user:password@host:5432/a2flow` | Used by the Docker Compose stack |

The async driver suffix (`aiosqlite` / `asyncpg`) is added automatically. Schema changes are tracked as versioned [Alembic](https://alembic.sqlalchemy.org/) migrations and applied automatically on startup — redeploying the app (a container restart) is what runs any pending migrations, so no separate migration step is needed.

The database is also what coordinates a multi-replica backend: an agent run holds a PostgreSQL advisory lock for the length of its SSE stream, so one conversation is never driven by two replicas at once. See [Horizontal scaling](../operations/scaling.md) for what that protects and the constraint it places on connection pooling.

## What it holds

| Table | Holds |
|---|---|
| `users` | Application users and the roles granted to them — see [Users and groups](../guides/users-and-groups.md) |
| `auth_sessions` | Server-side login sessions |
| `impersonation_events` | Audit trail of [impersonation](../concepts/impersonation.md) sessions |
| `agent_skills` | [Agent Skill](../guides/agent-skills.md) definitions and the repository each is cloned from |
| `mcp_servers` | Registered [MCP servers](../guides/mcp-servers.md) and how to reach them |
| `secrets` | Named [credential bundles](../guides/secrets.md), either encrypted locally or referenced in Vault |
| `workflows` | [Workflow](../guides/workflows.md) definitions and their lifecycle status |
| `workflow_task_templates` | The pre-designed task list of a workflow |
| `workflow_published_versions` | The design frozen at publish time, which a `modified` workflow runs against |
| `workflow_executions` | One row per [run](../guides/workflow-executions.md), with the workflow and skill metadata snapshotted at execute time |
| `workflow_tasks` | The individual tasks of a run, copied from the templates |
| `workflow_task_tool_bindings` | The MCP tools bound to a task |
| `message_meta` | Per-message facts for the two shared chats: who sent a message, and which task was in progress |

Deleting a workflow cascades to its templates but leaves its past runs intact — a run is a record of what happened, not part of the design it came from.
