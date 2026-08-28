---
title: 認証
sidebar_position: 2
---

# 認証

このアプリはサインインが必須です。ログアウト状態でどのページを開いても `/login` にリダイレクトされます。初回起動時は、初期投入された **`root`** ユーザー(プラットフォーム全体の `super_admin`。テナント欄は空のままにします)か、**Default** テナントに初期投入された **`admin`** ユーザー(テナント欄に `default` と入力します)でログインしてください。パスワードは初回起動より前に `ROOT_PASSWORD` と `ADMIN_PASSWORD` で設定します。未設定のままなら、ランダムに生成されたパスワードが `docker compose logs backend` に出力されます(それぞれ一度きりの出力で、あとから復元はできません)。ユーザーの追加は[管理画面](../guides/users-and-groups.md#users)から行います。サインインすると[ウェルカムページ](../guides/admin-ui.md#welcome-page)に着きます。

- **セッション** — ログインするとサーバー側にセッション(`auth_sessions` テーブル)が作られ、不透明なトークンを持つ HttpOnly の `a2flow_session` クッキーが設定されます(保存されるのはハッシュだけです)。セッションにはスライド式の**アイドルタイムアウト**があります(`SESSION_IDLE_TIMEOUT_SECONDS`、既定 8 時間)。
- **CSRF** — ログイン時に、JavaScript から読める `a2flow_csrf` クッキーも設定されます。フロントエンドは状態を変えるリクエストのたびに、この値を `X-CSRF-Token` ヘッダーに載せて返します(double-submit cookie 方式)。値が一致しなければバックエンドは `403` で拒否します。
- **同一オリジンのプロキシ** — ブラウザはフロントエンドのオリジン(`:3000`)を呼びます。フロントエンドのプロキシ(`frontend/src/proxy.ts`)が `/api/*` をバックエンド(`:8000`)へ転送するので、認証クッキーはファーストパーティになり、`SameSite=Lax` がそのまま働きます。転送先は `BACKEND_BASE_URL` で変えられます。

エンドポイントとクッキーの詳細は [backend/README.md](https://github.com/kaitoy/a2flow/blob/master/backend/README.md#authentication) にあります。
