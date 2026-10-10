---
title: デモデータ
sidebar_position: 4
---

# デモデータ

バックエンドで `DEMO_DATA=true` を設定すると、承認つきで状態を変える 3 つの例 — 「EC2 インスタンスを起動する」例、「GKE の Pod を再起動する」例、「Azure Key Vault のシークレットをローテーションする」例 — に必要なものが一式、初期投入された **Default** テナントに登録されます。一つずつ手で登録しなくても、すぐに動かせるものが手元にある状態になります。[ワークフロー](../guides/workflows.md)自体はあえて登録しません。これらはワークフローを生成するための材料で、実際に生成するところからの手順が[ウォークスルー](./walkthrough.mdx)です。

## 有効にする

`backend/.env` にフラグを足してバックエンドを再起動します。[Docker Compose](./docker-compose.md) ならすでに有効です。`compose.yml` が `DEMO_DATA: ${DEMO_DATA:-true}` を設定しています。

```env
DEMO_DATA=true
DEMO_PASSWORD=change-me-now-123
DEMO_AWS_ACCESS_KEY_ID=AKIA...
DEMO_AWS_SECRET_ACCESS_KEY=...
DEMO_AWS_REGION=us-east-1
DEMO_GCP_CREDENTIALS_JSON='{"type":"service_account",...}'
DEMO_AZURE_TENANT_ID=...
DEMO_AZURE_CLIENT_ID=...
DEMO_AZURE_CLIENT_SECRET=...
```

