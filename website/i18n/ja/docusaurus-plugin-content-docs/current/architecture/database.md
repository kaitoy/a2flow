---
title: データベース
sidebar_position: 7
---

# データベース

永続化されるデータは、すべて `backend/.env` の `DB_URL` で選んだ 1 つのリレーショナルデータベースに入ります。

| 種類 | `DB_URL` | 備考 |
|---|---|---|
| SQLite(既定) | `sqlite:///a2flow.db` | 設定不要のローカルファイル |
| PostgreSQL | `postgresql://user:password@host:5432/a2flow` | Docker Compose 構成で使用 |

非同期ドライバの接尾辞(`aiosqlite` と `asyncpg`)は自動で付きます。スキーマの変更はバージョン管理された [Alembic](https://alembic.sqlalchemy.org/) のマイグレーションとして追跡し、起動時に自動適用します。アプリを再デプロイする(コンテナを再起動する)ことが未適用のマイグレーションを走らせる操作なので、別途マイグレーション手順を踏む必要はありません。

複数レプリカのバックエンドを協調させているのもこのデータベースです。エージェントの実行は、SSE ストリームが続くあいだ PostgreSQL のアドバイザリロックを保持します。そのため 1 つの会話が同時に 2 つのレプリカから動かされることはありません。これが何を守っているのか、そしてコネクションプールにどんな制約を課すのかは[水平スケーリング](../operations/scaling.md)を参照してください。

## 何が入っているか {#what-it-holds}

| テーブル | 内容 |
|---|---|
| `users` | アプリケーションのユーザーと、付与されたロール。[ユーザーとグループ](../guides/users-and-groups.md)を参照 |
| `auth_sessions` | サーバー側のログインセッション |
| `impersonation_events` | [代理ログイン](../concepts/impersonation.md)の監査証跡 |
| `agent_skills` | [Agent Skill](../guides/agent-skills.md) の定義と、クローン元のリポジトリ |
| `mcp_servers` | 登録済みの [MCP サーバー](../guides/mcp-servers.md)と、その接続方法 |
| `secrets` | 名前付きの[認証情報のまとまり](../guides/secrets.md)。ローカルで暗号化するか、Vault を参照します |
| `workflows` | [ワークフロー](../guides/workflows.md)の定義とライフサイクルの状態 |
| `workflow_task_templates` | ワークフローの、あらかじめ設計されたタスクの一覧 |
| `workflow_published_versions` | 公開時点で固めた設計。`modified` のワークフローはこれに対して実行されます |
| `workflow_executions` | [実行](../guides/workflow-executions.md)ごとに 1 行。実行時点のワークフローとスキルのメタデータのスナップショットつき |
| `workflow_tasks` | 実行が持つ個々のタスク。テンプレートからコピーされます |
| `workflow_task_tool_bindings` | タスクに紐づけられた MCP ツール |
| `message_meta` | 2 種類の共有チャットの、メッセージごとの情報。誰が送ったか、そのときどのタスクが進行中だったか |

ワークフローを削除するとテンプレートも一緒に消えますが、過去の実行は残ります。実行は設計の一部ではなく、何が起きたかの記録だからです。
