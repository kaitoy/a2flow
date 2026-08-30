---
title: Health checks
sidebar_position: 5
---

# Health checks

`GET /api/v1/health` is what an orchestrator or load balancer polls to decide whether a backend instance should receive traffic. It takes no authentication and returns a bare object rather than the usual `{meta, data, error}` envelope:

| Condition | Status | Body |
|---|---|---|
| The database answered a trivial query | `200` | `{"status": "ok"}` |
| It did not | `503` | `{"status": "unavailable"}` |

That is the whole check. It reports a failure as a definite status code instead of an error page, and it is excluded from the access log, so polling it every few seconds costs nothing and leaves no noise behind.

**Use it for both liveness and readiness.** A backend that cannot reach its database can serve nothing useful, and a fresh instance only answers 200 once its startup has finished — which is also when its [migrations](../architecture/database.md) have been applied. Gating rollout on this endpoint is what keeps a rolling deploy from sending traffic to an instance whose schema work is still running.

Docker Compose already does this ([compose.yml](https://github.com/kaitoy/a2flow/blob/master/compose.yml)):

```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -sf http://localhost:8000/api/v1/health || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 10s
```

Give the check a start-up grace period wherever you configure it. The first startup applies migrations and seeds the [initial users](./configuration.md#seeded-users), so an instance can legitimately take longer to answer than a steady-state restart would.

The frontend has no health route of its own. It holds no state and depends on nothing but the backend, so a plain HTTP request to its root is enough of a check.

For the numbers behind a running deployment — approval backlog, run volume, failures, lead time, email queue depth — see [Operations metrics](./metrics.md).
