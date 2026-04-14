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
| AG-UI | @ag-ui/client + @ag-ui/core |
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

Open [http://localhost:3000](http://localhost:3000).

## Project structure

```
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
├── hooks/
│   └── useChat.ts        # Session init + SSE streaming logic
├── store/
│   ├── chatSlice.ts      # Redux slice (messages, session, streaming state)
│   ├── index.ts          # Store configuration
│   ├── hooks.ts          # Typed useAppDispatch / useAppSelector
│   └── provider.tsx      # Client-side Redux Provider
└── lib/
    ├── api.ts            # createSession(), createChatAgent() (@ag-ui/client HttpAgent)
    └── logger.ts         # pino logger instance
```

## How it works

1. On mount, `useChat` calls `POST /sessions` to obtain a `session_id`.
2. When the user sends a message, `createChatAgent()` returns an `HttpAgent` (from `@ag-ui/client`) bound to that session.
3. `agent.runAgent()` posts an [AG-UI `RunAgentInput`](https://docs.ag-ui.com/concepts/events) to `POST /chat` and streams the SSE response. Events are handled via an `AgentSubscriber`:
   - `onTextMessageStartEvent` — creates a new assistant message in the Redux store
   - `onTextMessageContentEvent` — appends delta text (shows blinking cursor while streaming)
   - `onTextMessageEndEvent` — marks the message as complete
   - `onToolCallStartEvent` — tracks `send_a2ui_json_to_client` tool call IDs
   - `onToolCallResultEvent` — when a tracked tool call completes, extracts `validated_a2ui_json` from the result and dispatches `addA2uiMessage` to the Redux store
   - `onRunErrorEvent` — surfaces an error banner
4. Messages with an `a2uiPayload` are rendered by `A2uiRenderer` instead of a plain text bubble. `A2uiRenderer` creates a `MessageProcessor` (from `@a2ui/web_core/v0_9`) with `tailwindCatalog`, feeds the payload to `processMessages()`, and renders each resulting surface via `<A2uiSurface>`. For each surface, `A2uiRenderer` also subscribes to `surface.onAction` to capture user-triggered events (see step 5).
5. When the user triggers a `Button` action on an A2UI surface, `SurfaceModel.dispatchAction()` emits an event via `surface.onAction`. `A2uiRenderer` serializes it to a JSON string — `{"action":"<event.name>", ...resolvedContext}` — and calls `onAction`, which is wired to `sendMessage` via `Chat → MessageList → MessageBubble → A2uiRenderer`. The action is therefore submitted to the agent as a normal user turn via `POST /agent`. There is **no dedicated endpoint** for A2UI events; the agent handles them as regular conversational messages.
6. Reusing the same `session_id` / `threadId` across turns preserves conversation history in the backend.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `BACKEND_BASE_URL` | `http://localhost:8000` | Backend base URL |
