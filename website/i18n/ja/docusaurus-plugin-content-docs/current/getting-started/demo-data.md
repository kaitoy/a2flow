---
title: デモデータ
sidebar_position: 4
---

# デモデータ

バックエンドで `DEMO_DATA=true` を設定すると、承認つきで状態を変える 2 つの例 — 「EC2 インスタンスを起動する」例と「GKE の Pod を再起動する」例 — に必要なものが一式、初期投入された **Default** テナントに登録されます。一つずつ手で登録しなくても、すぐに動かせるものが手元にある状態になります。[ワークフロー](../guides/workflows.md)自体はあえて登録しません。これらはワークフローを生成するための材料で、その手順が下の「試してみる」です。

## 有効にする

`backend/.env` にフラグを足してバックエンドを再起動します。[Docker Compose](./docker-compose.md) ならすでに有効です。`compose.yml` が `DEMO_DATA: ${DEMO_DATA:-true}` を設定しています。

```env
DEMO_DATA=true
DEMO_PASSWORD=change-me-now-123
DEMO_AWS_ACCESS_KEY_ID=AKIA...
DEMO_AWS_SECRET_ACCESS_KEY=...
DEMO_AWS_REGION=us-east-1
DEMO_GCP_CREDENTIALS_JSON='{"type":"service_account",...}'
```

