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

`.env` の `APP_PORT` を設定すると、アプリを別のホスト側ポートで公開します。アプリのベース URL も自動でそれに合わせられます。ホスト名など別のアドレスでアプリを開かせたいときは、代わりに `.env` の `APP_BASE_URL` にそのアドレス(例 `http://a2flow.internal:3000`)を設定します。アプリが公開されるのは引き続き `APP_PORT` なので、アドレスにポートを書くときは `APP_PORT` も同じ値にしてください。

## 起動するコンテナ {#what-comes-up}

| コンテナ | 役割 |
|---|---|
| **db** | PostgreSQL 17。A2Flow が記録するものはすべてここに入ります |
| **backend** | エージェントと API |
| **worker** | バックエンドが積んだ[通知メール](../guides/notifications.md#the-delivery-queue)を送ります |
| **mcp-proxy** | 登録した [MCP サーバー](../guides/mcp-servers.md)を実行します。分けている理由は[登録したサーバーが動く場所](../architecture/mcp-gateway-and-proxy.md#the-sandbox)を参照してください |
| **ingress** | ブラウザが話す入口。画面のリクエストはフロントエンドへ、API のリクエストはバックエンドへ直接送ります |
| **frontend** | 実際に操作する画面 |
| **caddy** | `compose.https.yml` を使ったときだけ起動します。[HTTPS で公開する](#https)を参照してください |
| **openbao** | `--profile openbao` を付けたときだけ起動します。[OpenBao で Vault 型シークレットを試す](#openbao)を参照してください |
| **keycloak** | `--profile keycloak` を付けたときだけ起動します。[Keycloak でシングルサインオンを試す](#keycloak)を参照してください |

外から到達できるのは ingress(`compose.https.yml` を使うときは代わりに Caddy、プロファイル指定時は OpenBao の UI と Keycloak も)だけで、残りは Docker の内部ネットワークでやり取りします。

初回の起動は 2 回目以降より時間がかかります。イメージのビルド、データベースのスキーマ作成に加えて、MCP プロキシがバックエンドから必要な証明書を受け取るまで待ってから受付を始めるためです。

## HTTPS で公開する {#https}

`compose.https.yml` を追加すると、ingress の前に [Caddy](https://caddyserver.com/) が置かれます。Caddy がポート 80 と 443 で唯一の入口になり、`APP_BASE_URL` のアドレスの証明書を取得して、平文の HTTP を HTTPS にリダイレクトします。アドレスが `https://` なら、サインインの Cookie も Secure になり、[シングルサインオン](../guides/single-sign-on.md)の **リダイレクト URI** もこのアドレスから作られます。

```bash
echo APP_BASE_URL=https://a2flow.example.com >> .env
docker compose -f compose.yml -f compose.https.yml up --build
```

設定したアドレスを開きます。アドレスにポートは書けません。公開されるのは 80 と 443 だけで、ポート付きのアドレスでは Caddy が起動しません。その後の動きはホスト名によって変わります。

| `APP_BASE_URL` | 証明書 | 始める前に |
|---|---|---|
| 公開されたホスト名(例 `https://a2flow.example.com`) | Let's Encrypt から取得し、自動で更新します | そのホスト名の DNS をこのホストに向け、ポート 80 と 443 にインターネットから到達できるようにします |
| 未設定(`https://localhost`) | Caddy が自分で作る認証局が発行します | 不要です。ただし、その認証局を信頼するまでブラウザが証明書の警告を出します(下記) |

ブラウザに `https://localhost` を信頼させるには、認証局のルート証明書を取り出して、OS かブラウザの信頼されたルート証明書に追加します。

```bash
docker compose -f compose.yml -f compose.https.yml cp caddy:/data/caddy/pki/authorities/local/root.crt .
```

証明書とローカルの認証局は `caddy-data` ボリュームに保存されます。このボリュームは消さないでください。消すと証明書が発行し直され、信頼済みのルート証明書とも合わなくなります。

## OpenBao で Vault 型シークレットを試す {#openbao}

[OpenBao](https://openbao.org/) はオープンソースの Vault フォークで、A2Flow からは HashiCorp Vault とまったく同じようにつなげます。この構成では A2Flow の隣で OpenBao を起動できるので、自前の Vault がなくても [Vault 型シークレット](../guides/secrets.md)を試せます。

```bash
docker compose --profile openbao up --build
```

OpenBao のデータは A2Flow と同じ PostgreSQL に保存されるので、再起動しても消えません。起動のたびに自動でアンシールもされます。アンシールに使う鍵は `openbao-unseal` ボリュームにあり、鍵がないとデータを読めないので、`pgdata` と一緒にバックアップしてください。この構成は連携を試すためのもので、本番向けではありません。

### 1. OpenBao を初期化する(初回のみ) {#1-initialize-openbao-first-start-only}

```bash
docker compose exec openbao bao operator init -recovery-shares=1 -recovery-threshold=1
```

表示される **Initial Root Token** を控えておきます。表示されるのはこの一度だけです。

### 2. A2Flow 用の AppRole を作る {#2-create-an-approle-for-a2flow}

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

### 3. OpenBao の UI でシークレットを作る {#3-create-a-secret-in-the-openbao-ui}

1. [http://localhost:8200/ui](http://localhost:8200/ui) を開き、**Token** 方式でルートトークンを使ってサインインします。ルートトークンでのサインインはページを再読み込みすると消えるので、URL を直接入力せず画面上のリンクをクリックして移動してください。
2. **secret/** エンジンを開き、**Create secret** を選びます。
3. パスに `a2flow/demo` を入れ、エントリ `username` と `password` を追加して保存します。

### 4. A2Flow からつなぐ {#4-connect-a2flow}

1. A2Flow に `root` でログインし、**システム設定**の**グローバル Vault のアドレス**に `http://openbao:8200` を設定して保存します。
2. **テナント**を開いて **Default** を選び、**グローバル Vault へのログイン**にチェックを入れます。**Vault の認証方式**に **AppRole** を選び、手順 2 の role id と secret id を入力して保存します。
3. `admin` でログインし、**シークレット**で種類が **HashiCorp Vault**、**Vault のマウント**が `secret`、**Vault のパス**が `a2flow/demo` のシークレットを作ります。

あとはほかのシークレットと同じように参照できます。たとえば [MCP サーバー](../guides/mcp-servers.md)の環境変数に `${secret:<名前>/password}` と書きます。シークレットを選ぶ画面では、そのキー `username` と `password` が一覧に出ます。これはその場で OpenBao から読んだものなので、表示されれば接続できています。

OpenBao の UI をホスト側の 8200 以外のポートで公開したい場合は、`.env` に `OPENBAO_PORT` を設定します。A2Flow 自身は常に内部ネットワーク上の `http://openbao:8200` でアクセスします。

## Keycloak でシングルサインオンを試す {#keycloak}

[Keycloak](https://www.keycloak.org/) はオープンソースの IdP です。この構成では A2Flow 向けに設定済みの Keycloak を A2Flow の隣で起動できるので、自前の IdP がなくても[シングルサインオン](../guides/single-sign-on.md)を試せます。

```bash
docker compose --profile keycloak up --build
```

Keycloak は [http://keycloak.localhost:8180](http://keycloak.localhost:8180) で公開され、管理コンソールには `admin` / `admin` でログインできます(パスワードは `.env` の `KEYCLOAK_ADMIN_PASSWORD` で変えられます)。Chrome、Edge、Firefox は `keycloak.localhost` を自動で見つけます。それ以外のブラウザでは、先に hosts ファイルへ `127.0.0.1 keycloak.localhost` の行を追加してください。Keycloak はコンテナを作り直すと何も残さず、下の設定から始め直します。管理コンソールで加えた変更は失われます。

起動時点で、次の設定が済んでいます。

| 項目 | 値 |
|---|---|
| レルム | `a2flow` |
| 発行者 URL | `http://keycloak.localhost:8180/realms/a2flow` |
| クライアント ID | `a2flow` |
| クライアントシークレット | `a2flow-dev-secret` |
| リダイレクト URI | `http://localhost:3000`(または `APP_BASE_URL`)と `https://localhost`。それぞれに A2Flow のコールバックのパスが続きます |
| グループクレーム | `groups` |
| ユーザー | `alice` はグループ `a2flow-admins`、`bob` はグループ `a2flow-users` に所属します。どちらもパスワードは `password` です |

### 1. A2Flow からつなぐ {#1-connect-a2flow}

1. A2Flow に `admin` でログインし、管理サイドバーの**テナント設定**を開きます。
2. **シングルサインオン**セクションで、上の表の値を**発行者 URL**、**クライアント ID**、**クライアントシークレット**に入力し、**シングルサインオンを有効にする**にチェックを入れて保存します。
3. **ユーザーグループ**を開き、付けたいロールを持つグループを開くか新しく作って、**IdP グループ**に `a2flow-admins` を入力して保存します。

### 2. ログインする {#2-sign-in}

1. ログアウトします。ログイン画面の**テナント**に `default` を入力し、**SSO でログイン**を押します。
2. Keycloak のログイン画面で `alice` / `password` でログインします。手順 1 のグループのメンバーとして、Alice で A2Flow にログインした状態で戻ってきます。
3. `bob` も試してみてください。所属グループ `a2flow-users` はどのユーザーグループにも割り当てられていないので、ログインは拒否されます。どれかのユーザーグループに割り当てれば通るようになります。

Keycloak は SAML にも対応していますが、A2Flow のログインは OpenID Connect だけを使います。
