---
title: デモデータ
sidebar_position: 4
---

# デモデータ

バックエンドで `DEMO_DATA=true` を設定すると、承認つきの「EC2 インスタンスを起動する」ワークフローの一式が起動時に登録されます。一つずつ手で登録しなくても、すぐに動かせるものが手元にある状態になります。登録先はすべて初期投入された **Default** テナントです。

- AWS のアクセスキー ID とシークレットアクセスキーを持つ[シークレット](../guides/secrets.md)が 2 件
- [MCP サーバー](../guides/mcp-servers.md)が 1 件(`AWS MCP Server`)。`uvx` で起動する `mcp-proxy-for-aws` を経由し、`stdio` で AWS のマネージド AWS MCP Server に接続します。認証情報は `${secret:…}` 参照で上のシークレットから読みます
- このリポジトリの `sample_skills/aws-ec2-launch` を指す[エージェントスキル](../guides/agent-skills.md)が 1 件
- 承認者[ユーザー](../guides/users-and-groups.md#users) `demo-approver-1` と `demo-approver-2`、依頼者ユーザー `demo-requester-1` と `demo-requester-2`、それに `demo-developer`。いずれも**直接のロールは一つも持ちません**
- [ユーザーグループ](../guides/users-and-groups.md#user-groups)が 3 件。`Demo Approvers` が `approver` を、`Demo Requesters` が `requester` を、`Demo Developers` が `developer` を付与します。`Demo Approvers` と `Demo Requesters` には対応するアカウントが 2 つずつ、`Demo Developers` には 1 つだけ所属します。つまりデモ用アカウントのロールはすべて継承で得たものなので、デモそのものがグループ機能の動作確認になります。ユーザーをグループから外すと、次のリクエストからアクセス権がなくなります

[ワークフロー](../guides/workflows.md)自体は登録されません。これらはワークフローを生成するための材料です。フラグを外して再起動すると、同じレコードが**削除されます**。つまり本当の意味でオン/オフのスイッチです。ほかのデータから参照されるようになったレコードは削除せずに残し、ログに記録します。レコードを作成したデモユーザーは論理削除にとどめるので、名前は引き続き解決できます。

⚠️ デモの MCP サーバーは読み取りだけでなく、**状態を変える** AWS の操作も実行できます。渡した認証情報の権限で実際のリソースを作成したり削除したりできてしまうので、使い捨てのアカウントか、権限を絞った IAM ポリシーを使ってください。

## 登録されるレコード

| リソース | 名前 | 内容 |
|---|---|---|
| シークレット | `demo-aws-credentials` | `local` タイプ。`AWS_ACCESS_KEY_ID` と `AWS_SECRET_ACCESS_KEY` の 2 エントリを持ち、ほかのシークレットと同じく Fernet で暗号化されます |
| MCP サーバー | `AWS MCP Server` | `stdio` トランスポート。`uvx mcp-proxy-for-aws@1.6.4 https://aws-mcp.us-east-1.api.aws/mcp --region us-east-1 --metadata AWS_REGION=${env:AWS_REGION}` を起動します。`AWS_ACCESS_KEY_ID` と `AWS_SECRET_ACCESS_KEY` の環境変数は上の 2 エントリへの `${secret:demo-aws-credentials/…}` 参照で、`AWS_REGION` 環境変数(`DEMO_AWS_REGION` 由来)は接続時に `--metadata AWS_REGION=${env:AWS_REGION}` 引数として展開されます |
| エージェントスキル | `Demo AWS EC2 Launch` | このリポジトリの `sample_skills/aws-ec2-launch`([エージェントスキル](../guides/agent-skills.md)を参照) |
| ユーザー | `demo-approver-1` | **直接のロールなし**。`Demo Approvers` から `approver` を継承します。サンプルスキルが承認依頼を送る先の管理職役です |
| ユーザー | `demo-approver-2` | **直接のロールなし**。`Demo Approvers` から `approver` を継承します。グループに複数人が所属できることを示す 2 人目です |
| ユーザー | `demo-requester-1` | **直接のロールなし**。`Demo Requesters` から `requester` を継承し、ワークフローを実行できます |
| ユーザー | `demo-requester-2` | **直接のロールなし**。`Demo Requesters` から `requester` を継承する 2 人目の依頼者です |
| ユーザー | `demo-developer` | **直接のロールなし**。`Demo Developers` から `developer` を継承し、ワークフロー、MCP サーバー、エージェントスキルを構築・登録できます |
| ユーザーグループ | `Demo Approvers` | `approver` を付与。メンバーは `demo-approver-1` と `demo-approver-2` |
| ユーザーグループ | `Demo Requesters` | `requester` を付与。メンバーは `demo-requester-1` と `demo-requester-2` |
| ユーザーグループ | `Demo Developers` | `developer` を付与。メンバーは `demo-developer` のみ |

デモ用アカウントに直接ではなくグループ経由でロールを渡しているのは意図的です。こうすると[ロールの継承](../concepts/authorization.md)を端から端まで実際に試せるので、ユーザーをグループから外せばアクセス権が失われることが目に見えます。ロールを直接付与していた古いバージョンで初期化されたデータベースは、次回起動時に正規化されるため、付与が二重になることはありません。

ワークフロー自体をあえて登録しないのは、これらのレコードがワークフローを組み立てる材料だからです。

```env
DEMO_DATA=true
DEMO_PASSWORD=change-me-now-123
DEMO_AWS_ACCESS_KEY_ID=AKIA...
DEMO_AWS_SECRET_ACCESS_KEY=...
DEMO_AWS_REGION=us-east-1
```

- `DEMO_PASSWORD` は 5 つのデモユーザーで共有され、`ROOT_PASSWORD` や `ADMIN_PASSWORD` と同じく、未設定なら生成してログに一度だけ出力します。参照されるのは、そのアカウントがまだ存在しないときだけです。
- **AWS MCP Server** は AWS がホストするマネージドのリモートサーバーであって、このプロジェクトが動かすものではありません。そのため登録される `stdio` サーバーが実際に起動するのは [`mcp-proxy-for-aws`](https://github.com/aws/mcp-proxy-for-aws) です。環境変数から認証情報を読んでリクエストを SigV4 で署名し、エンドポイントへ転送するだけの薄いブリッジです。非推奨になった自己ホスト型の `awslabs.aws-api-mcp-server` を置き換えるもので、[移行ガイド](https://github.com/awslabs/mcp/blob/main/src/aws-api-mcp-server/MIGRATION.md)が上流にあります。

  引数に現れる 2 つのリージョンは別物です。`--region us-east-1` は*署名*を計算するリージョンで、エンドポイントの所在に合わせて固定されます。一方 `--metadata AWS_REGION=${env:AWS_REGION}`(この行自身の `env` に入っている `DEMO_AWS_REGION` に展開されます。[`${env:NAME}`](../guides/mcp-servers.md) を参照)は、サーバーの*ツール*が操作する対象のリージョンです。プロキシはエンドポイント URL から署名リージョンを推測しないので、明示したままにしてあります。

- AWS の認証情報は任意です。未設定なら `REPLACE_ME` というプレースホルダーが保存されるので、形としてはデモが揃った状態になり、実際の値はシークレットのページから入れられます。ここで設定しておけば、起動直後からデモが AWS に到達します。必要な権限は、ツールが実際に行う操作の権限に加えて、マネージドエンドポイント(`aws-mcp` サービス)を呼び出す権限です。

  > **デモの MCP サーバーは読み取り専用ではありません。** 渡した認証情報の権限で、実際のリソースを作成・変更・削除できます。課金される稼働中インスタンスも含みます。使い捨てのアカウントを指すか、IAM ポリシーを絞ってください。(`mcp-proxy-for-aws` には `--read-only` フラグがありますが、サンプルのワークフローはインスタンスを起動するので、デモではあえて渡していません。)

- エージェントスキルのリポジトリは起動後にバックグラウンドで clone します。リモートが遅かったり届かなかったりしても、サーバーの起動が待たされることはありません。clone が終わるまでスキルは `pending` のままです。API から登録したスキルと同じ挙動で、失敗した場合はその理由がスキルの行に記録されます。

フラグを外すと(`DEMO_DATA=false`、または削除)、次の起動時にこれらのレコードが**削除されます**。どちらの方向にも宣言的に働くということです。各レコードは名前ではなく固定の ID で追跡するので、管理画面で名前を変えても迷子になりません。

削除されても残るものが 2 つあります。いずれも意図した動作です。

- ほかから依存されるようになったデモレコード(デモスキルの上に作られたワークフローや、デモ MCP サーバーへのタスクのツール割り当てなど)は削除できません。`WARNING` としてログに残してスキップし、残りのデモレコードは削除され、アプリは通常どおり起動します。
- サインインしてレコードを作成したデモユーザーは、削除ではなく**論理削除**になります(無効化して `deletedAt` を設定)。そのレコード上で名前が引き続き解決できるようにするためです。`DEMO_DATA` を再び有効にすると、無効のままにせず復活させます。
