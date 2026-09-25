---
title: MCP サーバー
sidebar_position: 7
---

# MCP サーバー

[MCP](https://modelcontextprotocol.io/) サーバーは、エージェントが呼び出せるツールを提供します。ここはその登録簿です。サーバーを登録すると、そのツールをワークフローのタスクテンプレートに割り当てられるようになります。[タスクが使う MCP ツール](./workflows.md#mcp-tools-for-tasks)を参照してください。

管理サイドバーの **MCP Servers** を開くと登録簿を管理できます。レコードは一意の **Name**、任意の **Description**、[タグ](./tags.md)、そして残りの入力項目を決める **Transport** を持ちます。

## トランスポート {#transports}

| トランスポート | 項目 | 何か |
|---|---|---|
| **Streamable HTTP**(既定) | **URL**、**HTTP Headers** | リモートのサーバー。ヘッダーは毎リクエストに付きます。多くは `Authorization: Bearer …` です。SSE のみのサーバーには対応していません。 |
| **stdio** | **Command**、**Arguments**、**Environment Variables** | バックエンドの子プロセスとして起動するサーバー。たとえば `npx` に `["-y", "@modelcontextprotocol/server-everything"]` を渡します。`npx` と `uvx` のどちらも使えます。 |
| **Script** | **Language**、**Source**、**Environment Variables** | 自分で書いた Python または JavaScript のコード。公開された関数がそれぞれツールになります。[スクリプトを書く](#writing-a-script)を参照してください。 |

既存のサーバーのトランスポートを切り替えると、切り替え前のトランスポートの項目は消えます。stdio サーバーに URL、リモートサーバーに command、どちらかにソースコードといった、形が混ざったレコードは拒否されます。

⚠️ **stdio サーバーの登録は、指定したコマンドをバックエンドのコンテナ内で実行することを意味します。**実行はコンテナの非特権ユーザーとして行われます。ほかの MCP サーバーへの書き込みと同じく `developer` ロールで守られています。Arguments はシェルを介さずリストとしてプロセスに渡され、子プロセスが引き継ぐ環境変数は、安全な小さな組み合わせと設定した Environment Variables だけです。バックエンド自身の API キーやデータベース URL は見えません。

## スクリプトを書く {#writing-a-script}

スクリプトサーバーを使うと、パッケージを公開しなくても、自分で書いた関数をツールにできます。**Transport** で **Script** を選び、**Language** を選んで、コードを **Source** に貼り付けます。

**Source** はコードエディターです。選んだ **Language** に合わせてコードを色分けし、行番号を付け、**Tab** キーでインデントします。**Tab** で次の項目へ移るには、先に **Esc** キーを押します。入力に合わせて問題のある箇所に下線が引かれ、下線にマウスを重ねると内容が表示されます。

| 下線 | 意味 | 例 |
|---|---|---|
| 赤の波線 | 構文エラー。スクリプトを実行できません | 閉じていない括弧、綴りを間違えたキーワード |
| 黄色の波線 | 間違いの可能性があります | ツールになる関数が 1 つもない。Python の関数に docstring がない、または引数に型ヒントがない。標準ライブラリ以外を import している。JavaScript の関数に `description` がない |
| アクセント色の波線 | 補足です | JavaScript の関数に `inputSchema` がない |

下線は助言であり、保存を妨げることはありません。保存時の検査については後述します。

| | Python | JavaScript |
|---|---|---|
| ツールになる関数 | トップレベルで定義した関数のうち、名前が `_` で始まらないもの。import した関数は公開されません。 | export した関数（`export function`、`export async function`）のうち、名前が `_` で始まらないもの。default export は公開されません。 |
| ツール名 | 関数名 | export 名 |
| 説明 | docstring | 関数の `description` プロパティ |
| 引数 | 型ヒントから読み取ります | 関数の `inputSchema` プロパティ（JSON Schema）。無い場合、ツールはどんな引数も受け付けます。 |
| 呼び出され方 | 引数を名前で渡します | 引数をまとめた 1 つのオブジェクトを渡します |
| エージェントに返るもの | 戻り値 | 戻り値。文字列はそのまま、それ以外は JSON にします |

```python
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b
```

```js
export function add({ a, b }) {
  return a + b;
}
add.description = "Add two numbers.";
add.inputSchema = {
  type: "object",
  properties: { a: { type: "number" }, b: { type: "number" } },
  required: ["a", "b"],
};
```

どちらの言語にも次の決まりがあります。

- 使えるのは標準ライブラリだけです。Python 自身のモジュールか、Node.js 組み込みの `node:` モジュールです。サードパーティのパッケージはインストールできません。
- 関数が投げたエラーは、ツール呼び出しの失敗としてメッセージごとエージェントに伝わります。
- `print()` や `console.log()` の出力はサーバーのログに出ます。エージェントには届きません。
- **Environment Variables** は `os.environ["NAME"]` や `process.env.NAME` で読めます。[資格情報をレコードに置かない](#keeping-credentials-out-of-the-record)のプレースホルダーも使えます。
- **Source** に書けるのは 30,000 文字までです。
- Python のコードに構文エラーがあると、保存時に行番号付きで拒否されます。JavaScript は保存時には検査されません。壊れたスクリプトは、[ツールを確認](#checking-a-servers-tools)したときに起動できないサーバーとして表示されます。

⚠️ スクリプトは stdio サーバーと同じ場所で、同じ制限のもとで実行されます。

## 資格情報をレコードに置かない {#keeping-credentials-out-of-the-record}

⚠️ ヘッダーと環境変数にそのまま書いた値は**平文で保存され**、詳細ページにも表示されます。資格情報を直接書く代わりに、登録済みの[シークレット](./secrets.md)の 1 エントリを参照してください。

| プレースホルダー | 使える場所 | 例 |
|---|---|---|
| `${secret:name/key}` | ヘッダーの値、環境変数の値 | `Authorization: Bearer ${secret:github/token}`<br/>`AWS_ACCESS_KEY_ID: ${secret:aws-credentials/AWS_ACCESS_KEY_ID}` |
| `${gcp-token:name/key}` | `${secret:…}` と同じ。エントリには Google Cloud の認証情報 JSON を入れておきます | `Authorization: Bearer ${gcp-token:gcp-credentials/GOOGLE_CREDENTIALS_JSON}` |
| `${env:NAME}` | **Arguments** の要素。このサーバー自身の環境変数を名前で参照します | `--token ${env:API_KEY}` |

プレースホルダーが展開されるのは接続のときだけなので、資格情報が保存されたレコードに現れることはありません。

`${env:NAME}` は、その環境変数自身の `${secret:…}` が展開されたあとに展開されます。おかげで、シークレット由来の値をコマンドラインのフラグとして使い回せます。プロセスの環境変数から読むのではなく、引数として受け取るランチャー向けです。`NAME` は **Environment Variables** のキーでなければならず、存在しないキーへの参照は — そのキーを消したせいで残った参照も含めて — 保存時に拒否されます。

### Google Cloud の MCP サーバー {#google-cloud-mcp-servers}

Google のマネージド MCP サーバー（GKE のものなど）は API キーを受け付けません。すべてのリクエストに Google Cloud の身元に対する OAuth 2.0 アクセストークンが要り、しかもトークンは 1 時間で失効するので、シークレットに貼っておくこともできません。そこで `${gcp-token:name/key}` を使います。エントリの値そのものではなく、その値から**発行したばかりのアクセストークン**に展開され、期限が切れれば自動で更新されます。エントリに入れる認証情報 JSON は次の 2 種類のどちらかです。

| 認証情報 | 入手方法 | トークンのスコープ |
|---|---|---|
| **サービスアカウントの鍵** | サービスアカウントを作り、**MCP Tool User** とツールが必要とするロールを付与して、JSON 鍵をダウンロードします | `cloud-platform` |
| **OAuth クライアント ID とシークレット** | OAuth クライアント（デスクトップアプリ）を作って JSON をダウンロードし、自分のマシンで一度だけ `gcloud auth application-default login --client-id-file=<その JSON> --scopes=https://www.googleapis.com/auth/cloud-platform` を実行してサインインします。できあがった `application_default_credentials.json` の中身を貼ります | 同意したスコープ |

どちらの場合も、JSON 全体を[シークレット](./secrets.md)の 1 エントリとして貼り、上の例のようにサーバーの `Authorization` ヘッダーから参照します。ワークフローを誰が始めても、ツール呼び出しはその 1 つの身元で実行されます。壊れた認証情報や Google が受け付けなくなった認証情報は、宙に浮いた `${secret:…}` 参照と同じ形で接続を失敗させます。

## MCP レジストリから登録する {#registering-from-the-mcp-registry}

一覧ページの **Browse registry** ボタンを押すと、公式の [MCP レジストリ](https://registry.modelcontextprotocol.io/)を検索するダイアログが開きます。

1. 名前で検索します。結果に出るのは A2Flow が登録できるサーバーだけです。streamable HTTP のエンドポイントを持つものと、npm か PyPI のパッケージとして公開されていて stdio で起動できるものです。
2. 1 つ選びます。接続情報と、そのサーバーが必要とするヘッダーや環境変数のキーが入った状態で、新規作成フォームが開きます。
3. シークレットの値を埋めて保存します。

パッケージから起動コマンドへの対応づけは最善努力なので、保存する前に内容を確認してください。検索先のレジストリは[設定リファレンス](../operations/configuration.md#mcp-tools-and-approvals)で変更できます。

## サーバーのツールを確認する {#checking-a-servers-tools}

タスクテンプレートのフォームは、サーバーが公開しているツール — 名前、説明、入力スキーマ — を問い合わせます。問い合わせ先は選んだ 1 台だけで、登録簿全体に一度に接続しにいくことはありません。到達できない、あるいは起動できないサーバーは、ツール一覧の代わりにその旨を表示します。

## サーバーを削除する {#deleting-a-server}

タスクやタスクテンプレートがそのサーバーのツールを割り当てている間は、サーバーを削除できません。先に割り当てを外してください。
