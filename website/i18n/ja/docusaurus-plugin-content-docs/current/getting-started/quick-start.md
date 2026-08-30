---
title: クイックスタート
sidebar_position: 1
---

# クイックスタート

## 0. ツールチェーン([mise](https://mise.jdx.dev/))

Python、Node.js、pnpm、uv のバージョンは [mise.toml](https://github.com/kaitoy/a2flow/blob/master/mise.toml) で固定し、mise が用意します。どのマシンでも同じツールチェーンが動くようにするためです。mise 自体のインストールは一度だけです。

| OS | コマンド |
|---|---|
| Windows | `winget install jdx.mise` |
| macOS | `brew install mise` |
| Linux | [インストール手順](https://mise.jdx.dev/installing-mise.html)を参照 |

シェルで有効化してから(bash/zsh/fish は[有効化の手順](https://mise.jdx.dev/installing-mise.html#shells)を参照。Windows では PowerShell の `$PROFILE` に `(&mise activate pwsh) | Out-String | Invoke-Expression` を追加します)、リポジトリのルートでツールをインストールします。

```bash
mise trust
mise install
```

Windows では、mise の shims ディレクトリ(`%LOCALAPPDATA%\mise\shims`)を `PATH` にも通してください。有効化済みのシェルの外でも `uv` や `pnpm` や `python` を解決できるようにするためです。

mise を使わない場合は、Python 3.11 以上、Node.js 20 以上に加えて、[uv](https://docs.astral.sh/uv/) と pnpm を手動で入れてください。

## 1. バックエンド

バックエンド自体に必要なのは Python と uv だけです。Node.js は npm パッケージとして公開されている stdio 方式の [MCP サーバー](../guides/mcp-servers.md)を `npx` で起動するときにしか使いません。`docker compose` のイメージには同梱されています。

```bash
cd backend
uv sync
cp .env.example .env
sed -i.bak 's/^GOOGLE_API_KEY=.*/GOOGLE_API_KEY=YOUR_API_KEY/' .env && rm .env.bak
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 30
```

`.env.example` は既定で Google Gemini を使うので、`YOUR_API_KEY` を取得済みの API キーに置き換えてください。別のモデルやプロバイダに切り替える場合は [LLM の設定](./llm-configuration.md) を参照してください。

これで API が `http://localhost:8000` で使えるようになります。

## 2. フロントエンド

```bash
cd frontend
pnpm install
# 任意: cp .env.local.example .env.local  (バックエンドが :8000 にない場合だけ必要)
pnpm build
pnpm start
```

[http://localhost:3000](http://localhost:3000) を開きます。別のポートで動かす方法は、フロントエンドの README にある [Changing the port](https://github.com/kaitoy/a2flow/blob/master/frontend/README.md#changing-the-port) を参照してください。
