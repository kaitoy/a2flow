---
title: 健康检查
sidebar_position: 5
---

# 健康检查

编排器或负载均衡器通过轮询 `GET /api/v1/health` 来决定某个后端实例是否应接收流量。它不需要认证，返回的是一个裸对象，而不是通常的 `{meta, data, error}` 信封结构：

| 条件 | 状态 | 响应体 |
|---|---|---|
| 数据库响应了一个简单查询 | `200` | `{"status": "ok"}` |
| 数据库未响应 | `503` | `{"status": "unavailable"}` |

检查的全部内容就是这些。它以明确的状态码而不是错误页面报告故障，并且不计入访问日志，因此每隔几秒轮询一次既没有开销，也不会留下干扰信息。

**请同时将它用于 liveness 和 readiness**。无法访问数据库的后端提供不了任何有用的服务，而新实例要等启动完成后才会返回 200，此时其[迁移](../architecture/database.md)也已应用完毕。用这个端点控制发布节奏，才能确保滚动部署不会把流量发送给架构变更仍在进行的实例。

Docker Compose 已经这样做了（[compose.yml](https://github.com/kaitoy/a2flow/blob/master/compose.yml)）：

```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -sf http://localhost:8000/api/v1/health || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 10s
```

无论在哪里配置，都请为检查设置启动宽限期。首次启动会应用迁移并预置[初始用户](./configuration.md#seeded-users)，因此实例响应所需的时间比常规重启更长是正常的。

前端没有自己的健康检查路由。它不保存状态，也只依赖后端，因此向其根路径发送普通的 HTTP 请求就足以完成检查。

如需了解运行中部署的各项数据（审批积压、运行量、失败情况、前置时间、邮件队列深度），请参阅[运维指标](./metrics.md)。
