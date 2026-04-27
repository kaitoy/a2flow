# A2Flow

A chat application that connects a [Google ADK](https://google.github.io/adk-docs/) agent to a Next.js UI using the [AG-UI protocol](https://docs.ag-ui.com/concepts/events). The agent supports [A2UI](https://a2ui.org/) — it can generate structured UI JSON payloads alongside plain text responses.

```
┌──────────────────────────────────┐    AG-UI RunAgentInput (JSON)    ┌──────────────────────┐
│   Next.js frontend               │  (render_a2ui tool injected by   │  FastAPI backend     │
│   @ag-ui/client                  │ ───────────────────────────────► │  Google ADK agent    │
│   @ag-ui/a2ui-middleware         │   A2UIMiddleware)                 │  AGUIToolset         │
│   Redux Toolkit                  │                                   │  InMemorySession     │
│                                  │ ◄─────────────────────────────── │                      │
└──────────────────────────────────┘  AG-UI events (SSE) incl.        └──────────────────────┘
     :3000                            A2UI (TOOL_CALL_*)                    :8000
```

## Repository layout

```
a2flow/
├── backend/   # FastAPI + Google ADK agent
└── frontend/  # Next.js 15 chat UI
```

## Quick start

### 1. Backend

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/)

```bash
cd backend
uv sync
cp .env.example .env
# Edit .env — set LLM_MODEL and the corresponding API key (see backend/README.md)
uv run uvicorn main:app --reload
```

The API is now available at `http://localhost:8000`.

### 2. Frontend

Requirements: Node.js 20+, pnpm

```bash
cd frontend
pnpm install
# Optional: cp .env.local.example .env.local  (only needed if backend is not on :8000)
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000).

## How it works

1. The frontend creates a session via `POST /sessions` on startup, obtaining a `session_id` / `threadId`.
2. When the user submits a message, `createChatAgent()` creates an `HttpAgent` (from `@ag-ui/client`) with `A2UIMiddleware` (from `@ag-ui/a2ui-middleware`) applied. Before each request reaches the backend, the middleware injects the `render_a2ui` tool into `RunAgentInput.tools` and the A2UI Basic Catalog schema (downloaded from `https://a2ui.org/specification/v0_9/basic_catalog.json` at build time) into `RunAgentInput.context`.
3. The backend's `ADKAgent` (from `ag-ui-adk`) bridges the AG-UI protocol to a Google ADK `LlmAgent` — translating events, managing sessions, and streaming AG-UI SSE events back to the client. The agent uses `AGUIToolset`, which the bridge replaces at runtime with a `ClientProxyToolset` built from `RunAgentInput.tools` — making the frontend-injected `render_a2ui` tool callable by the LLM.
4. When the LLM calls `render_a2ui`, the `ADKAgent` streams `TOOL_CALL_*` events. The `A2UIMiddleware` intercepts these, reconstructs the A2UI operations, and emits `ACTIVITY_SNAPSHOT` events (one per surface, `activityType: "a2ui-surface"`). No tool execution happens on the backend.
5. The frontend's `AgentSubscriber` dispatches each event to a Redux store. Text events update the chat incrementally. `ACTIVITY_SNAPSHOT` events carry A2UI operations under the `a2ui_operations` key, which are stored in Redux. `A2uiRenderer` feeds the operations to `MessageProcessor` (from `@a2ui/web_core/v0_9`) and renders surfaces via `<A2uiSurface>`. Component rendering uses `tailwindCatalog` — a custom `Catalog<ReactComponentImplementation>` in `src/components/a2uiCatalog.tsx` that provides Tailwind CSS–styled versions of `Text`, `Button`, `Card`, `Row`, `Column`, `TextField`, and `ChoicePicker`. `marked` is used as the markdown renderer via `MarkdownContext`.
6. When the LLM calls `render_a2ui`, `useChat` captures the tool call ID via `onToolCallEndEvent` and stores it in a ref. When the user triggers an action on the rendered surface (e.g. clicking a `Button`), `sendA2uiAction` sends a tool result message for that `render_a2ui` call — with the action description as the content — directly to `POST /agent`. This lets the backend match the result against the pending `render_a2ui` tool call and forward it to the LLM, which then responds to the user's action. `forwardedProps.a2uiAction` / `A2UIMiddleware.processUserAction` is not used.
7. Session state is preserved in memory on the backend; `threadId` is used directly as the ADK session ID (`use_thread_id_as_session_id=True`), so reusing the same `threadId` continues the conversation efficiently.

## LLM configuration

Set `LLM_MODEL` in `backend/.env`:

| Provider | Value |
|---|---|
| Google Gemini (default) | `gemini-2.0-flash` |
| OpenAI via LiteLLM | `litellm:openai/gpt-4o` |
| Anthropic via LiteLLM | `litellm:anthropic/claude-3-5-sonnet-20241022` |

See [backend/README.md](backend/README.md) for the full configuration reference.

## Further reading

- [backend/README.md](backend/README.md) — API reference, environment variables, running options
- [frontend/README.md](frontend/README.md) — project structure, component overview, environment variables
