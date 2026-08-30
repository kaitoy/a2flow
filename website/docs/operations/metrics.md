---
title: Operations metrics
sidebar_position: 6
---

# Operations metrics

Workflow operations data — approval backlog, run volume, failures, and lead time — is exposed for third-party dashboards in two shapes, both scoped to the caller's tenant and both available to any authenticated user.

Runs started from a still-`draft` workflow (a `developer`/`super_admin` [pre-publish test run](../guides/workflows.md#running-a-workflow)) are recorded with `isDraft: true` and **excluded from every metric below** — both the Prometheus KPIs and the aggregate sub-resources, including the approval-backlog views — so throwaway test data never skews the numbers. The flag is fixed when the run starts; publishing the workflow afterwards does not reclassify runs that already happened.

## Prometheus endpoint

`GET /api/v1/metrics` renders the single-value KPIs in [Prometheus](https://prometheus.io/) text exposition format. Every sample carries a `tenant` label.

Approvals:

| Metric | Meaning |
|---|---|
| `a2flow_approvals_pending` | Approval requests awaiting a decision |
| `a2flow_approvals_pending_over_threshold{threshold}` | Of those, the ones waiting longer than the threshold (default 24h) |
| `a2flow_approval_pending_age_seconds_max` | How long the longest-waiting request has been waiting |
| `a2flow_approvals_decided_today{decision}` | Approvals decided today, by `approved` / `rejected` / `returned` |

Workflow executions:

| Metric | Meaning |
|---|---|
| `a2flow_workflow_executions_active` | Runs currently in progress |
| `a2flow_workflow_executions_finished_today{status}` | Runs that finished today, by terminal status |
| `a2flow_workflow_executions_started_recently{window,workflow}` | Runs started in the last 24h, by workflow |
| `a2flow_workflow_executions_failed_recently{window}` | Runs that finished in failure in the last 24h |
| `a2flow_workflow_tasks_failed_recently{window,error_kind}` | Tasks that failed in the last 24h, by cause |
| `a2flow_workflow_execution_lead_time_seconds_avg{window,workflow}` | Mean start-to-finish duration of runs finishing in the last 24h |

Notification email:

| Metric | Meaning |
|---|---|
| `a2flow_email_queue_depth{status}` | Emails in the [outgoing queue](../guides/notifications.md#the-delivery-queue), by `pending` / `sending` / `sent` / `failed` |
| `a2flow_email_queue_oldest_pending_age_seconds` | How long the longest-waiting undelivered email has waited — rises when the relay is unreachable |

`?thresholdHours=` overrides the stalled-approval cutoff. `METRICS_TIMEZONE` (an IANA name, default `UTC`) decides where "today" starts; an unrecognized name falls back to UTC rather than failing startup.

The endpoint is protected by the ordinary session cookie, so a scrape config has to carry one. `GET` is a safe method, so no CSRF token is needed:

```yaml
- job_name: a2flow
  metrics_path: /api/v1/metrics
  http_headers:
    Cookie: { values: ["a2flow_session=<token>"] }
```

The session's idle timeout slides on every request, so a running scrape keeps its own session alive indefinitely; it does not survive a backend restart or an explicit logout, which is when the token has to be refreshed. A scrape covers exactly one tenant — to watch several, configure one job per tenant.

## Aggregate sub-resources

Anything whose natural key is a user id, a run id, or a free-text error message is deliberately kept out of Prometheus — those are unbounded label sets. Those views are served as JSON sub-resources of the existing collections instead, in the usual `{meta, data, error}` envelope:

| Endpoint | Returns |
|---|---|
| `GET /api/v1/workflow-executions/by-workflow` | Per-workflow run counts (`total` / `running` / `completed` / `failed`) and average lead time |
| `GET /api/v1/workflow-executions/lead-time-trend` | Daily average lead time, one bucket per calendar day including empty ones |
| `GET /api/v1/workflow-executions/failures` | Runs needing triage, each with its failed tasks and their recorded cause |
| `GET /api/v1/approvals/by-approver` | Pending-approval backlog per designated approver |
| `GET /api/v1/approvals/by-workflow` | The same backlog, grouped by workflow |

The execution endpoints take `since` / `until` (ISO-8601, defaulting to the last 30 days, capped at 366) and `limit`; the approval endpoints take `thresholdHours` (default 24) and `limit`. Backlog entries come back longest-single-wait first, so `?limit=5` is the worst five. Durations are always whole seconds.

`by-approver` groups by an approval's **destination**, which may be a user or a group. Each entry carries a `groupKind` of `"user"` or `"group"` to tell them apart: a `"user"` entry gives the id only, while a `"group"` entry also carries the group's name in `groupLabel`.

A task that fails records **why**: `error_kind` (one of `api_error`, `timeout`, `script_error`, `invalid_input`, `permission_denied`, `rejected`, `other`) and a free-text `error_message` are stored alongside `status="failed"`. Both are ordinary task fields, so a task list can be filtered on them — e.g. `?q=errorKind:eq:timeout`.
