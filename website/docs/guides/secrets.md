---
title: Secrets
sidebar_position: 9
---

# Secrets

Navigate to [http://localhost:3000/admin/secrets](http://localhost:3000/admin/secrets) to manage named credentials used for authentication elsewhere in the app.

A secret is a **named bundle of key/value entries**, the same shape [HashiCorp Vault's KV engine](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2) uses: one path holds a map of keys to values. Like the other registries, a secret can carry [tags](./tags.md). Credentials that belong together — an AWS access key id and its secret access key, say — live in one secret as two entries rather than in two separate secrets.

A single entry is referenced as `name/key`:

- **MCP server headers and environment** — any header value (streamable HTTP) or environment variable value (stdio) may embed `${secret:name/key}` placeholders, expanded when connecting (see [MCP Servers](./mcp-servers.md)).
- **Agent Skill repository clones** — a skill's **Auth Password** is a `name/key` reference to the entry used as the git basic-auth password, chosen from dropdowns rather than typed (see [Agent Skills](./agent-skills.md)).

The key is **always required**, even when the secret holds a single entry — a bare name identifies a map, not a value. A key-less `${secret:name}` fails with `SECRET_RESOLUTION_FAILED` rather than being passed through as a literal string.

| Operation | Path |
|-----------|------|
| List all secrets | `GET /admin/secrets` |
| Register a new secret | `GET /admin/secrets/new` |
| A secret's detail page — edit / delete | `GET /admin/secrets/{id}` |

A secret has one of two types:

- **Local (encrypted)** — the entries are submitted once and stored in `a2flow.db` with each value encrypted with [Fernet](https://cryptography.io/en/latest/fernet/) (AES-128-CBC + HMAC). Keys are stored in plaintext so they can be listed without decrypting anything. The API is **write-only**: a response carries the entry keys but never a value (neither plaintext nor ciphertext). The detail page therefore shows every stored key with a blank value — leave one blank to keep the stored value, retype it to replace it, or remove the row to delete that entry.
- **HashiCorp Vault** — only a KV v2 reference (mount and path) is stored; every key at that path is readable, and each value is fetched live from Vault when it is resolved.

`GET /api/v1/secrets/{id}/keys` lists one secret's entry keys — and only its keys — for both types alike: from the stored map for a `local` secret, from a live KV v2 read for a `vault` one (which yields HTTP 502 `SECRET_RESOLUTION_FAILED` when Vault is unreachable or unconfigured). The Agent Skill auth-password picker uses it; the `keys` field on a secret read cannot serve that purpose, since it is always empty for a `vault` secret.

Secrets are referenced **by name** and resolved lazily: renaming or deleting a secret that something still references does not fail at edit time, but the next use fails with HTTP 502 (`SECRET_RESOLUTION_FAILED`) naming the missing secret.

## Encryption key

The Fernet key for local secrets is resolved at first use with the following precedence:

1. `SECRET_ENCRYPTION_KEY` env var (must be a valid Fernet key; generate one with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
2. The key file at `SECRET_KEY_FILE` (default: `.secret_key` next to the SQLite database file, or the working directory for other databases).
3. A fresh key is generated, saved to that file, and a WARNING is logged.

⚠️ Back the key up — losing it makes every stored local secret undecryptable.

## HashiCorp Vault connection

A single global Vault connection is configured through env vars (see `backend/.env.example`): `VAULT_ADDR` selects the server, and either a static `VAULT_TOKEN` or **AppRole** credentials (`VAULT_ROLE_ID` + `VAULT_SECRET_ID`, login mount configurable via `VAULT_APPROLE_MOUNT`, default `approle`) authenticate. AppRole takes precedence when both are set; its client token is cached and refreshed automatically when its lease expires. Only the KV v2 secrets engine is supported. When Vault is not configured, `vault`-type secrets fail to resolve with `SECRET_RESOLUTION_FAILED`.
