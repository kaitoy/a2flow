---
title: 运维指标
sidebar_position: 6
---

# 运维指标

工作流运维数据（审批积压、运行量、失败情况和前置时间）以两种形式开放给第三方仪表板。两种形式都限定在调用方所在的租户内，除下文提到的失败列表外，任何已认证的用户都可以使用。

被[访问控制标签](../guides/tags.md#access-control-tags)对调用方隐藏的运行，不会出现在下面的任何视图中，这与它们不出现在运行列表中的处理方式完全相同，因此指标绝不会提及读者无法打开的运行。

从仍处于 `草稿` 状态的工作流启动的运行（开发人员或超级管理员的[发布前测试运行](../guides/workflows.md#running-a-workflow)）会被记录为 `isDraft: true`，并**从下面所有指标中排除**，包括 Prometheus KPI 和聚合子资源（含审批积压视图），因此一次性的测试数据绝不会使数字失真。这个标志在运行启动时确定；之后发布工作流也不会重新归类已经发生的运行。

## Prometheus 端点 {#prometheus-endpoint}

`GET /api/v1/metrics` 以 [Prometheus](https://prometheus.io/) 文本展示格式输出单值 KPI。每个样本都带有 `tenant` 标签。

审批：

| 指标 | 含义 |
|---|---|
| `a2flow_approvals_pending` | 等待决定的审批请求 |
| `a2flow_approvals_pending_over_threshold{threshold}` | 其中等待时间超过阈值（默认 24 小时）的请求 |
| `a2flow_approval_pending_age_seconds_max` | 等待最久的请求已等待的时长 |
| `a2flow_approvals_decided_today{decision}` | 今天作出决定的审批，按 `approved` / `rejected` / `returned` 划分 |

工作流执行：

| 指标 | 含义 |
|---|---|
| `a2flow_workflow_executions_active` | 当前进行中的运行（`running` 或 `scheduled`） |
| `a2flow_workflow_executions_finished_today{status}` | 今天结束的运行，按终止状态划分 |
| `a2flow_workflow_executions_started_recently{window,workflow}` | 过去 24 小时内启动的运行，按工作流划分 |
| `a2flow_workflow_executions_failed_recently{window}` | 过去 24 小时内以失败结束的运行 |
| `a2flow_workflow_tasks_failed_recently{window,error_kind}` | 过去 24 小时内失败的任务，按原因划分 |
| `a2flow_workflow_execution_lead_time_seconds_avg{window,workflow}` | 过去 24 小时内结束的运行从开始到结束的平均时长 |

通知邮件：

| 指标 | 含义 |
|---|---|
| `a2flow_email_queue_depth{status}` | [外发队列](../guides/notifications.md#the-delivery-queue)中的邮件，按 `pending` / `sending` / `sent` / `failed` 划分 |
| `a2flow_email_queue_oldest_pending_age_seconds` | 等待最久的未投递邮件已等待的时长；无法访问中继时会上升 |

`?thresholdHours=` 可覆盖审批积压的判定阈值。`TIMEZONE`（IANA 名称，默认为 `UTC`；请参阅[服务器设置](./configuration.md#server-settings)）决定“今天”从何时开始；无法识别的名称会回退到 UTC，而不会导致启动失败。

该端点由普通的会话 Cookie 保护，因此抓取配置必须携带一个 Cookie。`GET` 是安全方法，因此不需要 CSRF 令牌：

```yaml
- job_name: a2flow
  metrics_path: /api/v1/metrics
  http_headers:
    Cookie: { values: ["a2flow_session=<token>"] }
```

会话的空闲超时会在每次请求时滑动，因此持续运行的抓取会让自己的会话一直保持有效；但会话无法在后端重启或显式退出登录后继续存在，这时就必须刷新令牌。一次抓取只覆盖一个租户；如需监控多个租户，请为每个租户配置一个作业。

## 聚合子资源 {#aggregate-sub-resources}

凡是自然键为用户 ID、运行 ID 或自由文本错误消息的数据，都特意不放入 Prometheus，因为它们的标签集合没有上限。这些视图改为以现有集合的 JSON 子资源形式提供，使用通常的 `{meta, data, error}` 信封结构：

| 端点 | 返回内容 |
|---|---|
| `GET /api/v1/workflow-executions/by-workflow` | 各工作流的运行计数（`total` / `running` / `completed` / `failed`；`running` 包含 `scheduled` 的运行）和平均前置时间 |
| `GET /api/v1/workflow-executions/lead-time-trend` | 每日平均前置时间，每个自然日一个分桶，包括空的分桶 |
| `GET /api/v1/workflow-executions/failures` | 需要排查的运行，每条都带有其失败的任务及记录的原因。仅限管理员，因为其中会引用调用方可能未参与的运行的任务标题和错误消息 |
| `GET /api/v1/approvals/by-approver` | 各指定审批人的待审批积压 |
| `GET /api/v1/approvals/by-workflow` | 同样的积压，按工作流分组 |

执行类端点接受 `since` / `until`（ISO-8601，默认为过去 30 天，上限为 366 天）和 `limit`；审批类端点接受 `thresholdHours`（默认 24）和 `limit`。积压条目按单项等待时间从长到短返回，因此 `?limit=5` 就是最严重的五项。时长始终为整数秒。

`by-approver` 按审批的**目标**分组，目标可以是用户或用户组。每个条目都带有值为 `"user"` 或 `"group"` 的 `groupKind` 以示区分：`"user"` 条目只给出 ID，而 `"group"` 条目还会在 `groupLabel` 中给出用户组的名称。

失败的任务会记录**原因**：`error_kind`（`api_error`、`timeout`、`script_error`、`invalid_input`、`permission_denied`、`rejected`、`other` 之一）和自由文本的 `error_message` 会与 `status="failed"` 一起存储。两者都是普通的任务字段，因此可以据此筛选任务列表，例如 `?q=errorKind:eq:timeout`。
