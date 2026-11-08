# A2Flow frontend

Chat UI for [A2Flow](../README.md). Streams responses from the backend via SSE and renders them in real time.

What each screen does, from the user's side, is in the manual at
<https://kaitoy.github.io/a2flow/>. This file covers the implementation.

## Tech stack

| | |
|---|---|
| Framework | Next.js 16 (App Router) |
| Language | TypeScript |
| State | Redux Toolkit + React Redux |
| Styling | Tailwind CSS v4 |
| Animation | @react-spring/web (mount/unmount, list staggering, modals) + CSS keyframes |
| Icons | lucide-react (wrapped by `AnimatedIcon` for subtle, motion-safe animation) |
| Graph viz | @xyflow/react (React Flow) |
| HTTP | Fetch API (REST) / @ag-ui/client (SSE streaming) |
| AG-UI | @ag-ui/client + @ag-ui/core + @ag-ui/a2ui-middleware |
| A2UI | @a2ui/react + @a2ui/web_core |
| i18n | Typed catalogs + React context + `Intl`, in `src/i18n/` (see [Translating the GUI](#translating-the-gui)) |
| Package manager | pnpm |

## Requirements

Node.js and pnpm are pinned in [mise.toml](../mise.toml) and installed by `mise install` — see [Quick start](../README.md#0-toolchain-mise). Without mise, install Node.js 20+ and pnpm by hand.

Note that `pnpm dev` / `pnpm build` also shell out to `uv` (via `generate:api`), so the backend toolchain must be on `PATH` too.

At runtime the UI expects the [A2Flow backend](../backend/) to be running on `http://localhost:8000`.

## Setup

```bash
pnpm install
cp .env.local.example .env.local
```

Edit `.env.local` if the backend is not on the default address:

```env
BACKEND_BASE_URL=http://localhost:8000
```

## Running

```bash
# Development (hot reload)
pnpm dev

# Production build
pnpm build
pnpm start
```

`pnpm dev` and `pnpm build` automatically run `scripts/download-a2ui-schema.mjs` first, which downloads the A2UI Basic Catalog schema from `https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json` into `src/generated/basic_catalog.json`, verifying its SHA-256 against a pinned constant in the script and failing the build on mismatch.

Open [http://localhost:3000](http://localhost:3000).

### Changing the port

Both `next dev` and `next start` read the `PORT` environment variable natively. Set it before running the command — it **cannot** go in `.env.local`, since Next.js starts its HTTP server before any `.env*` file is loaded:

```bash
# bash
PORT=4000 pnpm dev
```

```powershell
# PowerShell
$env:PORT=4000; pnpm dev
```

## Project structure

The directory layout and where each kind of code lives is documented in [.claude/rules/frontend-patterns.md](../.claude/rules/frontend-patterns.md).

## How it works

1. Clicking "+ New session" navigates the frontend to `/sessions/new` without any backend call. The session is materialized lazily: when the user submits the first message, `useChat.sendMessage` generates a UUID with `crypto.randomUUID()`, sets it in Redux, calls `router.replace('/sessions/{id}')` to update the URL, and uses that UUID as the `threadId` for the agent run. The backend creates the ADK session implicitly on the first `POST /agent` it receives. The `/sessions/[sessionId]` page detects that the Redux `sessionId` already matches the URL parameter and skips the initial `getSessionMessages` fetch so the in-flight stream is preserved across the navigation. Sessions can also be deleted from the sidebar via a per-row ✕ button (confirmation modal); if the active session is deleted, the user is redirected to `/sessions/new`. Visiting the bare `/sessions` path redirects to `/sessions/new`.
2. When the user sends a message, `createChatAgent()` returns an `HttpAgent` (from `@ag-ui/client`) configured with the `X-User-Id` header (taken from the current Redux `userId`) and `A2UIMiddleware` applied. Before each request, the middleware:
   - Injects the `render_a2ui` tool into `RunAgentInput.tools` so the backend LLM can call it.
   - Injects the A2UI Basic Catalog schema (from `src/generated/basic_catalog.json`) into `RunAgentInput.context`.
3. `agent.runAgent()` posts the `RunAgentInput` to `POST /agent` and streams the SSE response. Events are handled via an `AgentSubscriber`:
   - `onTextMessageStartEvent` — creates a new assistant message in the Redux store
   - `onTextMessageContentEvent` — appends delta text (shows blinking cursor while streaming)
   - `onTextMessageEndEvent` — marks the message as complete
   - `onActivitySnapshotEvent` — when `activityType` is `"a2ui-surface"`, extracts the A2UI operations from `event.content["a2ui_operations"]` and dispatches `addA2uiMessage`. Subsequent snapshots with the same `messageId` update the existing message in place (upsert).
   - `onToolCallEndEvent` — when `toolCallName` is `render_a2ui`, stores the tool call ID in `pendingRenderToolCallIds` ref for use in the next turn.
   - `onRunErrorEvent` — surfaces an error banner, which stays until dismissed or until the user sends the next message (history polling deliberately leaves it alone)
4. Messages with an `a2uiPayload` are rendered by `A2uiRenderer` instead of a plain text bubble. `A2uiRenderer` creates a `MessageProcessor` (from `@a2ui/web_core/v0_9`) with `tailwindCatalog`, feeds the operations to `processMessages()`, and renders each resulting surface via `<A2uiSurface>`. For each surface, `A2uiRenderer` also subscribes to `surface.onAction` to capture user-triggered events (see step 5).
5. When the user triggers a `Button` action on an A2UI surface, `A2uiRenderer` calls `sendA2uiAction`. This drains `pendingRenderToolCallIds` and, for each ID, calls `agent.addMessage()` with a tool result message whose `toolCallId` matches the pending `render_a2ui` call and whose `content` describes the user's action (e.g. `User performed action "submit" on surface "my-form". Context: {...}`). The backend matches the tool result against the pending `render_a2ui` call and passes it to the LLM, which responds to the action. `forwardedProps.a2uiAction` / `A2UIMiddleware.processUserAction` is **not** used.
6. Reusing the same `id` / `threadId` across turns preserves conversation history in the backend.
7. A workflow execution's session works differently: the backend runs every turn itself, so `useExecutionSessionChat` never runs the agent. It reads the session's history (`getExecutionSessionHistory`, which also returns a `streamCursor`, and `running` while a turn is queued or under way — the hook then shows the agent working at once, and the turn's message is already appended to the history), then subscribes with `createSessionStreamAgent` — an `HttpAgent` that `GET`s the session's stream after that cursor, with the same `A2UIMiddleware` so streamed `render_a2ui` calls still become surfaces. The stream ends with each turn; the hook re-reads the history and subscribes again. Sending a message or answering a form posts it to the session's input endpoint (`sendSessionInput`) for the server to run. A question an MCP server asks mid-call arrives as an `mcp_elicitation` activity in the running turn's stream; `ElicitationControls` renders its form and answers it with `answerSessionElicitation`, which the still-running turn picks up by itself. Such a question only comes after the session was `waiting_for_initiator` and the initiator pressed **Resume** in `InitiatorResumeNotice` — which just sends a chat message, the turn the backend lets the held task start on. The design session still uses the browser-driven path above (`useDesignSessionChat`).

For the full end-to-end A2UI flow (build-time schema download → tool injection → LLM call → event conversion → rendering → action feedback loop), see [docs/a2ui-flow.md](../docs/a2ui-flow.md).

## Translating the GUI

The screens come in `en`, `ja`, `es`, `zh-CN`, `ko` and `fr`, through a small layer in `src/i18n/` with no i18n library.

| File | Holds |
|---|---|
| `messages/en.ts` | The English text, which also defines the keys |
| `messages/<locale>.ts` | Each translation, typed so a missing or extra key fails the build |
| `config.ts` | The language list, and matching a browser's preference onto it |
| `translate.ts` | `{name}` placeholders, plurals via `Intl.PluralRules`, `t.rich` for embedded nodes |
| `provider.tsx`, `locale-sync.tsx` | The language on screen, and following the signed-in user's setting |
| `server.ts` | Resolving a request's language from the `a2flow.locale` cookie, then `Accept-Language` |

Use `{ one, other }` for a message with a count; a language without plural forms gives `other` alone. A test checks that every language uses the same placeholders as English.

**Adding a language** means a new value in the backend's `Language` literal (`backend/models/user.py`), a new entry in `LOCALE_NAMES`, a catalog, a loader line in `load.ts`, and the strings in `app/global-error.tsx`, which carries its own.

### Glossary

Keep these consistent when adding text. The manual under `website/i18n/` uses the same wording.

| English | ja | es | zh-CN | ko | fr |
|---|---|---|---|---|---|
| Workflow | ワークフロー | flujo de trabajo | 工作流 | 워크플로 | workflow |
| Task | タスク | tarea | 任务 | 작업 | tâche |
| Task template | タスクテンプレート | plantilla de tarea | 任务模板 | 작업 템플릿 | modèle de tâche |
| Workflow execution | ワークフロー実行 | ejecución | 工作流执行 | 워크플로 실행 | exécution |
| Approval | 承認 | aprobación | 审批 | 승인 | approbation |
| Agent skill | エージェントスキル | skill de agente | 代理技能 | 에이전트 스킬 | compétence d'agent |
| Tool mock | ツールモック | mock de herramienta | 工具模拟 | 도구 모의 | simulacre d'outil |
| Secret | シークレット | secreto | 密钥 | 시크릿 | secret |
| Knowledge base | ナレッジベース | base de conocimiento | 知识库 | 지식 베이스 | base de connaissances |
| Tag | タグ | etiqueta | 标签 | 태그 | étiquette |
| User group | ユーザーグループ | grupo de usuarios | 用户组 | 사용자 그룹 | groupe d'utilisateurs |
| Tenant | テナント | tenant | 租户 | 테넌트 | tenant |
| Role | ロール | rol | 角色 | 역할 | rôle |
| Impersonate | 代理ログイン | suplantar | 代理登录 | 대리 로그인 | agir en tant que |

## Testing

Unit tests are implemented with [Vitest](https://vitest.dev/), [Testing Library](https://testing-library.com/), and [MSW](https://mswjs.io/). They run against [happy-dom](https://github.com/capricorn86/happy-dom) rather than jsdom — the suite's cost is dominated by each of its ~140 files building a DOM from scratch, and happy-dom builds one far more cheaply. Like jsdom it has no layout engine, so tests that depend on real measurements stub them.

### Running tests

```bash
# Run all tests once
pnpm test

# Watch mode
pnpm test:watch

# Run with coverage report
pnpm test:coverage
```

### Test structure and mocking strategy

Test file placement, the shared `src/test/` infrastructure, and the per-boundary mocking strategy are documented in [.claude/rules/frontend-patterns.md](../.claude/rules/frontend-patterns.md).

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `BACKEND_BASE_URL` | `http://localhost:8000` | Backend base URL, read by `src/proxy.ts` at server startup — not baked in at `docker build` time, so it can be set in `compose.yml`'s `frontend.environment` without rebuilding the image. |
| `PORT` | `3000` | Dev/start server port, read natively by Next.js. Must be set as a real environment variable — `.env.local` doesn't work (see [Changing the port](#changing-the-port)). |
