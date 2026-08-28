---
title: MCP サーバー
sidebar_position: 7
---

# MCP サーバー

[http://localhost:3000/admin/mcp-servers](http://localhost:3000/admin/mcp-servers) で [MCP](https://modelcontextprotocol.io/) サーバーのレジストリを管理します。ここに登録したサーバーのツールを、ワークフローエージェントが WorkflowTask に割り当てられるようになります([タスクが使う MCP ツール](./workflows.md#mcp-tools-for-tasks)を参照)。

| 操作 | パス |
|-----------|------|
| サーバーの一覧 | `GET /admin/mcp-servers` |
| サーバーの新規登録 | `GET /admin/mcp-servers/new` |
| サーバーの詳細ページ(編集・削除) | `GET /admin/mcp-servers/{id}` |

各レコードには一意な名前、分類に使う[タグ](./tags.md)、そして**トランスポート**が入ります。フォームの残りはトランスポートで決まります。

| トランスポート | フィールド | 備考 |
|---|---|---|
| **ストリーマブル HTTP**(既定) | `url`、`headers` | リモートのサーバーです。SSE のみのサーバーには対応していません。ヘッダーはリクエストごとに送られます。通常は `Authorization: Bearer …` です。 |
| **stdio** | `command`、`args`、`env` | バックエンドの子プロセスとして起動するサーバーです。たとえば `npx` に `["-y", "@modelcontextprotocol/server-everything"]` を渡します。バックエンドのイメージには `npx`(Node.js 22)と `uvx` の両方が入っています。 |

⚠️ ヘッダーや環境変数にそのまま書いた値は、`a2flow.db` に**平文で**保存され、API からも返ります。認証情報を直接埋め込む代わりに、登録済みの[シークレット](./secrets.md)のエントリを `${secret:name/key}` のプレースホルダー構文で参照してください(たとえば `Authorization: Bearer ${secret:github/token}` や `AWS_ACCESS_KEY_ID: ${secret:aws-credentials/AWS_ACCESS_KEY_ID}`)。プレースホルダーが展開されるのは接続時だけなので、認証情報が保存されたレコードや API のレスポンスに現れることはありません。

⚠️ stdio サーバーを登録するということは、**指定したコマンドをバックエンドのコンテナ内で実行する**ということです。実行者はコンテナの非特権ユーザー `app` です。この操作は MCP サーバーへのほかの書き込みと同じ `developer` ロールで守られています。`args` はリストとしてプロセスに渡され、シェルを経由することはありません。子プロセスが引き継ぐ環境変数は、MCP SDK が許す小さな安全集合(`PATH`、`HOME` など)に、設定した `env` を加えたものだけです。バックエンド自身の API キーや `DB_URL` は見えません。

`args` の要素からは、同じサーバー自身の `env` を `${env:NAME}` という名前で参照することもできます。展開は `env` 側の `${secret:…}` の展開より後です。そのため `--token ${env:API_KEY}` のように、シークレット由来の `env` の値を CLI のフラグとして再利用できます。プロセスの環境変数からではなく引数として値を受け取るランチャー向けです。`NAME` は `env` のキーでなければならず、保存時に確認されます(作成時と、どちらかのフィールドを変える PATCH の両方です)。参照先の `env` キーを消して古い参照が残った場合も、同じように拒否されます。

既存のサーバーのトランスポートを切り替えると、もう一方のトランスポートのフィールドは消えます。2 つの形を混ぜたリクエスト(stdio サーバーに URL、リモートサーバーに command)は HTTP 422(`INVALID_MCP_SERVER`)で拒否されます。

一覧ページの**レジストリを見る**ボタンは、公式の [MCP レジストリ](https://registry.modelcontextprotocol.io/)(`GET /api/v1/mcp-registry`)を使った検索ダイアログを開きます。名前でサーバーを検索し、A2Flow が登録できるものだけを並べます。ストリーマブル HTTP のリモートを持つサーバーと、npm または PyPI のパッケージとして公開されていて stdio で起動できるサーバーです(OCI と NuGet のパッケージは対象外です)。結果を選ぶと、接続情報と必要なヘッダーや環境変数のキーが埋まった作成フォームが開くので、保存前にシークレットの値を入れるだけで済みます。パッケージからコマンドへの対応付けはベストエフォートなので、保存前に確認してください。レジストリのベース URL は `MCP_REGISTRY_URL` 環境変数で変更できます。レジストリに到達できない場合は HTTP 502(`REGISTRY_UNREACHABLE`)になります。

`GET /api/v1/mcp-servers/{id}/tools` は稼働中のサーバーに問い合わせ、公開されているツール(名前、説明、入力スキーマ)を返します。管理画面のタスクのフォームは、操作者が選んだ 1 つのサーバーについてだけこれを呼び、レジストリ全体に一度に問い合わせることはありません。到達も起動もできないサーバーは HTTP 502(`MCP_UNREACHABLE`)になります。WorkflowTask のツール割り当てから参照されているサーバーは削除できません(HTTP 409 `CONFLICT_REFERENCED`)。
