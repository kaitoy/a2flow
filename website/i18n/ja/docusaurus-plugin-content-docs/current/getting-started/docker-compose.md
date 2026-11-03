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
| **mcp-proxy** | 登録した [MCP サーバ](../guides/mcp-servers.md)を実行します。分けている理由は[登録したサーバーが動く場所](../architecture/mcp-gateway-and-proxy.md#the-sandbox)を参照してください |
| **frontend** | 実際に操作する画面 |
| **openbao** | `--profile openbao` を付けたときだけ起動します。[OpenBao で Vault 型シークレットを試す](#openbao)を参照してください |

外から到達できるのはフロントエンド(プロファイル指定時は OpenBao の UI も)だけで、残りは Docker の内部ネットワークでやり取りします。

初回の起動は 2 回目以降より時間がかかります。イメージのビルド、データベースのスキーマ作成に加えて、MCP プロキシがバックエンドから必要な証明書を受け取るまで待ってから受付を始めるためです。

## OpenBao で Vault 型シークレットを試す {#openbao}

[OpenBao](https://openbao.org/) はオープンソースの Vault フォークで、A2Flow からは HashiCorp Vault とまったく同じようにつなげます。この構成では A2Flow の隣で OpenBao を起動できるので、自前の Vault がなくても [Vault 型シークレット](../guides/secrets.md)を試せます。

```bash
docker compose --profile openbao up --build
```

OpenBao のデータは A2Flow と同じ PostgreSQL に保存されるので、再起動しても消えません。起動のたびに自動でアンシールもされます。アンシールに使う鍵は `openbao-unseal` ボリュームにあり、鍵がないとデータを読めないので、`pgdata` と一緒にバックアップしてください。この構成は連携を試すためのもので、本番向けではありません。

### 1. OpenBao を初期化する(初回のみ)

```bash
docker compose exec openbao bao operator init -recovery-shares=1 -recovery-threshold=1
```

表示される **Initial Root Token** を控えておきます。表示されるのはこの一度だけです。

### 2. A2Flow 用の AppRole を作る

AppRole のロールは UI からは作れないので、ここはコマンドラインで行います。`<root-token>` は手順 1 のトークンに置き換えてください。

```bash
docker compose exec -e BAO_TOKEN=<root-token> openbao sh -c '
  bao secrets enable -path=secret kv-v2
  bao auth enable approle
  printf "path \"secret/data/a2flow/*\" { capabilities = [\"read\"] }" | bao policy write a2flow -
  bao write auth/approle/role/a2flow token_policies=a2flow token_ttl=1h
  bao read -field=role_id auth/approle/role/a2flow/role-id; echo
  bao write -f -field=secret_id auth/approle/role/a2flow/secret-id; echo'
```

最後の 2 行で **role id** と **secret id** が表示されます。このポリシーで A2Flow が読めるのは `a2flow/` 以下のパスだけです。

### 3. OpenBao の UI でシークレットを作る

1. [http://localhost:8200/ui](http://localhost:8200/ui) を開き、**Token** 方式でルートトークンを使ってサインインします。ルートトークンでのサインインはページを再読み込みすると消えるので、URL を直接入力せず画面上のリンクをクリックして移動してください。
2. **secret/** エンジンを開き、**Create secret** を選びます。
3. パスに `a2flow/demo` を入れ、エントリ `username` と `password` を追加して保存します。

### 4. A2Flow からつなぐ

1. A2Flow に `root` でサインインし、**System Settings** の **Global Vault Address** に `http://openbao:8200` を設定して保存します。
2. **Tenants** を開いて **Default** を選び、**Log in to the global Vault** にチェックを入れます。**Vault Auth Method** に **AppRole** を選び、手順 2 の role id と secret id を入力して保存します。
3. `admin` でサインインし、**Secrets** で種類が **HashiCorp Vault**、**Vault Mount** が `secret`、**Vault Path** が `a2flow/demo` のシークレットを作ります。

あとはほかのシークレットと同じように参照できます。たとえば [MCP サーバー](../guides/mcp-servers.md)の環境変数に `${secret:<名前>/password}` と書きます。シークレットを選ぶ画面では、そのキー `username` と `password` が一覧に出ます。これはその場で OpenBao から読んだものなので、表示されれば接続できています。

OpenBao の UI をホスト側の 8200 以外のポートで公開したい場合は、`.env` に `OPENBAO_PORT` を設定します。A2Flow 自身は常に内部ネットワーク上の `http://openbao:8200` でアクセスします。
