# A2Flow frontend

Chat UI for [A2Flow](../README.md). Streams responses from the backend via SSE and renders them in real time.

## Tech stack

| | |
|---|---|
| Framework | Next.js 15 (App Router) |
| Language | TypeScript |
| State | Redux Toolkit + React Redux |
| Styling | Tailwind CSS |
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

`pnpm dev` and `pnpm build` automatically run `scripts/download-a2ui-schema.mjs` first, which downloads the A2UI Basic Catalog schema from `https://a2ui.org/specification/v0_9/basic_catalog.json` into `src/generated/basic_catalog.json`.

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
    ├── api.ts            # createSession(), createChatAgent() with A2UIMiddleware
    └── logger.ts         # pino logger instance
```

## How it works

1. On mount, `useChat` calls `POST /sessions` to obtain a `session_id`.
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
6. Reusing the same `session_id` / `threadId` across turns preserves conversation history in the backend.

For the full end-to-end A2UI flow (build-time schema download → tool injection → LLM call → event conversion → rendering → action feedback loop), see [docs/a2ui-flow.md](../docs/a2ui-flow.md).

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `BACKEND_BASE_URL` | `http://localhost:8000` | Backend base URL |
