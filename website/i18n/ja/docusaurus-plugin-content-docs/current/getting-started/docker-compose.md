---
title: Docker Compose で動かす
sidebar_position: 2
---

# Docker Compose で動かす

個別に起動する代わりに、一式まとめて Docker Compose でビルドして起動することもできます([compose.yml](https://github.com/kaitoy/a2flow/blob/master/compose.yml))。

```bash
echo GOOGLE_API_KEY=your_google_api_key_here > .env
docker compose up --build
```

[http://localhost:3000](http://localhost:3000) を開きます。データベースの中身は `pgdata` ボリュームに残るので、再起動しても消えません。

フロントエンドをホスト側の別のポートで公開したい場合は、`.env` に `FRONTEND_PORT` を設定します(コンテナ内では 3000 のまま待ち受けます)。バックエンドの `CORS_ORIGINS` は自動的にそれに追従します。

## 起動するコンテナ

| コンテナ | 役割 |
|---|---|
| **db** | PostgreSQL 17。A2Flow が記録するものはすべてここに入ります |
| **backend** | エージェントと API |
| **worker** | バックエンドが積んだ[通知メール](../guides/notifications.md#the-delivery-queue)を送ります |
| **mcp-proxy** | 登録した [MCP サーバ](../guides/mcp-servers.md)を実行します。分けている理由は[サンドボックス](../architecture/mcp-proxy.md#the-sandbox)を参照してください |
| **frontend** | 実際に操作する画面 |

外から到達できるのはフロントエンドだけで、残りは Docker の内部ネットワークでやり取りします。

初回の起動は 2 回目以降より時間がかかります。イメージのビルド、データベースのスキーマ作成に加えて、MCP プロキシがバックエンドから必要な証明書を受け取るまで待ってから受付を始めるためです。
