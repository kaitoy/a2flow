---
title: MCP Servers
sidebar_position: 7
---

# MCP Servers

An [MCP](https://modelcontextprotocol.io/) server provides tools the agent can call. This is the registry of them: register a server here, and its tools become available to bind to a workflow's task templates — see [MCP tools for tasks](./workflows.md#mcp-tools-for-tasks).

Open **MCP Servers** in the admin sidebar to manage the registry. Each record has a unique **Name**, an optional **Description**, its [tags](./tags.md), and a **Transport** that decides the rest of the form.

## Transports

| Transport | Fields | What it is |
|---|---|---|
| **Streamable HTTP** (default) | **URL**, **HTTP Headers** | A remote server. Headers are sent with every request — typically `Authorization: Bearer …`. SSE-only servers are not supported. |
| **stdio** | **Command**, **Arguments**, **Environment Variables** | A server launched as a child process of the backend, e.g. `npx` with `["-y", "@modelcontextprotocol/server-everything"]`. Both `npx` and `uvx` are available. |

Switching an existing server's transport clears the other transport's fields, and a record that mixes the two shapes — a URL on a stdio server, a command on a remote one — is refused.

⚠️ **Registering a stdio server means running the chosen command inside the backend container**, as the container's unprivileged user. It is gated behind the same `developer` role as any other MCP server write. Arguments are passed to the process as a list and never through a shell, and the child inherits only a small safe set of environment variables plus the ones you configure — the backend's own API keys and database URL are not visible to it.

## Keeping credentials out of the record

⚠️ Literal header and environment values are stored **in plaintext** and shown back on the detail page. Rather than typing a credential in directly, reference one entry of a registered [secret](./secrets.md):

| Placeholder | Where it works | Example |
|---|---|---|
| `${secret:name/key}` | Any header value or environment variable value | `Authorization: Bearer ${secret:github/token}`<br/>`AWS_ACCESS_KEY_ID: ${secret:aws-credentials/AWS_ACCESS_KEY_ID}` |
| `${gcp-token:name/key}` | Same as `${secret:…}`, for an entry holding a Google Cloud credential JSON | `Authorization: Bearer ${gcp-token:gcp-credentials/GOOGLE_CREDENTIALS_JSON}` |
| `${env:NAME}` | An **Arguments** entry, naming one of this server's own environment variables | `--token ${env:API_KEY}` |

Placeholders are expanded only at connect time, so the credential never appears in the stored record.

`${env:NAME}` is expanded after that environment variable's own `${secret:…}`, which lets a secret-backed value be reused as a command-line flag — for a launcher that expects it as an argument rather than reading it from the process environment. `NAME` must be a key of **Environment Variables**; a reference to a key that is not there, including one left behind by removing that key, is refused when saving.

### Google Cloud MCP servers

Google's managed MCP servers — GKE's, for one — do not accept API keys. Every request must carry an OAuth 2.0 access token for a Google Cloud identity, and a token only lives an hour, so it cannot be pasted into a secret either. `${gcp-token:name/key}` solves this: rather than the entry's value, it expands to a **fresh access token minted from it**, refreshed automatically as it expires. The entry holds the credential JSON, in one of two shapes:

| Credential | How to get it | Token scope |
|---|---|---|
| A **service account key** | Create a service account, grant it **MCP Tool User** plus whatever its tools need, and download a JSON key | `cloud-platform` |
| An **OAuth client ID and secret** | Create an OAuth client (Desktop app), download its JSON, then run `gcloud auth application-default login --client-id-file=<that JSON> --scopes=https://www.googleapis.com/auth/cloud-platform` once on your own machine and sign in. Paste the contents of the resulting `application_default_credentials.json` | Whatever you consented to |

Either way, paste the whole JSON as one entry of a [secret](./secrets.md) and reference it from the server's `Authorization` header as in the example above. Every tool call runs as that one identity, whoever started the workflow. A malformed credential, or one Google no longer accepts, fails the connection the same way a dangling `${secret:…}` reference does.

## Registering from the MCP registry

The list page's **Browse registry** button opens a search dialog backed by the official [MCP registry](https://registry.modelcontextprotocol.io/).

1. Search by name. The results list only the servers A2Flow can register: those with a streamable-HTTP endpoint, and those published as an npm or PyPI package it can launch over stdio.
2. Pick one. The create form opens pre-filled with the connection details and the header or environment keys the server requires.
3. Fill in the secret values and save.

The mapping from a package to a launch command is best-effort, so review it before saving. The registry A2Flow searches can be pointed elsewhere in the [configuration reference](../operations/configuration.md#mcp-tools-and-approvals).

## Checking a server's tools

The task template forms query a server for the tools it advertises — name, description and input schema — but only for the one server you picked, never for the whole registry at once. A server that cannot be reached or launched says so in place of its tool list.

## Deleting a server

A server cannot be deleted while any task or task template still binds one of its tools. Remove those bindings first.
