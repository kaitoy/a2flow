---
title: Notifications
sidebar_position: 11
---

# Notifications

A **bell icon** in the top toolbar (present on both the chat header and the admin sidebar) opens a notification center with an unread-count badge. Notifications are **per-user**, persisted in `a2flow.db`, and delivered by **polling** (the frontend refreshes every 30 seconds).

The bell's dropdown lists **unread notifications only** — it is there to surface what still needs attention. The full history, read items included, lives on a dedicated [Notifications page](./notifications.md#notification-history-page), reachable from the account menu (toolbar profile button → **Notifications**), which is also the only place a notification can be deleted.

Four workflow events generate a notification. The recipient depends on the event: a `request_approval` notification is addressed to that approval's **designated approver** — or, for a group destination, one notification per eligible member — while the others are addressed to the **user who started the session or generation**:

| Type | Raised when |
|---|---|
| `workflow_draft_ready` | The background design run of ["Generate workflow"](./workflows.md#generating-a-workflow) finished and the draft's initial task templates are ready for review. |
| `workflow_generation_failed` | That same design run failed. Since it runs unattended with no client watching it, this is how the user finds out; the reason is on the workflow's detail page and in its design chat. |
| `approval_request` | The agent requests a mid-execution decision (`request_approval`) and waits for the designated approver. |
| `execution_completed` | Every `WorkflowTask` in the run has reached a terminal state (`completed` / `failed` / `skipped`) — emitted once per run, whether the final task was written by the execution agent or through the REST task endpoints. The same evaluation stamps the run's own [terminal status](./workflow-executions.md). |

Clicking a notification marks it read and deep-links to the relevant place: run-scoped events to the `/workflow-executions/{id}/session` chat, workflow-scoped ones (`workflow_draft_ready`, `workflow_generation_failed`) to the workflow's detail page. Each row also has a **"Mark as read" (✓)** button that clears it from the dropdown without navigating, and the panel header offers a **"Mark all read"** action (shown only while unread items remain) that clears every unread notification at once. Nothing in the dropdown deletes a notification — marking it read only moves it out of the way.

## Notification history page

The [`/notifications`](http://localhost:3000/notifications) page, reachable from the toolbar profile button's account menu (**Notifications**), lists every notification the signed-in user has received, read ones included, as a sortable and filterable table (title, type, and creation time). An **All / Unread** switch above it toggles the read-state filter, each unread row offers the same **"Mark as read"** action, and every row has a **delete (✕)** button that permanently removes that notification after a confirmation dialog.

`GET /api/v1/notifications` takes the same `limit` / `offset` / `s` / `q` [list query parameters](./admin-ui.md#list-query-parameters) as every other collection endpoint, so unread-only listing is `?q=read:eq:false` and ordering is e.g. `?s=-createdAt` (the default). `PATCH /api/v1/notifications/{id}` takes a request body and accepts `read` as its only mutable field, so `{"read": true}` marks a notification read and `{"read": false}` returns it to unread. Those endpoints, plus mark-all-read and delete, are documented in the [API reference](http://localhost:3000/api-doc); all are scoped to the authenticated user, so reading, updating, or deleting another user's notification returns HTTP 404 — and a `q` term naming `userId` can only narrow that scope, never escape it. Notifications cascade-delete with their recipient user and their linked `WorkflowExecution` or `Workflow`.

## Email delivery

Once a `super_admin` has configured an SMTP server under [System Settings](./system-settings.md), the same four events are **also emailed** to the recipient, so an approval request does not have to wait for someone to open the app.

The message carries the notification's title as its subject, its body as the text, and a link back to what it is about — the run for `approval_request` / `execution_completed`, the workflow for `workflow_draft_ready` / `workflow_generation_failed` — built from the configured **Application Base URL**. When no base URL is set the message is sent without a link.

Recipients who cannot be reached are skipped before any relay is contacted: the internal system user, disabled or soft-deleted accounts, accounts whose address is unverified, and any account without an address. There is no per-user opt-out — email delivery is on or off for the whole platform.

### The delivery queue

Nothing is sent while a workflow operation is in flight. The notification row and a row in `outbound_emails` — the fully rendered message, recipient and all — are written in **one transaction**, so a crash can never leave a notification whose email was never queued. A worker then drains that queue:

- **Paced.** A token bucket holds the relay to a sustained rate (5/s by default, with a burst of 10), and a whole batch goes out over one reused SMTP connection.
- **Retried.** A transient failure — the relay is down, returns a 4xx, or rejects the credentials — schedules another attempt with exponential backoff and jitter: 15s, 30s, 1m, 2m, doubling to a one-hour ceiling. The default budget of 9 attempts rides out roughly an hour of downtime.
- **Written off when hopeless.** A failure the relay reports as permanent (an unknown recipient, say) is not retried at all. Once a message is out of attempts, or fails permanently, it stays as `status=failed` with the last error on the row — a dead letter to look at, not a silent loss. Delivered messages are purged after 30 days; dead letters are kept.

Exactly **one process sends at a time**, elected by a PostgreSQL advisory lock, which is what makes the rate limit exact rather than approximate. Scaling the worker past one replica buys failover, not throughput. A sender that dies mid-batch leaves its claims leased; the next pass reclaims them without spending an attempt.

The API process runs the worker itself by default, so `uvicorn main:app` alone delivers mail. `compose.yml` instead runs a dedicated `worker` service and sets `EMAIL_WORKER_IN_PROCESS=false` on the API, keeping SMTP work off the process serving requests. Every tunable is listed under **Outgoing email queue** in [`backend/.env.example`](https://github.com/kaitoy/a2flow/blob/master/backend/.env.example).

Backlog and stuck-relay symptoms are visible on the [metrics endpoint](../operations/metrics.md) as `a2flow_email_queue_depth{tenant,status}` and `a2flow_email_queue_oldest_pending_age_seconds{tenant}`.
