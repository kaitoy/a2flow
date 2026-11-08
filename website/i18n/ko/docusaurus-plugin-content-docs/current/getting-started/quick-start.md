---
title: 빠른 시작
sidebar_position: 1
---

# 빠른 시작

## 0. 도구 체인([mise](https://mise.jdx.dev/)) {#0-toolchain-mise}

Python, Node.js, pnpm, uv 버전은 [mise.toml](https://github.com/kaitoy/a2flow/blob/master/mise.toml)에 고정되어 있고 mise가 이를 설치하므로, 어느 컴퓨터에서나 같은 도구 체인이 실행됩니다. mise는 한 번만 설치하면 됩니다.

| OS | 명령 |
|---|---|
| Windows | `winget install jdx.mise` |
| macOS | `brew install mise` |
| Linux | [설치 문서](https://mise.jdx.dev/installing-mise.html)를 참조하세요 |

셸에서 mise를 활성화한 다음(bash/zsh/fish는 [활성화 문서](https://mise.jdx.dev/installing-mise.html#shells)를 참조하세요. Windows에서는 PowerShell의 `$PROFILE`에 `(&mise activate pwsh) | Out-String | Invoke-Expression`을 추가합니다) 저장소 루트에서 도구를 설치합니다.

```bash
mise trust
mise install
```

Windows에서는 mise의 shims 디렉터리(`%LOCALAPPDATA%\mise\shims`)도 `PATH`에 추가하세요. 그래야 활성화된 셸 밖에서도 `uv`, `pnpm`, `python`을 찾을 수 있습니다.

mise를 사용하지 않는다면 최소 버전은 Python 3.11 이상, Node.js 20 이상이며, [uv](https://docs.astral.sh/uv/)와 pnpm은 직접 설치해야 합니다.

## 1. 백엔드 {#1-backend}

백엔드 자체에는 Python과 uv만 있으면 됩니다. Node.js는 npm 패키지로 배포된 stdio [MCP 서버](../guides/mcp-servers.md)를 `npx`로 실행할 때만 사용하며, `docker compose` 이미지에는 포함되어 있습니다.

```bash
cd backend
uv sync
cp .env.example .env
sed -i.bak 's/^GOOGLE_API_KEY=.*/GOOGLE_API_KEY=YOUR_API_KEY/' .env && rm .env.bak
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 30
```

`.env.example`의 기본값은 Google Gemini이므로 `YOUR_API_KEY`를 본인의 키로 바꾸세요. 다른 모델이나 제공자를 사용하려면 [LLM 설정](./llm-configuration.md)을 참조하세요.

이제 `http://localhost:8000`에서 API를 사용할 수 있습니다.

## 2. 프런트엔드 {#2-frontend}

```bash
cd frontend
pnpm install
# 선택 사항: cp .env.local.example .env.local  (백엔드가 :8000에 있지 않을 때만 필요)
pnpm build
pnpm start
```

[http://localhost:3000](http://localhost:3000)을 엽니다. 다른 포트에서 실행하려면 프런트엔드 README의 [Changing the port](https://github.com/kaitoy/a2flow/blob/master/frontend/README.md#changing-the-port)를 참조하세요.
