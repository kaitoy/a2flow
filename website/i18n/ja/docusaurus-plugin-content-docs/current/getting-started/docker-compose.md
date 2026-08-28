---
title: Docker Compose で動かす
sidebar_position: 2
---

# Docker Compose で動かす

個別に起動する代わりに、PostgreSQL 17、バックエンド、[メール送信ワーカー](../guides/notifications.md#the-delivery-queue)、フロントエンドをまとめて Docker Compose でビルドして起動することもできます([compose.yml](https://github.com/kaitoy/a2flow/blob/master/compose.yml))。

```bash
echo GOOGLE_API_KEY=your_google_api_key_here > .env
docker compose up --build
```

[http://localhost:3000](http://localhost:3000) を開きます。データベースの中身は `pgdata` ボリュームに残るので、再起動しても消えません。

フロントエンドをホスト側の別のポートで公開したい場合は、`.env` に `FRONTEND_PORT` を設定します(コンテナ内では 3000 のまま待ち受けます)。バックエンドの `CORS_ORIGINS` は自動的にそれに追従します。
