---
title: 快速开始
sidebar_position: 1
---

# 快速开始

## 0. 工具链（[mise](https://mise.jdx.dev/)） {#0-toolchain-mise}

Python、Node.js、pnpm 和 uv 的版本都固定在 [mise.toml](https://github.com/kaitoy/a2flow/blob/master/mise.toml) 中，并由 mise 负责安装，因此每台机器运行的都是相同的工具链。mise 本身只需安装一次：

| 操作系统 | 命令 |
|---|---|
| Windows | `winget install jdx.mise` |
| macOS | `brew install mise` |
| Linux | 请参阅[安装文档](https://mise.jdx.dev/installing-mise.html) |

在 shell 中激活它（bash/zsh/fish 请参阅[激活文档](https://mise.jdx.dev/installing-mise.html#shells)；在 Windows 上，将 `(&mise activate pwsh) | Out-String | Invoke-Expression` 添加到 PowerShell 的 `$PROFILE`），然后在仓库根目录下安装这些工具：

```bash
mise trust
mise install
```

在 Windows 上，还要把 mise 的 shims 目录（`%LOCALAPPDATA%\mise\shims`）加入 `PATH`，这样即使不在已激活的 shell 中，也能找到 `uv`、`pnpm` 和 `python`。

不使用 mise？最低版本要求是 Python 3.11+、Node.js 20+，另外还需手动安装 [uv](https://docs.astral.sh/uv/) 和 pnpm。

## 1. 后端 {#1-backend}

后端本身只需要 Python 和 uv；Node.js 仅用于启动以 npm 包形式发布的 stdio [MCP 服务器](../guides/mcp-servers.md)（`npx`），而 `docker compose` 镜像已自带 Node.js。

```bash
cd backend
uv sync
cp .env.example .env
sed -i.bak 's/^GOOGLE_API_KEY=.*/GOOGLE_API_KEY=YOUR_API_KEY/' .env && rm .env.bak
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 30
```

`.env.example` 默认使用 Google Gemini，因此请将 `YOUR_API_KEY` 替换为您自己的密钥。要使用其他模型或提供商，请参阅 [LLM 配置](./llm-configuration.md)。

现在可以通过 `http://localhost:8000` 访问 API 了。

## 2. 前端 {#2-frontend}

```bash
cd frontend
pnpm install
# 可选: cp .env.local.example .env.local  (仅当后端不在 :8000 上时才需要)
pnpm build
pnpm start
```

打开 [http://localhost:3000](http://localhost:3000)。要在其他端口上运行，请参阅前端 README 中的 [Changing the port](https://github.com/kaitoy/a2flow/blob/master/frontend/README.md#changing-the-port)。
