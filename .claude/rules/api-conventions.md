---
paths:
  - "backend/**/*.py"
---

# List Query Parameters

Every collection endpoint (`GET /agent-skills`, `GET /workflows`, `GET /workflows/{id}/task-templates`, `GET /workflow-sessions`, `GET /workflow-sessions/{id}/workflow-tasks`) accepts the same set of optional query parameters. Field names are written in **camelCase** (matching the JSON response), and an unknown field, operator, or uncoercible value returns HTTP 400 with the `INVALID_QUERY` error code.

| Param | Purpose | Syntax | Example |
|---|---|---|---|
| `limit` | Page size (1–1000, default 20) | integer | `?limit=50` |
| `offset` | Records to skip (default 0) | integer | `?offset=100` |
| `s` | Sort | Comma-separated fields; prefix `-` for descending | `?s=-createdAt,name` |
| `q` | Filter (repeatable) | `field:op:value` | `?q=name:like:foo&q=status:eq:pending` |

Filter operators (`op`):

| Operator | Meaning |
|---|---|
| `eq` / `ne` | Equal / not equal |
| `lt` / `lte` / `gt` / `gte` | Less / less-or-equal / greater / greater-or-equal |
| `like` | Case-insensitive substring match (string fields) |
| `in` | Matches any of a comma-separated list, e.g. `status:in:pending,completed` |

When `s` is omitted, each endpoint falls back to its default ordering (`createdAt` descending; workflow tasks and task templates order by `position` then `createdAt` ascending).