- `DEMO_PASSWORD` は 11 のデモユーザーで共有され、`ROOT_PASSWORD` や `ADMIN_PASSWORD` と同じく、未設定なら生成してログに一度だけ出力します。参照されるのは、そのアカウントがまだ存在しないときだけです。
- AWS、Google Cloud、Azure の認証情報はいずれも任意です。未設定なら `REPLACE_ME` というプレースホルダーが保存されるので、形としてはデモが揃った状態になり、実際の値は[シークレット](../guides/secrets.md)のページから入れられます。
- `DEMO_AWS_REGION` は、デモの AWS MCP サーバーのツールが操作する対象のリージョンです。既定は `us-east-1` です。
- `DEMO_GCP_CREDENTIALS_JSON` は Google Cloud の認証情報 JSON を 1 行にしたものです。サービスアカウントの鍵か、OAuth クライアント ID とシークレットで一度サインインしたあとに `gcloud` が書き出す authorized-user JSON のどちらかを入れます。GKE MCP サーバーはここからアクセストークンを発行します。Google の MCP サーバーは API キーを受け付けません。入手方法は [Google Cloud の MCP サーバー](../guides/mcp-servers.md#google-cloud-mcp-servers)を参照してください。
- `DEMO_AZURE_TENANT_ID`・`DEMO_AZURE_CLIENT_ID`・`DEMO_AZURE_CLIENT_SECRET` は Azure のサービスプリンシパルです。`az ad sp create-for-rbac` が表示するテナント、アプリのクライアント ID、クライアントシークレットをそのまま入れます。デモでシークレットをローテーションする Key Vault に対して、**Key Vault Secrets Officer** ロールを付与しておいてください。

⚠️ AWS・GKE・Azure の MCP サーバーは、読み取りだけでなく、**状態を変える**操作を実行できます。AWS MCP サーバーの認証情報は実際の AWS リソースを作成・削除でき、GKE MCP サーバーの身元は実際のクラスタでワークロードのローリング再起動や Pod の削除を行え、Azure MCP サーバーのサービスプリンシパルは Key Vault のシークレットを書き込めます。いずれも使い捨てのアカウントか、権限を絞った認証情報を使ってください。実際のプロバイダにまったく触れずにデモを試す方法は、下の[試してみる](#trying-it-out)を参照してください。

## 登録されるもの

- **[エージェントスキル](../guides/agent-skills.md) `Demo AWS EC2 Launch`** — インスタンスの構成を聞き取り、それについて管理職の明示的な承認を得てから、MCP ツールでインスタンスを起動します。リポジトリは起動後にバックグラウンドで clone するので、使えるようになるまでの間スキルは `pending` と表示されます。
- **[エージェントスキル](../guides/agent-skills.md) `Demo GKE Pod Restart`** — 対象(プロジェクト・クラスタ・namespace・そして Deployment/StatefulSet 名か単一の Pod 名のいずれか)をユーザーと合意し、その対象について管理職の明示的な承認を得てから、既定では GKE MCP Server でワークロードをローリング再起動し、ユーザーが1つの Pod だけを望む場合はその Pod を削除して所有コントローラーに再作成させ、結果を報告します。リポジトリの clone も同じ仕組みなので、最初は同様に `pending` と表示されます。
- **[エージェントスキル](../guides/agent-skills.md) `Demo Azure Key Vault Secret Rotation`** — Key Vault と、その中にある既存のシークレットをユーザーと合意し、そのシークレットについて管理職の明示的な承認を得てから、新しく生成したランダムな値をシークレットの新しいバージョンとして Azure MCP Server で書き込み、新しいバージョン ID を報告します。値はチャットに表示しません。リポジトリの clone も同じ仕組みなので、最初は同様に `pending` と表示されます。
- **[MCP サーバー](../guides/mcp-servers.md) `AWS MCP Server`** — AWS のマネージド AWS MCP Server に接続する `stdio` サーバーです。EC2 のツールはここから来ます。
- **[MCP サーバー](../guides/mcp-servers.md) `GKE MCP Server`** — Google Cloud のマネージド GKE(Google Kubernetes Engine)MCP サーバーのフルエンドポイントに接続する `streamable_http` サーバーです。`Authorization` ヘッダーは `Bearer ${gcp-token:demo-gcp-credentials/GOOGLE_CREDENTIALS_JSON}` なので、接続のたびに `demo-gcp-credentials` シークレットから発行したばかりのアクセストークンを送ります。ツールはクラスタや Kubernetes リソースを管理でき、ワークロードのローリング再起動や Pod の削除も含まれます。
- **[MCP サーバー](../guides/mcp-servers.md) `Azure MCP Server`** — Microsoft の Azure MCP Server を、Key Vault のツールだけに絞って動かす `stdio` サーバーです。`demo-azure-credentials` シークレットのサービスプリンシパルでサインインし、Key Vault のシークレット・キー・証明書を一覧したり書き込んだりできます。シークレットに対する操作のたびに同意を求め、その質問は実行の申請者に[チャットでの確認](../guides/workflow-executions.md#mcp-server-confirmations)として届きます。ローテーションに対する管理職の承認とは別に求められます。デモのスキルはデザインエージェントにこのツールへ「質問する」印を付けるよう伝えるので、ツールを使うタスクはそれぞれ申請者の再開を待ちます。新しいシークレットの値は Key Vault に届くまでにエージェントの会話を通るので、実行のチャットはシークレットと同じように扱ってください。
- **[MCP サーバー](../guides/mcp-servers.md) `EC2 Cost Estimator`** — Python の[スクリプトサーバー](../guides/mcp-servers.md#writing-a-script)です。指定したリージョンの価格を AWS の価格表からその場で取得し、EC2 インスタンスタイプのオンデマンド月額を見積もるツール(`estimate_monthly_cost`)と、複数のタイプを安い順に並べるツール(`compare_instance_types`)を提供します。**Packages** で `boto3` をインストールし、`demo-aws-credentials` シークレットを使います。そのため **Test Run** で試すには、AWS の価格表を読む権限(`pricing:GetProducts`)を持つ認証情報が必要です。読み取りしか行いません。
- **[MCP サーバー](../guides/mcp-servers.md) `Kubernetes Manifest Toolkit`** — JavaScript のスクリプトサーバーです。Kubernetes マニフェストに必須項目の抜けがないかを確認するツール(`validate_manifest`)と、Deployment・StatefulSet・DaemonSet をローリング再起動するパッチを作るツール(`build_restart_patch`)を提供します。**Packages** で `js-yaml` をインストールします。認証情報は不要で、クラスタには接続しないので、**Test Run** ですぐに試せます。
- **[MCP サーバー](../guides/mcp-servers.md) `Secret Value Generator`** — JavaScript のスクリプトサーバーです。暗号論的に安全なランダムなシークレット値を生成するツール(`generate_secret_value`)を1つだけ提供します。パッケージのインストールも認証情報も不要で、Azure には接続しないので、**Test Run** ですぐに試せます。
- **[シークレット](../guides/secrets.md) `demo-aws-credentials`** — AWS MCP Server が読む、AWS のアクセスキー ID とシークレットアクセスキーです。
- **[シークレット](../guides/secrets.md) `demo-gcp-credentials`** — GKE MCP Server がアクセストークンを発行する元になる、Google Cloud の認証情報 JSON です。
- **[シークレット](../guides/secrets.md) `demo-azure-credentials`** — Azure MCP Server がサインインに使う、Azure サービスプリンシパルのテナント ID・クライアント ID・クライアントシークレットです。
- **[ツールモック](../guides/tool-mocks.md)** — デモ実行で副作用のあるツールのスタブです。AWS MCP Server の `aws___call_aws` と `aws___run_script`(どちらも起動成功を返す)、GKE MCP Server の `patch_k8s_resource`(ローリング再起動成功を返す)と `delete_k8s_resource`(Pod 削除成功を返す)、Azure MCP Server の `keyvault_secret_get`(Key Vault のシークレット一覧を返す)と `keyvault_secret_create`(新しいシークレットバージョンを返す)、および組み込みの `request_approval`(approved を返す)。ドラフト実行の **Run** ダイアログで選ぶと、AWS や実際の GKE クラスタ、実際の Key Vault に触れることも管理職の承認を待つこともなく、3 つのワークフローのどれも最後まで動きます。
- **[タグ](../guides/tags.md)** `AWS`・`GCP`・`Azure` — それぞれ[アクセス制御タグ](../guides/tags.md#access-control-tags)です。`Demo AWS Group`/`Demo GCP Group`/`Demo Azure Group` のメンバー(および `admin`、スーパー管理者)以外には、そのプロバイダのタグが付いた上記のレコードは見えません。`EC2 Cost Estimator` には `AWS`、`Kubernetes Manifest Toolkit` には `GCP`、`Secret Value Generator` には `Azure` が付いており、それぞれが補助するプロバイダのレコードと同じ扱いになります。`Approval Required` は 3 つのエージェントスキルすべてに付く普通のタグで、何も制限しません。
- **デモユーザーとグループ:**

| ユーザー | ロール | アクセス制御グループ | 役割 |
|---|---|---|---|
| `demo-aws-developer` | `developer` | `Demo AWS Group` | EC2 起動ワークフローを生成する |
| `demo-aws-reviewer` | `reviewer` | `Demo AWS Group` | EC2 起動ワークフローを公開する |
| `demo-aws-requester` | `requester` | `Demo AWS Group` | EC2 起動ワークフローを実行する |
| `demo-gcp-developer` | `developer` | `Demo GCP Group` | GKE Pod 再起動ワークフローを生成する |
| `demo-gcp-reviewer` | `reviewer` | `Demo GCP Group` | GKE Pod 再起動ワークフローを公開する |
| `demo-gcp-requester` | `requester` | `Demo GCP Group` | GKE Pod 再起動ワークフローを実行する |
| `demo-azure-developer` | `developer` | `Demo Azure Group` | シークレットローテーションワークフローを生成する |
| `demo-azure-reviewer` | `reviewer` | `Demo Azure Group` | シークレットローテーションワークフローを公開する |
| `demo-azure-requester` | `requester` | `Demo Azure Group` | シークレットローテーションワークフローを実行する |
| `demo-approver-1`、`demo-approver-2` | `approver` | `Demo Approvers`(3 つのタグすべて) | 起動、Pod の再起動、またはローテーションを承認する |

いずれもロールを直接は持ちません。それぞれ[ユーザーグループ](../guides/users-and-groups.md#user-groups) `Demo Developers`、`Demo Reviewers`、`Demo Requesters`、`Demo Approvers` から継承します。AWS・GCP・Azure の3人組はそれぞれ、もう一つのグループ `Demo AWS Group`・`Demo GCP Group`・`Demo Azure Group` のいずれかにも所属します。このグループはロールを一切付与せず、対応するアクセス制御タグを保持するためだけに存在するので、その3人組だけがそのプロバイダのタグ付きレコードを見られ、それ以外には見えません。ただし `admin`(またはスーパー管理者)は例外で、[アクセス制御タグを完全に素通り](../guides/tags.md#access-control-tags)するため、グループに所属する必要すらありません。`Demo Approvers` 自体は `AWS`・`GCP`・`Azure` の 3 つのアクセス制御タグを直接持ちます。承認者は特定のプロバイダに縛られる立場ではないためで、これにより 3 つのデモワークフローのどれから来た承認依頼でも、デモ承認者のどちらかを宛先にできます。

## 試してみる {#trying-it-out}

どの例も、生成、公開、実行、承認、結果の確認までを一気に通す手順が[ウォークスルー](./walkthrough.mdx)です。`root` で一度サインインし、デモアカウントを順に[なりすまし](../concepts/impersonation.md)で演じます。`DEMO_PASSWORD` で各アカウントにサインインし直しても同じことができます。誰が何をするかは上の表のとおりです。

`Demo AWS Group`・`Demo GCP Group`・`Demo Azure Group` はそれぞれ自分のプロバイダのレコードしか見えないため、`demo-aws-developer` は `Demo GKE Pod Restart` を開けず、`demo-gcp-developer` は `Demo Azure Key Vault Secret Rotation` を開けません。`Demo Approvers` は 3 つのアクセス制御タグすべてを直接持っているので、承認者アカウントはどの例でもどちらでも構いません。GKE の例を実際に動かすには、実際の GKE クラスタに届く権限を持つ身元の認証情報を `DEMO_GCP_CREDENTIALS_JSON` に設定しておく必要があります。ローテーションを実際に動かすには、`DEMO_AZURE_*` のサービスプリンシパルが実際の Key Vault のシークレットを書き込める必要があります。

**AWS アカウントも GKE クラスタも Key Vault もない場合。** 公開せず、`draft` のまま実行してください。`developer` であるそのプロバイダの開発者アカウント(`demo-aws-developer`、`demo-gcp-developer`、`demo-azure-developer`)はそれができ、[ツールモック](../guides/tool-mocks.md)を選べる Run ダイアログが出るのはドラフト実行のときだけです。**Mock tools** に並ぶ同梱のスタブ(起動用の `aws___call_aws` または `aws___run_script`、Pod 再起動用の `patch_k8s_resource` または `delete_k8s_resource`、ローテーション用の `keyvault_secret_get` と `keyvault_secret_create`、`request_approval`)にチェックを入れれば、実際のプロバイダに届くことも人の承認を待つこともなく、ワークフローが最後まで動きます。ローテーションのモックを選んだ場合は Key Vault のシークレット一覧も作り物になるので、その中から `db-password` を選んでください。

## 削除する

`DEMO_DATA=false` にすると(または行を削除すると)、次の起動時にこれらのレコードが**削除されます**。どちらの方向にも宣言的に働くということです。

意図的に残るものが 2 つあります。ほかから依存されるようになったデモレコード(デモスキルの上に作られたワークフローなど)は、削除せずログに記録して残します。レコードを作成したデモユーザーは論理削除にとどめるので、そのレコード上で名前は引き続き解決できます。
