---
title: データベース
sidebar_position: 2
---

# データベース

永続化されるデータ、つまり REST API のレコードと ADK のセッションストレージは、すべて `backend/.env` の `DB_URL` で選んだ 1 つのリレーショナルデータベースに入ります。

| 種類 | `DB_URL` | 備考 |
|---|---|---|
| SQLite(既定) | `sqlite:///a2flow.db` | 設定不要のローカルファイル |
| PostgreSQL | `postgresql://user:password@host:5432/a2flow` | Docker Compose 構成で使用 |

非同期ドライバの接尾辞(`aiosqlite` と `asyncpg`)は自動で付きます。スキーマの変更はバージョン管理された [Alembic](https://alembic.sqlalchemy.org/) のマイグレーション(`backend/alembic/versions/`)として追跡し、起動時に自動適用します。アプリを再デプロイする(コンテナを再起動する)ことが未適用のマイグレーションを走らせる操作なので、別途マイグレーション手順を踏む必要はありません。

複数レプリカのバックエンドを協調させているのもこのデータベースです。エージェントの実行は、SSE ストリームが続くあいだ ADK セッションに対して PostgreSQL のアドバイザリロックを保持します。そのため 1 つの会話が同時に 2 つのレプリカから動かされることはありません。これが何を守っているのか、そしてコネクションプールにどんな制約を課すのかは[水平スケーリング](../operations/scaling.md)を参照してください。
