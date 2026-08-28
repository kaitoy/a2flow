---
title: Agent Skills
sidebar_position: 6
---

# Agent Skills

Navigate to [http://localhost:3000/admin/agent-skills](http://localhost:3000/admin/agent-skills) to manage the Agent Skills registry — a catalog of AI agent skills stored in Git repositories.

| Operation | Path |
|-----------|------|
| List all skills | `GET /admin/agent-skills` |
| Register a new skill | `GET /admin/agent-skills/new` |
| A skill's detail page — edit / delete | `GET /admin/agent-skills/{id}` |
| Generate a workflow from a skill | "Generate workflow" in the list's Actions column, or the Generate Workflow icon button in the detail page's header (see [Generating a workflow](./workflows.md#generating-a-workflow)) |
| Pull a skill's repository | `POST /api/v1/agent-skills/{id}/pull` |

Skills are persisted in a SQLite database (`a2flow.db` by default, configurable via `DB_URL` in `backend/.env`). Each record stores the skill name, repository URL, repository path, an optional **Ref** (a branch or tag name), and description, plus any [tags](./tags.md) it is classified by.

## The skill store

Registering a skill returns immediately and **shallow-clones its repository in the background** using [Dulwich](https://www.dulwich.io/) — no external `git` CLI required. The clone is published into the skill store under `SKILLS_DIR` as one immutable directory per revision:

```
$SKILLS_DIR/<agent_skill_id>/<commit_sha>/
```

The clone is staged in a temporary sibling directory and moved into place with a single atomic rename, so a replica reading the store never sees a half-written revision. A published revision is then **never modified** — a pull only ever adds a sibling.

The list and detail pages show each skill's **Status** (`Cloning` / `ready` / `failed`, with the failure reason) and the short **Revision** it has published. Two fields carry that state, and they mean different things:

- **`commitSha`** — the published revision. A skill is runnable **only** once this is set; a workflow started against a skill with no revision is rejected with HTTP 409 (`SKILL_NOT_READY`).
- **`syncStatus`** — how the *last* clone or pull went. A pull that fails does **not** clear `commitSha`, so a skill that was working keeps working at its previous revision; only the status and the error change.

**Pull** re-clones the repository at its configured **Ref**, or its default branch when none is set. It is how a skill picks up upstream changes, and how a failed registration clone is retried after fixing the URL or the credentials. Setting a **Ref** (a branch or tag name) pins every clone and pull to that ref instead of the repository's default branch — a moved branch tip or a re-pointed tag is picked up the next time the skill is synced. Concurrent clones of one skill are serialized across replicas by the advisory lock in `backend/infrastructure/locks.py`; a replica that finds another already cloning the skill skips the work instead of duplicating it. After a successful pull, revisions that no longer back any workflow execution are pruned.

Under `docker compose`, `SKILLS_DIR` is `/var/lib/a2flow/skills`, persisted in the `skills` Docker volume so the store survives container recreation. It is **durable state, not a cache**: a workflow execution pins the revision it started with, so wiping the directory leaves existing executions unable to load their skill until an admin pulls again. Scaling the backend past one replica requires every replica to mount this same volume.

Private repositories are supported through the optional **Auth Password** field. It is not typed in: pick a registered [Secret](./secrets.md) and one **Entry Key** within it from the two dropdowns, and that entry's value is used as the HTTP basic-auth password (typically a personal access token) when the repository is cloned. Both secret types are offered — a `vault` secret's entry keys are read live from its KV v2 path, since they are not stored locally. The **Auth Username** field defaults to `x-access-token` (suitable for GitHub PATs); set it explicitly for hosts that require a real account name.

The secret is stored as a `name/key` reference and resolved at clone time, so deleting or renaming it later makes the next pull fail and record the reason on the skill. The detail page does not quietly drop such a stale reference: it stays selected, marked `(not found)`, with a warning — clearing it is your call.
