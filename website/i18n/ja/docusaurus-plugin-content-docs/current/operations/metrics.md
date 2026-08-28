---
title: 運用メトリクス
sidebar_position: 4
---

# 運用メトリクス

ワークフローの運用データ(承認の滞留、実行の件数、失敗、リードタイム)は、外部のダッシュボード向けに 2 つの形で公開しています。どちらも呼び出し元のテナントに閉じ、どちらも認証済みのユーザーなら誰でも利用できます。

まだ `draft` のワークフローから開始された実行(`developer` や `super_admin` による[公開前のテスト実行](../guides/workflows.md#running-a-workflow))は `isDraft: true` で記録され、**以下のすべてのメトリクスから除外されます**。Prometheus の KPI も、承認の滞留のビューを含む集計サブリソースも同じです。使い捨てのテストデータが数字を歪めないようにするためです。このフラグは実行の開始時に決まります。あとからワークフローを公開しても、すでに起きた実行が分類し直されることはありません。

## Prometheus のエンドポイント

`GET /api/v1/metrics` は単一値の KPI を [Prometheus](https://prometheus.io/) のテキスト形式で返します。すべてのサンプルに `tenant` ラベルが付きます。

| メトリクス | 意味 |
|---|---|
| `a2flow_approvals_pending` | 判断待ちの承認依頼 |
| `a2flow_approvals_pending_over_threshold{threshold}` | そのうち、しきい値(既定 24 時間)より長く待っているもの |
| `a2flow_approval_pending_age_seconds_max` | 最も長く待っている依頼の待ち時間 |
| `a2flow_workflow_executions_active` | 進行中の実行 |
| `a2flow_workflow_executions_finished_today{status}` | 今日終了した実行を終了ステータス別に集計 |
| `a2flow_approvals_decided_today{decision}` | 今日判断された承認を `approved` / `rejected` / `returned` 別に集計 |
| `a2flow_workflow_executions_failed_recently{window}` | 直近 24 時間に失敗で終わった実行 |
| `a2flow_workflow_tasks_failed_recently{window,error_kind}` | 直近 24 時間に失敗したタスクを原因別に集計 |
| `a2flow_workflow_executions_started_recently{window,workflow}` | 直近 24 時間に開始された実行をワークフロー別に集計 |
| `a2flow_workflow_execution_lead_time_seconds_avg{window,workflow}` | 直近 24 時間に終了した実行の、開始から終了までの平均時間 |
| `a2flow_email_queue_depth{status}` | [送信キュー](../guides/notifications.md#the-delivery-queue)にある通知メールを `pending` / `sending` / `sent` / `failed` 別に集計 |
| `a2flow_email_queue_oldest_pending_age_seconds` | 未配信のメールのうち最も長く待っているものの待ち時間。リレーに到達できないと増えます |

`?thresholdHours=` で滞留承認の区切りを上書きできます。「今日」がどこで始まるかは `METRICS_TIMEZONE`(IANA の名前。既定は `UTC`)が決めます。認識できない名前は起動を止めず UTC にフォールバックします。

このエンドポイントは通常のセッションクッキーで保護されているので、スクレイプの設定にもクッキーが要ります。`GET` は安全なメソッドなので CSRF トークンは不要です。

```yaml
- job_name: a2flow
  metrics_path: /api/v1/metrics
  http_headers:
    Cookie: { values: ["a2flow_session=<token>"] }
```

セッションのアイドルタイムアウトはリクエストのたびにスライドするので、稼働中のスクレイプは自分のセッションを無期限に維持します。維持できなくなるのはバックエンドの再起動か明示的なログアウトのときで、そのタイミングでトークンを更新します。1 つのスクレイプが対象にするのはちょうど 1 テナントです。複数を監視するなら、テナントごとにジョブを設定してください。

## 集計サブリソース

ユーザー ID、実行 ID、自由入力のエラーメッセージのように自然キーが定まらないものは、意図的に Prometheus に載せていません。ラベルの集合が無制限になるからです。これらは代わりに、既存のコレクションの JSON サブリソースとして、いつもの `{meta, data, error}` の封筒で提供します。

| エンドポイント | 返すもの |
|---|---|
| `GET /api/v1/workflow-executions/by-workflow` | ワークフローごとの実行件数(`total` / `running` / `completed` / `failed`)と平均リードタイム |
| `GET /api/v1/workflow-executions/lead-time-trend` | 日ごとの平均リードタイム。空の日も含めて 1 日 1 バケット |
| `GET /api/v1/workflow-executions/failures` | 調査が必要な実行。失敗したタスクと記録された原因つき |
| `GET /api/v1/approvals/by-approver` | 指名された承認者ごとの、承認待ちの滞留 |
| `GET /api/v1/approvals/by-workflow` | 同じ滞留をワークフロー単位でまとめたもの |

実行側のエンドポイントは `since` と `until`(ISO-8601。既定は直近 30 日、上限 366 日)と `limit` を受け取り、承認側のエンドポイントは `thresholdHours`(既定 24)と `limit` を受け取ります。滞留の項目は 1 件あたりの待ち時間が長い順に返るので、`?limit=5` は最悪の 5 件になります。時間は常に秒の整数値です。

`by-approver` は承認の**宛先**で集計します。宛先はユーザーかグループのどちらかで、裸の ID では区別できません。そのため各項目は `"user"` か `"group"` の `groupKind` を持ちます。`"user"` の場合に返すのは **ID だけ**で、名前は返しません。名前の解決は `UserService` が決めることですし、クライアントはすでに `POST /users/resolve-names` で ID を一括解決しているからです。`"group"` の場合は項目の `groupLabel` にグループ名が入ります。グループ名にはそうした可視性の規則がないためです。

失敗したタスクは**理由**を記録します。実行エージェントが `status="failed"` と一緒に `error_kind`(`api_error`、`timeout`、`script_error`、`invalid_input`、`permission_denied`、`rejected`、`other` のいずれか)と自由入力の `error_message` を渡します。どちらも通常のタスクのフィールドなので、[一覧クエリパラメータ](../guides/admin-ui.md#list-query-parameters)で絞り込めます(たとえば `?q=errorKind:eq:timeout`)。