- `DEMO_PASSWORD` は 8 つのデモユーザーで共有され、`ROOT_PASSWORD` や `ADMIN_PASSWORD` と同じく、未設定なら生成してログに一度だけ出力します。参照されるのは、そのアカウントがまだ存在しないときだけです。
- AWS の認証情報と Google Cloud の認証情報は任意です。未設定なら `REPLACE_ME` というプレースホルダーが保存されるので、形としてはデモが揃った状態になり、実際の値は[シークレット](../guides/secrets.md)のページから入れられます。
- `DEMO_AWS_REGION` は、デモの AWS MCP サーバーのツールが操作する対象のリージョンです。既定は `us-east-1` です。
- `DEMO_GCP_CREDENTIALS_JSON` は Google Cloud の認証情報 JSON を 1 行にしたものです。サービスアカウントの鍵か、OAuth クライアント ID とシークレットで一度サインインしたあとに `gcloud` が書き出す authorized-user JSON のどちらかを入れます。GKE MCP サーバーはここからアクセストークンを発行します。Google の MCP サーバーは API キーを受け付けません。入手方法は [Google Cloud の MCP サーバー](../guides/mcp-servers.md#google-cloud-mcp-servers)を参照してください。

⚠️ どちらのデモ MCP サーバーも読み取りだけでなく、**状態を変える**操作を実行できます。AWS MCP サーバーの認証情報は実際の AWS リソースを作成・削除でき、GKE MCP サーバーの身元は実際のクラスタでワークロードのローリング再起動や Pod の削除を行えます。どちらも使い捨てのアカウントか、権限を絞った認証情報を使ってください。実際のプロバイダにまったく触れずにデモを試す方法は、下の[試してみる](#trying-it-out)を参照してください。

## 登録されるもの

- **[エージェントスキル](../guides/agent-skills.md) `Demo AWS EC2 Launch`** — インスタンスの構成を聞き取り、それについて管理職の明示的な承認を得てから、MCP ツールでインスタンスを起動します。リポジトリは起動後にバックグラウンドで clone するので、使えるようになるまでの間スキルは `pending` と表示されます。
- **[エージェントスキル](../guides/agent-skills.md) `Demo GKE Pod Restart`** — 対象(プロジェクト・クラスタ・namespace・そして Deployment/StatefulSet 名か単一の Pod 名のいずれか)をユーザーと合意し、その対象について管理職の明示的な承認を得てから、既定では GKE MCP Server でワークロードをローリング再起動し、ユーザーが1つの Pod だけを望む場合はその Pod を削除して所有コントローラーに再作成させ、結果を報告します。リポジトリの clone も同じ仕組みなので、最初は同様に `pending` と表示されます。
- **[MCP サーバー](../guides/mcp-servers.md) `AWS MCP Server`** — AWS のマネージド AWS MCP Server に接続する `stdio` サーバーです。EC2 のツールはここから来ます。
- **[MCP サーバー](../guides/mcp-servers.md) `GKE MCP Server`** — Google Cloud のマネージド GKE(Google Kubernetes Engine)MCP サーバーのフルエンドポイントに接続する `streamable_http` サーバーです。`Authorization` ヘッダーは `Bearer ${gcp-token:demo-gcp-credentials/GOOGLE_CREDENTIALS_JSON}` なので、接続のたびに `demo-gcp-credentials` シークレットから発行したばかりのアクセストークンを送ります。ツールはクラスタや Kubernetes リソースを管理でき、ワークロードのローリング再起動や Pod の削除も含まれます。
- **[シークレット](../guides/secrets.md) `demo-aws-credentials`** — AWS MCP Server が読む、AWS のアクセスキー ID とシークレットアクセスキーです。
- **[シークレット](../guides/secrets.md) `demo-gcp-credentials`** — GKE MCP Server がアクセストークンを発行する元になる、Google Cloud の認証情報 JSON です。
- **[ツールモック](../guides/tool-mocks.md)** — デモ実行で副作用のあるツールのスタブです。AWS MCP Server の `aws___call_aws` と `aws___run_script`(どちらも起動成功を返す)、GKE MCP Server の `patch_k8s_resource`(ローリング再起動成功を返す)と `delete_k8s_resource`(Pod 削除成功を返す)、および組み込みの `request_approval`(approved を返す)。ドラフト実行の **Run** ダイアログで選ぶと、AWS や実際の GKE クラスタに触れることも管理職の承認を待つこともなく、どちらのワークフローも最後まで動きます。
- **[タグ](../guides/tags.md)** `AWS` と `GCP` — それぞれ[アクセス制御タグ](../guides/tags.md#access-control-tags)です。`Demo AWS Group`/`Demo GCP Group` のメンバー(および `admin`、スーパー管理者)以外には、AWS または GCP のタグが付いた上記のレコードは見えません。`Approval Required` は両方のエージェントスキルに付く普通のタグで、何も制限しません。
- **デモユーザーとグループ:**

| ユーザー | ロール | アクセス制御グループ | 役割 |
|---|---|---|---|
| `demo-aws-developer` | `developer` | `Demo AWS Group` | EC2 起動ワークフローを生成する |
| `demo-aws-reviewer` | `reviewer` | `Demo AWS Group` | EC2 起動ワークフローを公開する |
| `demo-aws-requester` | `requester` | `Demo AWS Group` | EC2 起動ワークフローを実行する |
| `demo-gcp-developer` | `developer` | `Demo GCP Group` | GKE Pod 再起動ワークフローを生成する |
| `demo-gcp-reviewer` | `reviewer` | `Demo GCP Group` | GKE Pod 再起動ワークフローを公開する |
| `demo-gcp-requester` | `requester` | `Demo GCP Group` | GKE Pod 再起動ワークフローを実行する |
| `demo-approver-1`、`demo-approver-2` | `approver` | `Demo Approvers`(両方のタグ) | 起動、または Pod の再起動を承認する |

いずれもロールを直接は持ちません。それぞれ[ユーザーグループ](../guides/users-and-groups.md#user-groups) `Demo Developers`、`Demo Reviewers`、`Demo Requesters`、`Demo Approvers` から継承します。AWS と GCP の3人組はそれぞれ、もう一つのグループ `Demo AWS Group` または `Demo GCP Group` にも所属します。このグループはロールを一切付与せず、対応するアクセス制御タグを保持するためだけに存在するので、その3人組だけが AWS または GCP のタグ付きレコードを見られ、それ以外には見えません。ただし `admin`(またはスーパー管理者)は例外で、[アクセス制御タグを完全に素通り](../guides/tags.md#access-control-tags)するため、グループに所属する必要すらありません。`Demo Approvers` 自体は `AWS` と `GCP` 両方のアクセス制御タグを直接持ちます。承認者は特定のプロバイダに縛られる立場ではないためで、これによりどちらのデモワークフローから来た承認依頼でも、デモ承認者のどちらかを宛先にできます。

## 試してみる {#trying-it-out}

`DEMO_PASSWORD` を使い、次の順に各アカウントでサインインします。

1. **`demo-aws-developer`** で[エージェントスキル](../guides/agent-skills.md)を開き、`Demo AWS EC2 Launch` の clone が終わるのを待ちます。終わるまで **Generate workflow** は押せません。
2. その行の **Generate workflow** から、起動したいインスタンスを説明し、デザインエージェントにタスクリストを作らせます([ワークフローを生成する](../guides/workflows.md#generating-a-workflow))。ワークフローは `draft` になります。
3. **`demo-aws-reviewer`** でサインインし直し、ワークフローの詳細ページで生成されたタスクテンプレートを確認して **Publish** します。
4. **`demo-aws-requester`** でワークフローの **Run** を押します([ワークフローを実行する](../guides/workflows.md#running-a-workflow))。実行のチャットが開き、エージェントがタスクを順に進めます。
5. スキルが承認を求めてきたら、**`demo-approver-1`** でサインインして承認します([承認](../guides/approvals.md))。エージェントはそのあと MCP ツールでインスタンスを起動します。

同じ 5 ステップは **`Demo GKE Pod Restart`** でも、**`demo-gcp-developer`**、**`demo-gcp-reviewer`**、**`demo-gcp-requester`** でサインインすれば実行できます。`Demo AWS Group` と `Demo GCP Group` はそれぞれ自分のプロバイダのレコードしか見えないため、`demo-aws-developer` は `Demo GKE Pod Restart` を開けず、`demo-gcp-developer` は `Demo AWS EC2 Launch` を開けません。承認は起動ではなく、再起動するワークロード(または、単一の Pod だけを望む場合はその Pod)そのものを対象にし、最後のステップは何かを作る代わりにワークロードのローリング再起動を実行します。`Demo Approvers` は `AWS` と `GCP` 両方のアクセス制御タグを直接持っているので、承認のルーティングは AWS/GCP のグループ分けの影響を受けず、どちらの承認者アカウントでも構いません。ここで実際に動かすには、実際の GKE クラスタに届く権限を持つ身元の認証情報を `DEMO_GCP_CREDENTIALS_JSON` に設定しておく必要があります。

**AWS アカウントも GKE クラスタもない場合。** 手順 3 を飛ばし、`draft` のまま実行してください。`developer` である `demo-aws-developer`(GKE の例なら `demo-gcp-developer`)はそれができ、[ツールモック](../guides/tool-mocks.md)を選べる Run ダイアログが出るのはドラフト実行のときだけです。**Mock tools** に並ぶ同梱のスタブ(起動用の `aws___call_aws` または `aws___run_script`、Pod 再起動用の `patch_k8s_resource` または `delete_k8s_resource`、`request_approval`)にチェックを入れれば、AWS や実際の GKE クラスタに届くことも人の承認を待つこともなく、ワークフローが最後まで動きます。

## 削除する

`DEMO_DATA=false` にすると(または行を削除すると)、次の起動時にこれらのレコードが**削除されます**。どちらの方向にも宣言的に働くということです。

意図的に残るものが 2 つあります。ほかから依存されるようになったデモレコード(デモスキルの上に作られたワークフローなど)は、削除せずログに記録して残します。レコードを作成したデモユーザーは論理削除にとどめるので、そのレコード上で名前は引き続き解決できます。
