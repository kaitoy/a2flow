---
title: 動作の仕組み
sidebar_position: 1
---

# 動作の仕組み

1. ユーザーが「+ 新しいセッション」を押すと、フロントエンドはバックエンドに問い合わせずに `/newSession` へ移動します。セッション ID(`threadId`)は、ユーザーが最初のメッセージを送信した瞬間にフロントエンドが生成します(`crypto.randomUUID()`)。ADK のセッションは、それを参照する最初の `POST /agent` リクエストでバックエンドが暗黙に作ります。そのあとページの URL は `/sessions/{id}` に置き換わり、ストリーミング中の応答が正規のセッションのルートの下で続きます。
2. ユーザーがメッセージを送信すると、`createChatAgent()` が `HttpAgent`(`@ag-ui/client`)を作ります。これは認証セッションのクッキー(`credentials: "include"`)と `X-CSRF-Token` ヘッダーを送り、`A2UIMiddleware`(`@ag-ui/a2ui-middleware`)が適用されます。リクエストがバックエンドに届く前に、ミドルウェアが `render_a2ui` ツールを `RunAgentInput.tools` へ、A2UI Basic Catalog のスキーマ(ビルド時に `https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json` から取得したもの)を `RunAgentInput.context` へ注入します。
3. バックエンドの `ADKAgent`(`ag-ui-adk`)が、AG-UI プロトコルと Google ADK の `LlmAgent` を橋渡しします。イベントを変換し、セッションを管理し、AG-UI の SSE イベントをクライアントへ返します。エージェントは `AGUIToolset` を使い、ブリッジがこれを実行時に `RunAgentInput.tools` から組み立てた `ClientProxyToolset` に差し替えます。これによって、フロントエンドが注入した `render_a2ui` ツールを LLM が呼べるようになります。
4. LLM が `render_a2ui` を呼ぶと、`ADKAgent` が `TOOL_CALL_*` イベントを流します。`A2UIMiddleware` がこれを捕まえて A2UI の操作を組み立て直し、`ACTIVITY_SNAPSHOT` イベント(サーフェスごとに 1 つ、`activityType: "a2ui-surface"`)を出します。バックエンドでツールが実行されることはありません。
5. フロントエンドの `AgentSubscriber`(`src/lib/agentSubscriber.ts` の `createAgentSubscriber` が作り、2 つのチャット画面で共有します)が、各イベントを Redux のストアへ振り分けます。テキストのイベントはチャットを少しずつ更新し、アシスタントのテキストは Markdown として描画されます(`marked` を使い、`markdown-body` ユーティリティでスタイルを当てます)。描画系でないツールの `TOOL_CALL_*` イベントと `REASONING_*` イベントは `activity` メッセージ(`activityType: "tool_call"` と `"reasoning"`)に対応づけられ、`ToolActivityBubble` と `ReasoningBubble` がインラインで描画します([チャットに出るエージェントの動き](./overview.md#agent-activity-in-the-chat)を参照)。`ACTIVITY_SNAPSHOT` イベントは `a2ui_operations` キーの下に A2UI の操作を持ち、Redux に保存されます。`A2uiRenderer` がその操作を `MessageProcessor`(`@a2ui/web_core/v0_9`)へ渡し、`<A2uiSurface>` でサーフェスを描画します。

   コンポーネントの描画には `tailwindCatalog` を使います。`src/components/a2uiCatalog.tsx` にある独自の `Catalog<ReactComponentImplementation>` で、`Text`、`Button`、`Card`、`Row`、`Column`、`TextField`、`ChoicePicker` の Tailwind CSS 版を提供します。選択肢が 5 つ以上ある単一選択の `ChoicePicker` は、ラジオの一覧ではなく共有の `Select` ドロップダウンに畳まれます。エージェントが許される値(EC2 のインスタンスタイプやリージョンなど)をすべて列挙しても会話が埋もれないようにするためです。[A2UI flow](https://github.com/kaitoy/a2flow/blob/master/docs/a2ui-flow.md) を参照してください。Markdown のレンダラーは `MarkdownContext` 経由で `marked` を使います。
6. LLM が `render_a2ui` を呼ぶと、`useChat` が `onToolCallEndEvent` でツール呼び出しの ID を捕まえ、`pendingRenderCalls` に保存します。ユーザーが描画されたサーフェス上で操作を起こす(たとえば `Button` を押す)と、`sendA2uiAction` がその `render_a2ui` 呼び出しに対するツール結果のメッセージを `POST /agent` へ直接送ります。これでバックエンドは、保留中の `render_a2ui` ツール呼び出しと結果を突き合わせて LLM へ渡せるので、LLM がユーザーの操作に応答できます。`forwardedProps.a2uiAction` と `A2UIMiddleware.processUserAction` は使いません。

   ツールの結果は **JSON オブジェクト**で、サーフェスのデータモデル全体を `values` の下に持ちます。ユーザーが入力・選択した値がすべて入ります。文章ではなく JSON にしているのは、`ag-ui-adk` が JSON として解釈できないツール結果を保存前に包んでしまい、再読み込み時に形が変わってしまうからです。操作の `context` ではなくデータモデル全体を載せているのは、`context` には操作されたコンポーネントについてエージェントが宣言したバインディングしか入らないからです。この 2 つのおかげで、エージェントは実際の入力を読めますし、再読み込みしたセッションでは、回答済みのサーフェスがエージェントの既定値ではなくユーザーが送信した内容で埋まった状態で再表示されます([docs/a2ui-flow.md](https://github.com/kaitoy/a2flow/blob/master/docs/a2ui-flow.md) を参照)。
7. セッションの状態はバックエンドのメモリに保たれます。`threadId` がそのまま ADK のセッション ID として使われるので(`use_thread_id_as_session_id=True`)、同じ `threadId` を使えば会話を効率よく続けられます。

## チャットに出るエージェントの動き {#agent-activity-in-the-chat}

返信と返信のあいだにエージェントが何をしているのかが見えるよう、途中の作業もチャットの流れの中に出します。

- **作業中の表示** — 実行中でまだ画面に何も出ていないあいだ、メッセージ一覧の下に「考えています…」という控えめな明滅が出ます。
- **ツール呼び出しの行** — バックエンドのツール呼び出し(`create_workflow_task`、`list_workflow_tasks` など)はすべて、スピナー(`running…`)からチェック(`done`)へ変わるコンパクトなステータス行になります。`call_mcp_tool` のプロキシを通した呼び出しは、**本来の MCP ツール名**で `MCP` タグとともに出ます。`render_a2ui` と `render_approval` のクライアントツールは専用の UI を持つので、ツールの行としては出ません。
- **呼び出しの詳細** — 引数や結果を持つツールの行は**クリックで展開**し、両方を整形した JSON で表示します。エージェントが実際に何を送って何を受け取ったのかを、チャットを離れずに確認できます。[ツールモック](../guides/tool-mocks.md)が答えた行には `Mocked` のバッジが付きます。差し替えられた呼び出しは MCP プロキシに届かず監査の行を残さないので、確認できる場所はチャットだけです。
- **推論** — 思考を出せるモデルが `REASONING_*` イベントを出すと、流れてくる思考が「Thinking」の控えめなパネルとして描画されます。既定の `gemini-3.5-flash` は内部で推論しますが、有効にしない限り思考の要約を流さないので、このパネルが出るのは思考を出すよう設定したモデルのときだけです。

セッションを再開したときに履歴から復元されるのは、**MCP のツール呼び出し**(`call_mcp_tool`)だけです。A2Flow 内部のツール呼び出しと推論はその場限りです。
