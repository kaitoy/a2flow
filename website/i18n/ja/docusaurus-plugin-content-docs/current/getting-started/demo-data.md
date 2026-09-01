---
title: デモデータ
sidebar_position: 4
---

# デモデータ

バックエンドで `DEMO_DATA=true` を設定すると、承認つきの「EC2 インスタンスを起動する」例に必要なものが一式、初期投入された **Default** テナントに登録されます。一つずつ手で登録しなくても、すぐに動かせるものが手元にある状態になります。[ワークフロー](../guides/workflows.md)自体はあえて登録しません。これらはワークフローを生成するための材料で、その手順が下の「試してみる」です。

## 有効にする

`backend/.env` にフラグを足してバックエンドを再起動します。[Docker Compose](./docker-compose.md) ならすでに有効です。`compose.yml` が `DEMO_DATA: ${DEMO_DATA:-true}` を設定しています。

```env
DEMO_DATA=true
DEMO_PASSWORD=change-me-now-123
DEMO_AWS_ACCESS_KEY_ID=AKIA...
DEMO_AWS_SECRET_ACCESS_KEY=...
DEMO_AWS_REGION=us-east-1
```

- `DEMO_PASSWORD` は 5 つのデモユーザーで共有され、`ROOT_PASSWORD` や `ADMIN_PASSWORD` と同じく、未設定なら生成してログに一度だけ出力します。参照されるのは、そのアカウントがまだ存在しないときだけです。
- AWS の認証情報は任意です。未設定なら `REPLACE_ME` というプレースホルダーが保存されるので、形としてはデモが揃った状態になり、実際の値は[シークレット](../guides/secrets.md)のページから入れられます。
- `DEMO_AWS_REGION` は、デモの MCP サーバーのツールが操作する対象のリージョンです。既定は `us-east-1` です。

⚠️ デモの MCP サーバーは読み取りだけでなく、**状態を変える** AWS の操作も実行できます。渡した認証情報の権限で実際のリソースを作成したり削除したりできてしまうので、使い捨てのアカウントか、権限を絞った IAM ポリシーを使ってください。AWS にまったく触れずにデモを試す方法は、下の[試してみる](#trying-it-out)を参照してください。

## 登録されるもの

- **[エージェントスキル](../guides/agent-skills.md) `Demo AWS EC2 Launch`** — インスタンスの構成を聞き取り、それについて管理職の明示的な承認を得てから、MCP ツールでインスタンスを起動します。リポジトリは起動後にバックグラウンドで clone するので、使えるようになるまでの間スキルは `pending` と表示されます。
- **[MCP サーバー](../guides/mcp-servers.md) `AWS MCP Server`** — AWS のマネージド AWS MCP Server に接続する `stdio` サーバーです。EC2 のツールはここから来ます。
- **[シークレット](../guides/secrets.md) `demo-aws-credentials`** — 上の MCP サーバーが読む、AWS のアクセスキー ID とシークレットアクセスキーです。
- **[ツールモック](../guides/tool-mocks.md)** — デモ実行で副作用のあるツールのスタブです。AWS MCP Server の `call_aws` と `run_script`(どちらも起動成功を返す)、および組み込みの `request_approval`(approved を返す)。ドラフト実行の **Run** ダイアログで選ぶと、AWS に触れることも管理職の承認を待つこともなく、ワークフローが最後まで動きます。
- **デモユーザーとグループ:**

| ユーザー | ロール | 役割 |
|---|---|---|
| `demo-developer` | `developer` | ワークフローを生成して公開する |
| `demo-requester-1`、`demo-requester-2` | `requester` | ワークフローを実行する |
| `demo-approver-1`、`demo-approver-2` | `approver` | 起動を承認する |

いずれもロールを直接は持ちません。それぞれ[ユーザーグループ](../guides/users-and-groups.md#user-groups) `Demo Developers`、`Demo Requesters`、`Demo Approvers` から継承します。

## 試してみる {#trying-it-out}

`DEMO_PASSWORD` を使い、次の順に各アカウントでサインインします。

1. **`demo-developer`** で[エージェントスキル](../guides/agent-skills.md)を開き、`Demo AWS EC2 Launch` の clone が終わるのを待ちます。終わるまで **Generate workflow** は押せません。
2. その行の **Generate workflow** から、起動したいインスタンスを説明し、デザインエージェントにタスクリストを作らせます([ワークフローを生成する](../guides/workflows.md#generating-a-workflow))。ワークフローは `draft` になります。
3. ワークフローの詳細ページで、生成されたタスクテンプレートを確認して **Publish** します。
4. **`demo-requester-1`** でワークフローの **Run** を押します([ワークフローを実行する](../guides/workflows.md#running-a-workflow))。実行のチャットが開き、エージェントがタスクを順に進めます。
5. スキルが承認を求めてきたら、**`demo-approver-1`** でサインインして承認します([承認](../guides/approvals.md))。エージェントはそのあと MCP ツールでインスタンスを起動します。

**AWS アカウントがない場合。** 手順 3 を飛ばし、`draft` のまま実行してください。`developer` である `demo-developer` はそれができ、[ツールモック](../guides/tool-mocks.md)を選べる Run ダイアログが出るのはドラフト実行のときだけです。**Mock tools** に並ぶ同梱のスタブ(起動用の `call_aws` または `run_script` と、`request_approval`)にチェックを入れれば、AWS に届くことも人の承認を待つこともなく、ワークフローが最後まで動きます。

## 削除する

`DEMO_DATA=false` にすると(または行を削除すると)、次の起動時にこれらのレコードが**削除されます**。どちらの方向にも宣言的に働くということです。

意図的に残るものが 2 つあります。ほかから依存されるようになったデモレコード(デモスキルの上に作られたワークフローなど)は、削除せずログに記録して残します。レコードを作成したデモユーザーは論理削除にとどめるので、そのレコード上で名前は引き続き解決できます。
