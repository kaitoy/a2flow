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

既存のサーバーのトランスポートを切り替えると、もう一方の項目は消えます。stdio サーバーに URL、リモートサーバーに command といった、2 つの形が混ざったレコードは拒否されます。

⚠️ **stdio サーバーの登録は、指定したコマンドをバックエンドのコンテナ内で実行することを意味します。**実行はコンテナの非特権ユーザーとして行われます。ほかの MCP サーバーへの書き込みと同じく `developer` ロールで守られています。Arguments はシェルを介さずリストとしてプロセスに渡され、子プロセスが引き継ぐ環境変数は、安全な小さな組み合わせと設定した Environment Variables だけです。バックエンド自身の API キーやデータベース URL は見えません。

## 資格情報をレコードに置かない {#keeping-credentials-out-of-the-record}

⚠️ ヘッダーと環境変数にそのまま書いた値は**平文で保存され**、詳細ページにも表示されます。資格情報を直接書く代わりに、登録済みの[シークレット](./secrets.md)の 1 エントリを参照してください。

| プレースホルダー | 使える場所 | 例 |
|---|---|---|
| `${secret:name/key}` | ヘッダーの値、環境変数の値 | `Authorization: Bearer ${secret:github/token}`<br/>`AWS_ACCESS_KEY_ID: ${secret:aws-credentials/AWS_ACCESS_KEY_ID}` |
| `${env:NAME}` | **Arguments** の要素。このサーバー自身の環境変数を名前で参照します | `--token ${env:API_KEY}` |

プレースホルダーが展開されるのは接続のときだけなので、資格情報が保存されたレコードに現れることはありません。

`${env:NAME}` は、その環境変数自身の `${secret:…}` が展開されたあとに展開されます。おかげで、シークレット由来の値をコマンドラインのフラグとして使い回せます。プロセスの環境変数から読むのではなく、引数として受け取るランチャー向けです。`NAME` は **Environment Variables** のキーでなければならず、存在しないキーへの参照は — そのキーを消したせいで残った参照も含めて — 保存時に拒否されます。

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
