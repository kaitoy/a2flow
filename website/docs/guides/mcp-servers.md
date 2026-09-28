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
| **Script** | **Language**, **Source**, **Packages**, **Environment Variables** | Python or JavaScript code you write yourself. Each of its public functions becomes a tool — see [Writing a script](#writing-a-script). |

Switching an existing server's transport clears the fields of the transport it leaves, and a record that mixes shapes — a URL on a stdio server, a command on a remote one, source code on either — is refused.

⚠️ **Registering a stdio server means running the chosen command inside the backend container**, as the container's unprivileged user. It is gated behind the same `developer` role as any other MCP server write. Arguments are passed to the process as a list and never through a shell, and the child inherits only a small safe set of environment variables plus the ones you configure — the backend's own API keys and database URL are not visible to it.

## Writing a script

A script server turns functions you write into tools without publishing a package. Choose **Script** as the **Transport**, pick a **Language**, and paste the code into **Source**.

**Source** is a code editor. It colors the code for the selected **Language**, numbers its lines, and indents with **Tab** — press **Esc** first to move on to the next field with **Tab**. As you type, it underlines problems in place; hover over an underline to read what is wrong.

| Underline | Meaning | Examples |
|---|---|---|
| Red, wavy | Syntax error — the script cannot run | An unclosed bracket, a misspelled keyword |
| Amber, wavy | Probably a mistake | No function would become a tool; a Python function without a docstring, or a parameter without a type hint; an import from outside the standard library while **Packages** is empty; a JavaScript function without a `description` |
| Accent, wavy | A note | A JavaScript function without an `inputSchema` |

Underlines are advice and never stop you from saving; the check on save is described below.

| | Python | JavaScript |
|---|---|---|
| Functions that become tools | Every function defined at the top level whose name does not start with `_`. Functions you import are not exposed. | Every exported function (`export function`, `export async function`) whose name does not start with `_`. The default export is not exposed. |
| Tool name | The function's name | The export's name |
| Description | The docstring | The function's `description` property |
| Arguments | Read from the type hints | The function's `inputSchema` property, a JSON Schema. Without one, the tool accepts any arguments. |
| How the tool is called | Arguments by name | One object holding the arguments |
| What the agent gets back | The return value | The return value: a string as is, anything else as JSON |

```python
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b
```

```js
export function add({ a, b }) {
  return a + b;
}
add.description = "Add two numbers.";
add.inputSchema = {
  type: "object",
  properties: { a: { type: "number" }, b: { type: "number" } },
  required: ["a", "b"],
};
```

A few rules apply to both languages:

- The standard library is always available — Python's own modules, or Node.js's built-in `node:` modules. Anything else must be listed under [Packages](#adding-packages).
- An error thrown by a function reaches the agent as a failed tool call, with its message.
- Output from `print()` or `console.log()` goes to the server log, not to the agent.
- **Environment Variables** are readable as `os.environ["NAME"]` or `process.env.NAME`, and may use the placeholders under [Keeping credentials out of the record](#keeping-credentials-out-of-the-record).
- **Source** holds at most 30,000 characters.
- Python code with a syntax error is refused when saving, with the line number. JavaScript is not checked on save — [test it](#testing-a-script) before saving to catch a script that cannot load.
- A script that fails to load — a package that will not install, a syntax error, or an error thrown at its top level — still starts. Every tool call to it fails with the error that stopped it, and [checking its tools](#checking-a-servers-tools) shows the server as unusable.

⚠️ A script runs in the same place as a stdio server, under the same restrictions.

### Adding packages {#adding-packages}

A script that talks to another service usually needs that service's client library — `boto3` for AWS, for example. List each one under **Packages**, one per row, and import it in **Source** as usual.

| Language | Write a package as | Examples |
|---|---|---|
| Python | A name from PyPI, optionally with a version | `boto3`, `boto3==1.40.0`, `requests>=2.32` |
| JavaScript | A name from the npm registry, optionally with `@version` | `is-number`, `@aws-sdk/client-s3@3` |

```python
import boto3


def list_buckets() -> list[str]:
    """List the S3 buckets the configured credentials can see."""
    return [b["Name"] for b in boto3.client("s3").list_buckets()["Buckets"]]
```

- Packages are installed the first time the script starts with that list, which can take a while; later starts reuse the installed copy. Scripts that list exactly the same packages share one copy.
- A package that cannot be installed — a misspelled name, a version that does not exist — stops the script from loading. [Load tools](#testing-a-script) shows the installer's error.
- A server holds at most 20 packages, each at most 200 characters and starting with a letter, a digit, or `@`.
- Installing needs the package registry to be reachable from where scripts run. To install from a private index instead, set the installer's own variable under **Environment Variables** — `UV_INDEX_URL` for Python, `NPM_CONFIG_REGISTRY` for JavaScript.

## Testing a script

The **Test Run** panel under **Environment Variables** runs the script exactly as the form holds it, without saving. Use it to catch a script that will not load before an agent tries to use it.

1. Click **Load tools**. The script starts with the **Source**, **Packages**, and **Environment Variables** currently in the form.
2. Pick a tool from **Tool**. **Arguments** fills in with every argument the tool declares, each set to `null`.
3. Edit **Arguments** — a JSON object — and click **Run**.

| You see | Meaning |
|---|---|
| A tool list | The script loaded; these are the tools it will expose |
| Red text in place of the tool list | The script could not load. The text is the error that stopped it |
| **This script exposes no tools.** | The script loaded, but no function would become a tool |
| The tool's output in **Output** | The call succeeded |
| Red text in **Output** | The tool threw an error; the text is its message |
| **Arguments must be a JSON object.** or **Invalid JSON: …** | **Arguments** is not a JSON object; nothing was run |

Placeholders in **Environment Variables** are expanded as they are for a saved server, so a test run reaches the same services with the same credentials. A test run is a real call: whatever the tool does happens.

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
