# A2Flow frontend

Chat UI for [A2Flow](../README.md). Streams responses from the backend via SSE and renders them in real time.

## Tech stack

| | |
|---|---|
| Framework | Next.js 16 (App Router) |
| Language | TypeScript |
| State | Redux Toolkit + React Redux |
| Styling | Tailwind CSS v4 |
| HTTP | Fetch API (REST) / @ag-ui/client (SSE streaming) |
| Logging | pino (browser mode) |
| AG-UI | @ag-ui/client + @ag-ui/core + @ag-ui/a2ui-middleware |
| A2UI | @a2ui/react + @a2ui/web_core |
| Package manager | pnpm |

## Requirements

- Node.js 20+
- pnpm
- [A2Flow backend](../backend/) running on `http://localhost:8000`

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

`pnpm dev` and `pnpm build` automatically run `scripts/download-a2ui-schema.mjs` first, which downloads the A2UI Basic Catalog schema from `https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json` into `src/generated/basic_catalog.json`.

Open [http://localhost:3000](http://localhost:3000).

## Project structure

```
scripts/
└── download-a2ui-schema.mjs   # Downloads basic_catalog.json at build time (predev/prebuild)
src/
├── app/
│   ├── layout.tsx        # Root layout — wraps tree in StoreProvider
│   ├── page.tsx          # Entry point
│   └── globals.css       # Tailwind directives
├── components/
│   ├── Chat.tsx          # Top-level chat screen
│   ├── MessageList.tsx   # Scrollable message history
│   ├── MessageBubble.tsx # Individual message bubble (text or A2UI)
│   ├── A2uiRenderer.tsx  # A2UI surface renderer
│   └── ChatInput.tsx     # Textarea with Enter-to-send
├── generated/
│   └── basic_catalog.json     # Downloaded at build time (gitignored)
├── hooks/
│   └── useChat.ts        # Session init + SSE streaming logic
├── store/
│   ├── chatSlice.ts      # Redux slice (messages, session, streaming state)
│   ├── index.ts          # Store configuration
│   ├── hooks.ts          # Typed useAppDispatch / useAppSelector
│   └── provider.tsx      # Client-side Redux Provider
└── lib/
    ├── api.ts            # listSessions(), createChatAgent() with A2UIMiddleware
    └── logger.ts         # pino logger instance
```

## How it works

1. Clicking "+ New session" navigates the frontend to `/new-session` without any backend call. The session is materialized lazily: when the user submits the first message, `useChat.sendMessage` generates a UUID with `crypto.randomUUID()`, sets it in Redux, calls `router.replace('/sessions/{id}')` to update the URL, and uses that UUID as the `threadId` for the agent run. The backend creates the ADK session implicitly on the first `POST /agent` it receives. The `/sessions/[sessionId]` page detects that the Redux `sessionId` already matches the URL parameter and skips the initial `getSessionMessages` fetch so the in-flight stream is preserved across the navigation. Sessions can also be deleted from the sidebar via a per-row ✕ button (confirmation modal); if the active session is deleted, the user is redirected to `/new-session`.
2. When the user sends a message, `createChatAgent()` returns an `HttpAgent` (from `@ag-ui/client`) with `A2UIMiddleware` applied. Before each request, the middleware:
   - Injects the `render_a2ui` tool into `RunAgentInput.tools` so the backend LLM can call it.
   - Injects the A2UI Basic Catalog schema (from `src/generated/basic_catalog.json`) into `RunAgentInput.context`.
3. `agent.runAgent()` posts the `RunAgentInput` to `POST /agent` and streams the SSE response. Events are handled via an `AgentSubscriber`:
   - `onTextMessageStartEvent` — creates a new assistant message in the Redux store
   - `onTextMessageContentEvent` — appends delta text (shows blinking cursor while streaming)
   - `onTextMessageEndEvent` — marks the message as complete
   - `onActivitySnapshotEvent` — when `activityType` is `"a2ui-surface"`, extracts the A2UI operations from `event.content["a2ui_operations"]` and dispatches `addA2uiMessage`. Subsequent snapshots with the same `messageId` update the existing message in place (upsert).
   - `onToolCallEndEvent` — when `toolCallName` is `render_a2ui`, stores the tool call ID in `pendingRenderToolCallIds` ref for use in the next turn.
   - `onRunErrorEvent` — surfaces an error banner
4. Messages with an `a2uiPayload` are rendered by `A2uiRenderer` instead of a plain text bubble. `A2uiRenderer` creates a `MessageProcessor` (from `@a2ui/web_core/v0_9`) with `tailwindCatalog`, feeds the operations to `processMessages()`, and renders each resulting surface via `<A2uiSurface>`. For each surface, `A2uiRenderer` also subscribes to `surface.onAction` to capture user-triggered events (see step 5).
5. When the user triggers a `Button` action on an A2UI surface, `A2uiRenderer` calls `sendA2uiAction`. This drains `pendingRenderToolCallIds` and, for each ID, calls `agent.addMessage()` with a tool result message whose `toolCallId` matches the pending `render_a2ui` call and whose `content` describes the user's action (e.g. `User performed action "submit" on surface "my-form". Context: {...}`). The backend matches the tool result against the pending `render_a2ui` call and passes it to the LLM, which responds to the action. `forwardedProps.a2uiAction` / `A2UIMiddleware.processUserAction` is **not** used.
6. Reusing the same `id` / `threadId` across turns preserves conversation history in the backend.

For the full end-to-end A2UI flow (build-time schema download → tool injection → LLM call → event conversion → rendering → action feedback loop), see [docs/a2ui-flow.md](../docs/a2ui-flow.md).

## Testing

Unit tests are implemented with [Vitest](https://vitest.dev/), [Testing Library](https://testing-library.com/), and [MSW](https://mswjs.io/).

### Running tests

```bash
# Run all tests once
pnpm test

# Watch mode
pnpm test:watch

# Run with coverage report
pnpm test:coverage
```

### Test structure

| Tool | Purpose |
|---|---|
| Vitest | Test runner |
| @testing-library/react | Rendering and assertions for components and hooks |
| @testing-library/user-event | User interaction simulation |
| MSW (Mock Service Worker) | Backend API mocking |

Test files live next to the source files they cover, named `*.test.ts(x)`.

Shared test infrastructure (custom renderer, MSW server, mocks) lives under `src/test/`:

```
src/test/
├── setup.ts           # Global setup (MSW server, jest-dom matchers)
├── test-utils.tsx     # Custom render wrapped in Redux Provider
├── mocks/
│   ├── next-navigation.ts  # Stub for next/navigation
│   └── next-font.ts        # Stub for next/font/google
└── msw/
    ├── handlers.ts    # MSW request handlers for the backend API
    └── server.ts      # MSW server instance
```

### Mocking strategy

- **Backend REST API** — intercepted via MSW
- **Agent streaming** (`/agent` endpoint) — `HttpAgent` from `@ag-ui/client` is mocked at the module level (SSE streaming is not practical to simulate with MSW in jsdom)
- **`next/navigation`** — replaced with a stub via `resolve.alias` in `vitest.config.ts`
- **`@a2ui/react` / `@a2ui/web_core`** — mocked per test file with `vi.mock()` at the `A2uiRenderer` boundary to avoid the complex dependency chain

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `BACKEND_BASE_URL` | `http://localhost:8000` | Backend base URL |
