---
title: MCP Servers
sidebar_position: 7
---

# MCP Servers

Navigate to [http://localhost:3000/admin/mcp-servers](http://localhost:3000/admin/mcp-servers) to manage the registry of [MCP](https://modelcontextprotocol.io/) servers whose tools the workflow agent can bind to WorkflowTasks (see [MCP tools for tasks](./workflows.md#mcp-tools-for-tasks)).

| Operation | Path |
|-----------|------|
| List all servers | `GET /admin/mcp-servers` |
| Register a new server | `GET /admin/mcp-servers/new` |
| A server's detail page — edit / delete | `GET /admin/mcp-servers/{id}` |

Each record stores a unique name, any [tags](./tags.md) it is classified by, and a **transport**, which decides the rest of the form:

| Transport | Fields | Notes |
|---|---|---|
| **Streamable HTTP** (default) | `url`, `headers` | A remote server. SSE-only servers are not supported. Headers are sent with every request — typically `Authorization: Bearer …`. |
| **stdio** | `command`, `args`, `env` | A server launched as a child process of the backend, e.g. `npx` + `["-y", "@modelcontextprotocol/server-everything"]`. Both `npx` (Node.js 22) and `uvx` are available in the backend image. |

⚠️ Literal header and environment values are stored **in plaintext** in `a2flow.db` and returned by the API; instead of embedding a credential directly, reference one entry of a registered [Secret](./secrets.md) with the `${secret:name/key}` placeholder syntax (e.g. `Authorization: Bearer ${secret:github/token}`, or `AWS_ACCESS_KEY_ID: ${secret:aws-credentials/AWS_ACCESS_KEY_ID}`) — placeholders are expanded only at connect time and the credential never appears in the stored record or any API response.

⚠️ Registering a stdio server means **running the chosen command inside the backend container**, as the container's unprivileged `app` user. It is gated behind the same `developer` role as any other MCP server write. `args` is passed to the process as a list and never through a shell, and the child inherits only the small safe set of environment variables the MCP SDK allows (`PATH`, `HOME`, …) plus the `env` you configure — the backend's own API keys and `DB_URL` are not visible to it.

An `args` entry may also reference this same server's own `env` by name as `${env:NAME}`, expanded after `env`'s own `${secret:…}` placeholders — so `--token ${env:API_KEY}` can reuse a secret-backed `env` value as a CLI flag, for a launcher that expects the value as an argument rather than reading it from the process environment. `NAME` must be a key of `env`, checked when saving (both on create and on a PATCH that changes either field); a stale reference left behind by removing the `env` key it names is rejected the same way.

Switching an existing server's transport clears the other transport's fields; a request that mixes the two shapes (a URL on a stdio server, a command on a remote one) is rejected with HTTP 422 (`INVALID_MCP_SERVER`).

The list page's **Browse registry** button opens a search dialog backed by the official [MCP registry](https://registry.modelcontextprotocol.io/) (`GET /api/v1/mcp-registry`). It searches servers by name and lists those A2Flow can register: servers with a streamable-HTTP remote, and servers published as an npm or PyPI package it can launch over stdio (OCI/NuGet packages are skipped). Picking a result opens the create form pre-filled with the connection details and the required header/environment keys, so you only fill in secret values before saving. The package-to-command mapping is best-effort — review it before saving. The registry base URL is configurable via the `MCP_REGISTRY_URL` env var; an unreachable registry yields HTTP 502 (`REGISTRY_UNREACHABLE`).

`GET /api/v1/mcp-servers/{id}/tools` queries the live server and returns the tools it advertises (name, description, input schema); the admin task forms call it for the one server the operator has picked, never for the whole registry at once. A server that cannot be reached or launched yields HTTP 502 (`MCP_UNREACHABLE`). A server cannot be deleted while WorkflowTask tool bindings still reference it (HTTP 409 `CONFLICT_REFERENCED`).
