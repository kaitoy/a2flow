# A2Flow

A chat application that connects a [Google ADK](https://google.github.io/adk-docs/) agent to a Next.js UI using the [AG-UI protocol](https://docs.ag-ui.com/concepts/events). The agent supports [A2UI](https://a2ui.org/) — it can generate structured UI JSON payloads alongside plain text responses.

```
┌─────────────────────┐        AG-UI RunAgentInput (JSON)        ┌──────────────────────┐
│   Next.js frontend  │  ────────────────────────────────────►   │  FastAPI backend     │
│   @ag-ui/client     │                                          │  Google ADK agent    │
│   Redux Toolkit     │  ◄────────────────────────────────────   │  a2ui-agent-sdk      │
└─────────────────────┘     AG-UI events (SSE) incl. A2UI JSON   │  InMemorySession     │
     :3000                                                        └──────────────────────┘
                                                                        :8000
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

Requirements: Node.js 20+, npm

```bash
cd frontend
npm install
# Optional: cp .env.local.example .env.local  (only needed if backend is not on :8000)
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## How it works

1. The frontend creates a session via `POST /sessions` on startup, obtaining a `session_id` / `threadId`.
2. When the user submits a message, `@ag-ui/client`'s `HttpAgent` posts a standard `RunAgentInput` to `POST /agent`.
3. The backend's `ADKAgent` (from `ag-ui-adk`) bridges the AG-UI protocol to a Google ADK `LlmAgent` — translating events, managing sessions, and streaming AG-UI SSE events (`RUN_STARTED` → `TEXT_MESSAGE_*` → `RUN_FINISHED`) back to the client. The FastAPI endpoint is registered via `add_adk_fastapi_endpoint`.
4. The agent is equipped with `SendA2uiToClientToolset` (from `a2ui-agent-sdk`). When the LLM decides to render rich UI, it calls `send_a2ui_json_to_client`; the tool validates the payload against the A2UI Basic Catalog (v0.9) schema and the result flows through the AG-UI stream as tool call events.
5. The frontend's `AgentSubscriber` dispatches each event to a Redux store. Text events update the chat incrementally. `TOOL_CALL_RESULT` events from `send_a2ui_json_to_client` carry the validated A2UI JSON payload, which is extracted and stored in Redux. `A2uiRenderer` then feeds the payload to `MessageProcessor` (from `@a2ui/web_core/v0_9`) and renders the resulting surfaces via `<A2uiSurface>`. Component rendering uses `tailwindCatalog` — a custom `Catalog<ReactComponentImplementation>` defined in `src/components/a2uiCatalog.tsx` that replaces the default `basicCatalog` implementations of `Text`, `Button`, `Card`, `Row`, `Column`, `TextField`, and `ChoicePicker` with Tailwind CSS–styled versions. `marked` is used as the markdown renderer, supplied via `MarkdownContext` so that `Text` components render markdown to HTML.
6. When a user triggers an action on an A2UI surface (e.g. clicking a `Button` whose `action` has an `event` field), `SurfaceModel.dispatchAction()` emits the event via `surface.onAction`. `A2uiRenderer` subscribes to this emitter and serializes the action as a plain JSON string — `{"action":"<event.name>", ...resolvedContext}` — then submits it to the agent as an ordinary user message via `POST /agent` (the same endpoint used for typed chat messages). There is **no separate webhook or event endpoint** for A2UI actions; the agent receives them as regular conversational turns and can inspect the action name and context values to decide what to do next.
6. Session state is preserved in memory on the backend; `threadId` is used directly as the ADK session ID (`use_thread_id_as_session_id=True`), so reusing the same `threadId` continues the conversation efficiently.

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
