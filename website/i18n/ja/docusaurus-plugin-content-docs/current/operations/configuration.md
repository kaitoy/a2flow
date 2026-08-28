---
title: 設定リファレンス
sidebar_position: 1
---

# 設定リファレンス

以下の設定はすべて、バックエンドが `backend/.env` から読む環境変数です。注釈つきのテンプレートは [backend/.env.example](https://github.com/kaitoy/a2flow/blob/master/backend/.env.example) にあります。モデルと API キーの設定は [LLM の設定](../getting-started/llm-configuration.md)に別ページとしてまとめてあります。

## サーバーの設定

```env
HOST=0.0.0.0
PORT=8000
# RELOAD=true
```

省略した場合の既定は `HOST=0.0.0.0` と `PORT=8000` です。`RELOAD`(既定 `false`)は uvicorn の自動リロードを有効にします。効くのは `python -m backend.main` だけで、[クイックスタート](../getting-started/quick-start.md)の `uv run uvicorn main:app --reload` や Dockerfile の起動経路は、どちらの値でも影響を受けません。

## 運用メトリクス

```env
# METRICS_TIMEZONE=Asia/Tokyo
```

ワークフローの運用メトリクスで暦日がどこから始まるかを決める IANA のタイムゾーン名です。`GET /api/v1/metrics` の「今日」の件数と、リードタイムの推移の日次バケットに効きます。既定は `UTC` です。認識できない名前は起動を止めず `UTC` にフォールバックするので、打ち間違いはアプリを止めるのではなくダッシュボードの日の境目をずらすだけで済みます。メトリクス自体は[運用メトリクス](./metrics.md)で説明しています。

## エージェントスキルストア {#agent-skill-store}

```env
SKILLS_DIR=.skills
# SKILLS_PRUNE_GRACE_SECONDS=3600
# SKILLS_CLONE_TIMEOUT_SECONDS=120
```

エージェントスキルのリポジトリをシャロークローンするストアのルートです。リビジョンごとに 1 つの不変ディレクトリという配置になります。

```
$SKILLS_DIR/<agent_skill_id>/<commit_sha>/
```

クローンは一時的な隣のディレクトリに用意し、1 回のアトミックな rename で公開します。そのため読み手が書きかけのリビジョンを見ることはありませんし、公開されたリビジョンが変更されることもありません。書き手(登録時のクローンと、すべての pull)は `infrastructure/locks.py` の `skill-sync:<id>` アドバイザリロックで直列化されます。読み手はロックを一切取りません。pull は隣にディレクトリを足すだけなので、既存のリビジョンを読み込んでいるエージェントを邪魔できないからです。

`SKILLS_PRUNE_GRACE_SECONDS`(既定 3600)は、何かから参照されているかどうかに関係なくリビジョンのディレクトリが残る時間です。pull は、どのワークフロー実行からも固定されていないリビジョンを削除します。この猶予時間は、実行がスキルの現在のリビジョンを読んでから、それを指す実行の行を挿入するまでの隙間をカバーします。

`SKILLS_CLONE_TIMEOUT_SECONDS`(既定 120)は、クローン中の個々の HTTP リクエストにかけられる時間の上限です。これがないと、遅い、あるいは応答しないリモートがクローンを無期限に止め、それと一緒にスキルの同期用アドバイザリロックも止めてしまいます。スキルは `pending` のまま残り、別のレプリカでの pull は待つのではなく黙って処理を飛ばすことになります。

既定は `backend/.skills`(作業ディレクトリからの相対)です。`docker compose` では `/var/lib/a2flow/skills` で、`skills` という名前つきボリュームに支えられます。

これは**キャッシュではなく永続的な状態**です。`WorkflowExecution` は開始時のリビジョンに固定されるので、このディレクトリを消すと、既存の実行は管理者がスキルをもう一度 pull するまでスキルを読み込めなくなります(HTTP 409 `SKILL_NOT_READY`)。バックエンドを 2 レプリカ以上で動かす場合は、すべてのレプリカがこの同じディレクトリをマウントする必要があります。

## シークレットの管理 {#secret-management}

```env
# SECRET_ENCRYPTION_KEY=
# SECRET_KEY_FILE=.secret_key
# VAULT_ADDR=https://vault.example.com
# VAULT_TOKEN=hvs.xxxxxxxx
# VAULT_ROLE_ID=...
# VAULT_SECRET_ID=...
# VAULT_APPROLE_MOUNT=approle
```

`local` タイプの[シークレット](../guides/secrets.md)は保存前に Fernet で暗号化されます。キーは最初の使用時に解決されます。`SECRET_ENCRYPTION_KEY`(有効な Fernet キーであること)が優先され、なければ `SECRET_KEY_FILE` のキーファイル(既定は SQLite のデータベースファイルの隣の `.secret_key`)を読み、それもなければキーを生成してそのファイルに保存し、WARNING をログに出します。キーはバックアップしてください。失うと保存済みのローカルシークレットはすべて復号できなくなります。

`vault` タイプのシークレットは、`VAULT_ADDR` で指定した 1 つの HashiCorp Vault(KV v2 のみ)からその場で読みます。認証は、設定されていれば AppRole(`VAULT_ROLE_ID` と `VAULT_SECRET_ID`。ログインのマウントは `VAULT_APPROLE_MOUNT`)を、なければ静的な `VAULT_TOKEN` を使います。`VAULT_ADDR` は、ユーザーが入力した URL に適用される SSRF のチェックを意図的に免除されています。運用者が設定するデプロイの構成であり、通常はプライベートアドレスを指すからです。

## アプリケーションのデータベース

```env
DB_URL=sqlite:///a2flow.db
# DB_URL=postgresql://user:password@localhost:5432/a2flow
```

REST API のデータと ADK のセッションストレージのためのデータベース URL です。どちらも同じデータベースに入ります。対応しているのは SQLite(既定。作業ディレクトリからの相対)と PostgreSQL です。非同期ドライバの接尾辞(`sqlite+aiosqlite` と `postgresql+asyncpg`)は自動で付くので、素のスキームで足ります。SQLite の場合 ADK のセッションストアは `SqliteSessionService` を使い、それ以外の URL では SQLAlchemy ベースの `DatabaseSessionService` に切り替わります。スキーマの変更はバージョン管理された [Alembic](https://alembic.sqlalchemy.org/) のマイグレーション(`alembic/versions/` 以下)として追跡し、起動時に自動適用します(`alembic upgrade head`)。つまりアプリを再デプロイすることがスキーマを最新にする操作です。モデルを変えたあとにマイグレーションを追加するには `uv run alembic revision --autogenerate -m "..."` を実行し、生成されたファイルを確認してからコミットしてください。

| テーブル | 説明 |
|---|---|
| `users` | アプリケーションのユーザー(`deleted_at` による論理削除。`roles` に付与されたロールが入ります)。[初期投入されるユーザー](./configuration.md#seeded-users)と[認可](../concepts/authorization.md)を参照 |
| `auth_sessions` | サーバー側のログインセッション(ハッシュ化したクッキーのトークンと CSRF トークン)。[認証](../concepts/authentication.md)を参照 |
| `impersonation_events` | なりすましセッションの監査証跡(`impersonator_id`、`target_user_id`、`started_at`、`ended_at`)。[認証](../concepts/authentication.md)を参照 |
| `agent_skills` | エージェントスキルの定義(プライベートリポジトリのクローン用に任意の `repo_auth_password` と `repo_auth_username` を含みます) |
| `mcp_servers` | 登録された MCP サーバー(名前、`transport`、続いてストリーマブル HTTP の URL とリクエストヘッダー、または stdio の command と args と env。ヘッダーと env の値には `${secret:NAME/KEY}` のプレースホルダーを埋め込めます) |
| `secrets` | 名前つきのキー/値の認証情報のまとまり。Fernet で暗号化したローカルの値の `entries` マップか、HashiCorp Vault の KV v2 パスへの参照です。[シークレット](../guides/secrets.md)を参照 |
| `workflows` | ワークフローの定義(名前、スキルへの参照、ライフサイクルの `status`、AI が要約した `generatedDescription`、ユーザーが編集できる `description`)に加えて、タスクテンプレートを設計する設計セッション(ADK のチャット)の `session_id` と、そのチャットが固定されている `agent_skill_commit_sha` |
| `workflow_task_templates` | ワークフローの、事前に設計されたタスク一覧(`workflow_id` の外部キーは `ON DELETE CASCADE`。依存の辺と MCP ツールの割り当ては専用の `workflow_task_template_*` 中間テーブルにあります) |
| `workflow_published_versions` | ワークフローごとに最大 1 行。公開時に凍結した名前、説明、タスクテンプレート(JSON)で、`modified` のワークフローはこれをもとに実行されます。[ワークフロー](../guides/workflows.md)を参照 |
| `workflow_executions` | ワークフローの実行 1 回につき 1 行。実行時点のワークフローとスキルのメタデータのスナップショットに加えて、実行が行われるワークフローセッション(ADK のチャット)の `session_id`(`workflow_id` の外部キーは `ON DELETE SET NULL` なので、実行は設計より長生きします) |
| `workflow_tasks` | `WorkflowExecution` に属する個々のタスク。実行時にテンプレートからコピーされます(`workflow_execution_id` の外部キーは `ON DELETE CASCADE`) |
| `workflow_task_tool_bindings` | タスクに割り当てられた MCP ツール(`task_id` の外部キーは `ON DELETE CASCADE`、`mcp_server_id` は `ON DELETE RESTRICT`) |
| `message_meta` | 共有される 2 つのセッションチャットの、メッセージごとの付帯情報。誰が送ったか(`sender_user_id`)と、どのタスクが進行中だったか(`workflow_task_id`。ワークフローセッションのみ)です。どちらのチャットも専用のテーブルを持たないので、行は `workflow_execution_id`(ワークフローセッション)か `workflow_id`(設計セッション)のちょうど一方で親を示します。`CHECK` がそれを強制し、どちらも削除時にカスケードします |
| `sessions` | セッションのメタデータとセッションレベルの状態 |
| `events` | セッションごとの全イベント履歴(JSON) |
| `app_states` | アプリケーションレベルの共有状態 |
| `user_states` | セッションをまたいで共有されるユーザーごとの状態 |

## 初期投入されるユーザー {#seeded-users}

起動時、バックエンドは隠しの**システムユーザー**に加えて実在の 2 アカウントを投入します。いずれも、対象のレコードが見つからなかった最初の起動でだけ作られます。

- **`super_admin`** ロールを持つ初期の **`root`** ユーザー([認可](../concepts/authorization.md)を参照)。プラットフォーム全体を対象とします(`tenantId: null`)。実在の(システム以外の)ユーザーが 1 人でもいれば飛ばされるので、実行されるのは本当に最初の起動のときだけです。
- **Default** テナント(`slug: default`)と、その中の **`admin`** ロールを持つ初期の **`admin`** ユーザー。テナント(`slug` で)とユーザー(そのテナント内の `username` で)は別々に確認するので、片方だけを重複なく作り直せます。

隠しの**システムユーザー**がブートストラップのレコードを所有します(ログインできず、ユーザー一覧からも除かれます)。

パスワードは環境変数から読みます。どちらにも、生成してログに一度だけ出す同じフォールバックがあります。

```env
ROOT_PASSWORD=change-me-now-123
ADMIN_PASSWORD=change-me-now-123
```

どちらかが未設定(または空)の場合は、そのユーザーの作成時にランダムなパスワードを生成し、`WARNING` レベルで**一度だけ**ログに出します。そのログ行が流れてしまうと復元できません。ローカルでの試用を超える用途では、初回起動より前に両方を明示的に設定するか、起動ログから生成されたパスワードをすぐ控えて、あとからユーザー API で変更してください。ユーザー名は `root` と `admin` に固定です。

## セッションの有効期間

セッションにはスライド式のアイドルタイムアウトがあります。認証済みのリクエストのたびにセッションの最終アクティブ時刻が更新され、`SESSION_IDLE_TIMEOUT_SECONDS`(既定 `28800`、8 時間)より長く放置されたセッションは拒否されて削除されます。クッキー自体はセッションクッキーなので(`Max-Age` も `Expires` もありません)、ブラウザを閉じたときにも消えます。

```env
# スライド式のアイドルタイムアウト(秒。既定 28800 = 8 時間)
SESSION_IDLE_TIMEOUT_SECONDS=28800
# クッキーに Secure を付ける(HTTPS のみ)。ローカルの HTTP 開発では false のまま(既定 false)
SESSION_COOKIE_SECURE=false
```

フロントエンドは同一オリジンの Next.js のリライト(`/api/*`)経由でバックエンドに届くので、クッキーはファーストパーティになり、`SameSite=Lax` がそのまま効きます。初回は初期投入された `root` か、Default テナントの `admin` でログインしてください([初期投入されるユーザー](./configuration.md#seeded-users)を参照)。

## CORS

```env
CORS_ORIGINS=http://localhost:3000
```

`/chat` と `/sessions` を呼べるオリジンをカンマ区切りで並べます。既定は `http://localhost:3000` です。フロントエンドを別のホストやポートから配信する場合はオリジンを追加します。

```env
CORS_ORIGINS=https://app.example.com,http://localhost:3000
```

`*` は起動時に拒否されます。`allow_credentials=True` を常に有効にしており、ワイルドカードのオリジンと組み合わせるのは CORS の仕様に反するためです。
