---
title: Horizontal scaling
sidebar_position: 3
---

# Horizontal scaling

Running more than one backend replica requires PostgreSQL (SQLite is single-writer and single-process). All replicas then share one database, which is also what coordinates them.

Writes to an ADK session are already safe across replicas: google-adk's `DatabaseSessionService.append_event` takes `SELECT ... FOR UPDATE` on the session row for the whole append transaction, so appends to one session are serialized and neither the session state nor the event rows can be lost.

Reads are the part that needs help. The ADK `Runner` holds one in-memory session for the length of an invocation, so events another replica appends during that window never reach it, and the rest of the run reasons over a conversation that is missing them. Serializing writes cannot repair that — only keeping a session to one driver at a time can. So `POST /api/v1/agent` takes a **PostgreSQL session-level advisory lock** (`infrastructure/locks.py`) keyed on `app_name:user_id:thread_id` and holds it for the whole SSE stream. A second concurrent run of the same session is refused with HTTP 409 `SESSION_RUN_IN_PROGRESS` before any SSE headers are sent, rather than being left to diverge quietly. Different sessions never contend, and the lock is briefly waited on before it gives up, so a client that aborts a stream and immediately retries is not rejected while the abandoned run is still tearing down.

Because the lock is session-level (not transaction-level), the deployment must not place a **transaction-pooling** proxy — PgBouncer in `transaction` mode, and most serverless PostgreSQL poolers — between the app and PostgreSQL; the lock would not survive between statements. Session-level pooling (or a direct connection) is required.

Human-in-the-loop is unaffected: a frontend tool call ends the run and closes the stream, releasing the lock, and the approval resumes as a *new* `POST /agent` that may land on any replica.
