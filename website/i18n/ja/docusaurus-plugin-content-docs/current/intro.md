---
title: はじめに
slug: /intro
sidebar_position: 1
---

# はじめに

A2Flow は、[Google ADK](https://google.github.io/adk-docs/) のエージェントと Next.js の UI を [AG-UI プロトコル](https://docs.ag-ui.com/concepts/events)でつないだチャットアプリケーションです。エージェントは [A2UI](https://a2ui.org/) に対応しています。ユーザーからの入力が必要になったときは A2UI の入力部品(テキストフィールド、選択リスト、ボタン)を描画するので、何を入力すればよいかがそのまま画面に出ます。単に情報を返すだけの応答はトークン単位でストリーミングされ、Markdown として描画されるため、ツール呼び出しの完了を待たされることもありません。

フロントエンドは**グラスモーフィズム**の見た目で、**ライト/ダークのテーマ切り替え**を備えています(選択は `localStorage` に保存され、初期値は OS の設定に従います)。デザインシステムの詳細は [DESIGN.md](https://github.com/kaitoy/a2flow/blob/master/DESIGN.md) を参照してください。上部ツールバーの**通知センター**には、下書きの生成完了や承認依頼といった未読のワークフローイベントが表示されます。全履歴はアカウントメニューから開ける専用の通知ページで確認できます([通知](./guides/notifications.md))。スーパー管理者が[システム設定](./guides/system-settings.md)で SMTP サーバーを設定すると、同じイベントが**メールでも**宛先に届きます。

UI は**レスポンシブ**です。`md` ブレークポイントより狭い画面では、サイドバー(チャットセッション一覧、管理画面のナビゲーション、ワークフロータスクのタイムライン)がすべてヘッダーのハンバーガーボタンから開くドロワーに収まります。レイアウトは動的ビューポート高さを使うので、モバイルの URL バーがチャット入力欄を隠すこともありません。タッチデバイスでは操作ボタンが常時表示になり、タップ領域は約 44px、フォームの文字は 16px(iOS のフォーカス時ズームを防ぐため)、チャット入力欄では Enter が改行になります。

```
┌──────────────────────────────────┐    AG-UI RunAgentInput (JSON)    ┌──────────────────────┐
│   Next.js frontend               │  (render_a2ui tool injected by   │  FastAPI backend     │
│   @ag-ui/client                  │ ───────────────────────────────► │  Google ADK agent    │
│   @ag-ui/a2ui-middleware         │   A2UIMiddleware)                 │  AGUIToolset         │
│   Redux Toolkit                  │                                   │  DB SessionService   │
│   Admin UI (/admin)              │ ◄─────────────────────────────── │  SQLite/PostgreSQL   │
└──────────────────────────────────┘  AG-UI events (SSE) incl.        └──────────────────────┘
     :3000                            A2UI (TOOL_CALL_*)                    :8000
```

## 次に読むページ

- **[クイックスタート](./getting-started/quick-start.md)** — 手元のマシンでバックエンドとフロントエンドを動かす
- **[用語](./concepts/terminology.md)** — ワークフロー、設計セッション、実行、ワークフローセッションの違い
- **[ワークフロー](./guides/workflows.md)** — エージェントスキルからワークフローを生成し、調整して、公開し、実行する
- **[設定リファレンス](./operations/configuration.md)** — バックエンドが読む環境変数の一覧
