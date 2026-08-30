---
title: バックアップと復旧
sidebar_position: 4
---

# バックアップと復旧

コンテナが失われても残さなければならないものは[3 つ](./deployment.md#state-that-has-to-persist)です。それ以外(登録済みの MCP サーバー、ワークフロー、ユーザー、システム設定)はすべてデータベースの行なので、データベースを取れば一緒に守られます。

| 対象 | 取り方 | 戻し方 |
|---|---|---|
| データベース | `pg_dump`、または SQLite ファイルのコピー | `pg_restore`、またはファイルを戻す |
| エージェントスキルストア | `SKILLS_DIR` のツリーのコピー | 元の場所に展開する |
| シークレット暗号化キー | `SECRET_ENCRYPTION_KEY` の値、または `SECRET_KEY_FILE` のファイル | 同じ値を設定する、または同じファイルを戻す |

**データベースとキーは必ず対で戻してください。** このキーはローカルシークレットと、承認 CA の署名キーの両方を復号します。どちらもデータベースに入っています。違うキーの隣に戻したデータベースは、シークレットがすべて読めない状態で立ち上がります。

## データベース {#the-database}

PostgreSQL の場合です。

```bash
pg_dump --format=custom --file=a2flow-$(date +%F).dump "postgresql://user:password@host:5432/a2flow"
pg_restore --clean --if-exists --dbname="postgresql://user:password@host:5432/a2flow" a2flow-2026-01-31.dump
```

Docker Compose では `db` サービスに直接届きます。

```bash
docker compose exec -T db pg_dump -U a2flow -Fc a2flow > a2flow-$(date +%F).dump
docker compose exec -T db pg_restore -U a2flow -d a2flow --clean --if-exists < a2flow-2026-01-31.dump
```

SQLite は `DB_URL` のパスにある 1 つのファイルです。アプリの稼働中はコピーではなく `sqlite3 a2flow.db ".backup out.db"` を使ってください。

戻したデータベースにマイグレーションの手順は要りません。バックエンドは起動時に未適用の [Alembic](https://alembic.sqlalchemy.org/) マイグレーションを適用するので、古いダンプを新しいビルドの下に戻して起動すればスキーマは前に進みます。

## エージェントスキルストア {#the-agent-skill-store}

`SKILLS_DIR` はスキルを登録し直しても再構成できません。スキルの取得はリポジトリの*現在の* HEAD をクローンするので、古いリビジョンに固定された実行はそのリビジョンを取り戻せず、スキルを読み込めないままになります。ディレクトリをバックアップしてください。

公開済みのリビジョンのディレクトリはあとから変更されないので、アプリの稼働中に取ったコピーでも整合します。

```bash
tar -czf skills-$(date +%F).tgz -C /var/lib/a2flow/skills .
```

Docker Compose ではストアは `skills` という名前付きボリュームです。

```bash
docker run --rm -v a2flow_skills:/skills -v "$PWD:/backup" alpine \
  tar -czf /backup/skills-$(date +%F).tgz -C /skills .
```

戻すときは、空のストアにアーカイブを展開してからバックエンドを起動します。

## シークレット暗号化キー {#the-secret-encryption-key}

`SECRET_ENCRYPTION_KEY` を明示的に設定しているなら、キーはすでにデプロイ設定を置いている場所にあり、ここで追加の作業は要りません。その保管場所自体がバックアップされていることだけ確認してください。

設定していない場合、バックエンドが最初の使用時に生成し、`SECRET_KEY_FILE` のファイル(既定は `.secret_key`。SQLite のデータベースファイルの隣)に書いています。このファイルが唯一の複製です。それが載っているマシン以外の場所にバックアップし、認証情報として扱ってください。

キーのローテーションには対応していません。既存のシークレットは古いキーで暗号化されているからです。[シークレットの管理](./configuration.md#secret-management)を参照してください。

## 復旧の確認 {#checking-a-restore}

1. バックエンドを起動し、[`GET /api/v1/health`](./health.md) が 200 を返すことを確認します。データベースに到達でき、スキーマが最新であることの証拠になります。
2. 管理 UI で `local` タイプの[シークレット](../guides/secrets.md)を開きます。エラーにならず開けることが、キーとデータベースが対応していることの証拠になります。
3. 進行中だった[ワークフロー実行](../guides/workflow-executions.md)を開きます。`SKILL_NOT_READY` にならず再開できることが、使用中のリビジョンごとスキルストアが戻っていることの証拠になります。
