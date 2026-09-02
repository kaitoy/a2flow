---
paths:
  - "backend/**/*.py"
---

# List Query Parameters

Every collection endpoint (`GET /agent-skills`, `GET /workflows`, `GET /workflows/{id}/task-templates`, `GET /workflow-executions`, `GET /workflow-executions/{id}/workflow-tasks`, `GET /notifications`, `GET /outbound-emails`, `GET /mcp-tool-invocations`, `GET /approval-certificates`, `GET /impersonation-events`) accepts the same set of optional query parameters. Field names are written in **camelCase** (matching the JSON response), and an unknown field, operator, or uncoercible value returns HTTP 400 with the `INVALID_QUERY` error code.

| Param | Purpose | Syntax | Example |
|---|---|---|---|
| `limit` | Page size (1–1000, default 20) | integer | `?limit=50` |
| `offset` | Records to skip (default 0) | integer | `?offset=100` |
| `s` | Sort | Comma-separated fields; prefix `-` for descending | `?s=-createdAt,name` |
| `q` | Filter (repeatable) | `field:op:value` | `?q=name:like:foo&q=status:eq:pending` |
| `tag` | Tag filter (repeatable) | tag id | `?tag=<id>&tag=<id>` |

Filter operators (`op`):

| Operator | Meaning |
|---|---|
| `eq` / `ne` | Equal / not equal |
| `lt` / `lte` / `gt` / `gte` | Less / less-or-equal / greater / greater-or-equal |
| `like` | Case-insensitive substring match (string fields) |
| `in` | Matches any of a comma-separated list, e.g. `status:in:pending,completed` |

Sorting an **enum-typed** field (`status`, `type`, `transport`, `color`, …) orders by the value's **declaration position**, not by its spelling: `pending` before `in_progress` before `completed`, since that is the order that means something to whoever asked for the page. `repositories/query.py::_sort_key` expands the enum into a `CASE` to do it, which also keeps the two dialects agreeing — PostgreSQL stores these as native enum types and already orders them this way, while SQLite keeps them as text and would sort alphabetically. Declare every new enum in the order it should sort.

The ordered filter operators (`lt` / `lte` / `gt` / `gte`) use that same order, so `q=status:gte:completed` selects the tail of the lifecycle rather than the alphabetical tail — `repositories/query.py::_ordered_operands` rewrites both sides of the comparison to declaration positions. `eq` / `ne` / `in` compare the stored value directly, since equality does not depend on the ordering and comparing in place lets an index serve the query. `like` casts the column to text first (`_text_operand`): an enum is a plain string to the client filtering it, but PostgreSQL's native enum types have no `ILIKE` operator of their own.

When `s` is omitted, each endpoint falls back to its default ordering (`createdAt` descending; workflow tasks and task templates order by `createdAt` then `id` ascending; tags order by `name` ascending; impersonation events order by `startedAt` descending, since that table has no `createdAt` column).

`tag` is accepted only by the four taggable collections (`GET /secrets`, `/workflows`, `/mcp-servers`, `/agent-skills`) and is **conjunctive**: a record must carry every tag listed, so repeating the parameter narrows the result rather than widening it. It is a parameter of its own rather than a `q` term because tags are not a column of any record — `apply_filters`/`apply_sort` resolve field names against the model, so `q=tagIds:eq:…` and `s=tagIds` are rejected as unknown fields, which is the intended behavior.
