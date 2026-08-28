---
title: クイックスタート
sidebar_position: 1
---

# クイックスタート

## 0. ツールチェーン([mise](https://mise.jdx.dev/))

Python、Node.js、pnpm、uv、lefthook のバージョンは [mise.toml](https://github.com/kaitoy/a2flow/blob/master/mise.toml) で固定し、mise が用意します。どのマシンでも同じツールチェーンが動くようにするためです。mise 自体のインストールは一度だけです。

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

Windows では、mise の shims ディレクトリ(`%LOCALAPPDATA%\mise\shims`)を `PATH` にも通してください。Git フックやエディタの連携機能は有効化済みのシェルの外から起動されるため、`uv` や `pnpm` や `python` を `PATH` からしか解決できません。

mise を使わない場合は、Python 3.11 以上、Node.js 20 以上に加えて、[uv](https://docs.astral.sh/uv/)、pnpm、lefthook を手動で入れてください。

## 1. バックエンド

バックエンド自体に必要なのは Python と uv だけです。Node.js は npm パッケージとして公開されている stdio 方式の [MCP サーバー](../guides/mcp-servers.md)を `npx` で起動するときにしか使いません。`docker compose` のイメージには同梱されています。

```bash
cd backend
uv sync
cp .env.example .env
# .env を編集し、LLM_MODEL と対応する API キーを設定する(backend/README.md を参照)
uv run uvicorn main:app --reload
```

これで API が `http://localhost:8000` で使えるようになります。

## 2. フロントエンド

```bash
cd frontend
pnpm install
# 任意: cp .env.local.example .env.local  (バックエンドが :8000 にない場合だけ必要)
pnpm dev
```

[http://localhost:3000](http://localhost:3000) を開きます。別のポートで動かす方法は、フロントエンドの README にある [Changing the port](https://github.com/kaitoy/a2flow/blob/master/frontend/README.md#changing-the-port) を参照してください。

## 3. Git フック(lefthook)

コミット前とプッシュ前のフック(lefthook)が、リンター、フォーマッター、型チェッカー、テストを実行します。`lefthook` のバイナリは `mise install` で入っているので、リポジトリのルートで `lefthook install` を一度実行して `.git/hooks/` に登録してください。詳細は [.claude/rules/git-workflow.md](https://github.com/kaitoy/a2flow/blob/master/.claude/rules/git-workflow.md) にあります。
