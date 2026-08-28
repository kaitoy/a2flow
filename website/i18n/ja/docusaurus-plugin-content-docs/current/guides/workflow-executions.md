---
title: ワークフロー実行
sidebar_position: 4
---

# ワークフロー実行

[http://localhost:3000/admin/workflow-executions](http://localhost:3000/admin/workflow-executions) ですべての `WorkflowExecution` を閲覧できます。各行からは、そのワークフローセッション(`/workflow-executions/{id}/session`)と、入れ子の**ワークフロータスク**管理ページ(`/admin/workflow-executions/{id}/workflow-tasks`)へリンクします。後者は実行のタスクの**読み取り専用**の表示です。タスクテンプレートを編集するのはワークフローの[タスクテンプレート](./workflows.md#adjusting-the-task-templates)側で、実行のステータスを進めるのは実行エージェント(と承認フロー)なので、実行の履歴は実際に走ったとおりに保たれます。

**下書き**列は、まだ `draft` のワークフローから開始された実行にバッジを付け([公開前のテスト実行](./workflows.md#running-a-workflow)。[運用メトリクス](../operations/metrics.md)からは除外されます)、Yes/No のフィルタとしても働くので隠せます。同じバッジは実行の詳細ページでもステータスの隣に出ます。行の**削除**操作は、確認のうえで `WorkflowExecution` を削除します。レコード、そのタスク(カスケード)、そのワークフローセッションがすべて消えます。

ワークフロータスクのページには**テーブル/グラフ**の切り替えがあります。グラフ表示は [React Flow](https://reactflow.dev/) でタスクの DAG を描き、依存順にタスクを 1 列に縦に積むので、前提になるタスクが依存する側の上に並びます。各タスクからは右へ、ツールを取る MCP サーバー、さらに個々のツールへと枝分かれします(読み取り専用。パン、ズーム、全体表示ができます)。

| 操作 | パス |
|-----------|------|
| 実行の一覧 | `GET /admin/workflow-executions` |
| 実行の削除 | `DELETE /api/v1/workflow-executions/{id}` |
| 実行のタスクを見る | `GET /admin/workflow-executions/{id}/workflow-tasks` |
| 実行の MCP ツール呼び出しを見る | `GET /admin/workflow-executions/{id}/tool-invocations` |

**ツール呼び出し**のページ(`/admin/workflow-executions/{id}/tool-invocations`。実行の詳細ヘッダーから開きます)には、その実行について[プロキシ](https://github.com/kaitoy/a2flow/blob/master/backend/README.md#mcp-proxy)が下した MCP ツール呼び出しの判断が並びます。上流へ送られた `allowed` のものと、ポリシーが拒否した `denied` のものが、ツール、サーバー、拒否理由、提示された証明書とともに出ます。引数はダイジェストとしてしか現れず、生の値は保存されません。[モック](./tool-mocks.md)されたツールへの呼び出しは、どちらの結果になったかに関係なくここには出ません。プロキシはほかの呼び出しと同じように確認しますが、最初からスナップショットで返すと決まっている呼び出しはどのサーバーにも届かないので、許可も拒否も記録されないからです。差し替えられた呼び出しを確認する場所は、実行のチャットの記録です。ツールのいずれかを差し替えた実行には**モック済み**のバッジが付きます。

実行自体にも**ライフサイクル**があります。`running` で始まり、タスクが 1 つ以上あって、そのすべてが終了状態(`completed` / `failed` / `skipped`)に達した時点で `completed` か `failed` になり、`finishedAt` のタイムスタンプが入ります。タスクに 1 つでも失敗があれば `failed` で終わります。この判定はタスクへの書き込みのたびに行われます。書き込みが実行エージェントからでも REST のタスクエンドポイントからでも同じです。記録された `finishedAt` があとからの編集で動くことはありません。タスクが 1 つもない実行は `running` のままです。これらのフィールドはサーバーが管理し、API から設定することはできません。[運用メトリクス](../operations/metrics.md)が数えるのもこれらです。
