---
title: Backup and restore
sidebar_position: 4
---

# Backup and restore

[Three things](./deployment.md#state-that-has-to-persist) have to survive the loss of a container. Everything else — registered MCP servers, workflows, users, system settings — is a row in the database and is covered by backing that up.

| What | Take | Restore |
|---|---|---|
| Database | `pg_dump`, or a copy of the SQLite file | `pg_restore`, or put the file back |
| Agent skill store | A copy of the `SKILLS_DIR` tree | Extract it back into place |
| Secret encryption key | The value of `SECRET_ENCRYPTION_KEY`, or the file at `SECRET_KEY_FILE` | Set the same value, or put the same file back |

**Restore the database and the key together.** The key decrypts the local secrets *and* the approval CA's signing key, both of which are stored in the database. A database restored next to a different key comes up with every secret unreadable.

## The database

PostgreSQL:

```bash
pg_dump --format=custom --file=a2flow-$(date +%F).dump "postgresql://user:password@host:5432/a2flow"
pg_restore --clean --if-exists --dbname="postgresql://user:password@host:5432/a2flow" a2flow-2026-01-31.dump
```

Under Docker Compose, reach the `db` service directly:

```bash
docker compose exec -T db pg_dump -U a2flow -Fc a2flow > a2flow-$(date +%F).dump
docker compose exec -T db pg_restore -U a2flow -d a2flow --clean --if-exists < a2flow-2026-01-31.dump
```

SQLite is one file, at the path in `DB_URL`. Use `sqlite3 a2flow.db ".backup out.db"` rather than copying it while the app runs.

A restored database does not need a separate migration step: the backend applies any pending [Alembic](https://alembic.sqlalchemy.org/) migrations on startup, so restoring an older dump under a newer build and starting it brings the schema forward.

## The agent skill store

`SKILLS_DIR` cannot be reconstructed by re-registering the skills. Pulling a skill clones its repository's *current* head, so a run pinned to an older revision does not get that revision back — it stays unable to load its skill. Back the directory up.

A published revision directory is never modified afterwards, so a copy taken while the app is running is consistent:

```bash
tar -czf skills-$(date +%F).tgz -C /var/lib/a2flow/skills .
```

Under Docker Compose the store is the `skills` named volume:

```bash
docker run --rm -v a2flow_skills:/skills -v "$PWD:/backup" alpine \
  tar -czf /backup/skills-$(date +%F).tgz -C /skills .
```

Restore by extracting the archive back into an empty store, then start the backend.

## The secret encryption key

If you set `SECRET_ENCRYPTION_KEY` explicitly, the key already lives wherever you keep deployment configuration and needs nothing further here — just make sure that store is itself backed up.

If you did not, the backend generated one on first use and wrote it to the file at `SECRET_KEY_FILE` (default `.secret_key`, next to the SQLite database file). That file is the only copy. Back it up somewhere other than the machine it sits on, and treat it like the credential it is.

Rotating the key is not supported: the existing secrets are encrypted with the old one. See [Secret management](./configuration.md#secret-management).

## Checking a restore

1. Start the backend and confirm [`GET /api/v1/health`](./health.md) returns 200 — that proves the database is reachable and the schema is current.
2. Open a `local` [secret](../guides/secrets.md) in the admin UI. It loading rather than erroring is what proves the key matches the database.
3. Open a [workflow execution](../guides/workflow-executions.md) that was in progress. It resuming rather than reporting `SKILL_NOT_READY` is what proves the skill store came back with the revisions still in use.
