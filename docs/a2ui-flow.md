# A2UI flow

This document describes how A2UI surfaces are generated and rendered in A2Flow, from build time through to the user interaction feedback loop.

## Overview

A2UI rendering is handled entirely on the frontend by [`@ag-ui/a2ui-middleware`](https://www.npmjs.com/package/@ag-ui/a2ui-middleware). The backend agent has no A2UI-specific logic; it simply calls a tool (`render_a2ui`) that the middleware injects into every request.

---

## 1. Build time — schema download

Before `pnpm dev` or `pnpm build` starts, a prebuild script downloads the A2UI Basic Catalog schema:

```
pnpm dev / pnpm build
  └─ scripts/download-a2ui-schema.mjs (predev / prebuild hook)
       └─ GET https://a2ui.org/specification/v0_9/basic_catalog.json
            → src/generated/basic_catalog.json  (gitignored)
```

The schema is used by `A2UIMiddleware` as context for the backend agent.

---

## 2. Request time — tool injection by middleware

When the user submits a message, `createChatAgent()` (`src/lib/api.ts`) attaches `A2UIMiddleware` to the `HttpAgent`. Before the request reaches the backend, the middleware modifies `RunAgentInput`:

```
useChat.sendMessage()
  └─ HttpAgent.runAgent()
       └─ A2UIMiddleware
            ├─ RunAgentInput.tools  ← render_a2ui tool definition appended
            └─ RunAgentInput.context ← basic_catalog.json content appended
                  ↓
            POST /agent  →  FastAPI backend
```

---

## 3. Backend — LLM calls render_a2ui

The backend `ADKAgent` (`ag-ui-adk`) replaces the agent's `AGUIToolset` placeholder with a `ClientProxyToolset` built from `RunAgentInput.tools`. This makes `render_a2ui` callable by the LLM as if it were a native backend tool.

When the LLM decides to render rich UI, it calls `render_a2ui` with structured arguments:

```json
{
  "surfaceId": "result",
  "catalogId": "https://a2ui.org/specification/v0_9/basic_catalog.json",
  "components": [
    { "id": "root", "component": "Card", "child": "col" },
    { "id": "col",  "component": "Column", "children": ["title", "btn"] },
    { "id": "title","component": "Text",   "text": "Hello!", "variant": "h2" },
    { "id": "btn",  "component": "Button", "child": "btn-txt",
      "action": { "event": { "name": "confirm" } } },
    { "id": "btn-txt", "component": "Text", "text": "OK" }
  ],
  "data": {}
}
```

No execution happens on the backend. The bridge streams `TOOL_CALL_START`, `TOOL_CALL_ARGS`, and `TOOL_CALL_END` events back to the frontend via SSE.

---

## 4. Frontend — middleware converts events to ACTIVITY_SNAPSHOT

`A2UIMiddleware` intercepts the `TOOL_CALL_*` events and, from the streamed `render_a2ui` arguments, constructs A2UI v0.9 operation objects:

```
TOOL_CALL_* events (SSE)
  └─ A2UIMiddleware
       └─ builds A2UI v0.9 operations:
            [
              { "version": "v0.9", "createSurface":    { "surfaceId": "result", "catalogId": "..." } },
              { "version": "v0.9", "updateComponents":  { "surfaceId": "result", "components": [...] } },
              { "version": "v0.9", "updateDataModel":   { "surfaceId": "result", "value": {...} } }
            ]
       └─ emits ACTIVITY_SNAPSHOT event:
            {
              "type":         "ACTIVITY_SNAPSHOT",
              "activityType": "a2ui-surface",
              "messageId":    "a2ui-surface-result-<toolCallId>",
              "content":      { "a2ui_operations": [ ... ] },
              "replace":      true
            }
```

Intermediate snapshots may be emitted while the tool args are still streaming. Each snapshot with the same `messageId` replaces the previous one.

---

## 5. Frontend — Redux and rendering

`onActivitySnapshotEvent` in `useChat.ts` dispatches to Redux:

```
onActivitySnapshotEvent
  └─ event.activityType === "a2ui-surface"
       └─ dispatch(addA2uiMessage({
            id:      event.messageId,
            payload: event.content["a2ui_operations"]
          }))
            └─ chatSlice: upsert by id
                  (same messageId → overwrite, new → append)
```

`MessageBubble` renders messages that have `a2uiPayload` via `A2uiRenderer`:

```
A2uiRenderer
  └─ MessageProcessor (@a2ui/web_core/v0_9)  +  tailwindCatalog
       └─ processMessages(operations)
            └─ SurfaceModel created for each surface
  └─ <A2uiSurface surface={...} />
       └─ Tailwind-styled Text / Card / Button / Row / Column /
          TextField / ChoicePicker  (src/components/a2uiCatalog.tsx)
```

---

## 6. User action — feedback loop

When the user interacts with a rendered surface (e.g. clicks a `Button`), `useChat` sends the action as the **tool result for the preceding `render_a2ui` call**:

```
Button click
  └─ SurfaceModel.dispatchAction()
       └─ surface.onAction emits A2UIUserAction:
            {
              name:              "confirm",
              surfaceId:         "result",
              sourceComponentId: "btn",
              context:           { userName: "Alice" },
              timestamp:         "2026-04-25T..."
            }
            └─ A2uiRenderer.onAction callback → sendA2uiAction()
                 └─ agent.addMessage({
                      role:       "tool",
                      toolCallId: <render_a2ui tool call ID>,
                      content:    'User performed action "confirm" on surface
                                   "result" (component: btn). Context: {"userName":"Alice"}'
                    })
                 └─ HttpAgent.runAgent({ forwardedProps: { userId } })
                      └─ POST /agent
                           └─ backend matches tool result against pending
                              render_a2ui call → LLM reads action context
                              and responds
```

The `render_a2ui` tool call ID used above is captured by `onToolCallEndEvent` during the previous turn and stored in `pendingRenderToolCallIds` ref in `useChat`.

---

### Why `forwardedProps.a2uiAction` was not used

`A2UIMiddleware.processUserAction` converts a user action into a synthetic **`log_a2ui_event`** assistant message + tool result pair injected into `input.messages`. This was the original design, but it fails with `ag-ui-adk` for the following reason:

`ADKAgent` only processes incoming tool result messages when their `tool_call_id` appears in the session-state list `pending_tool_calls`. That list is populated exclusively when the **LLM itself** issues a tool call during a run. Because `log_a2ui_event` is a synthetic tool call created by the middleware — never by the LLM — its ID is never registered in `pending_tool_calls`. The agent therefore logs:

```
Skipping tool result batch for thread <id> - no matching pending tool calls
```

and silently discards the user action.

Sending the action as the tool result for `render_a2ui` (the real, LLM-issued call) sidesteps this entirely: the ID is already in `pending_tool_calls`, the match succeeds, and the LLM receives the action context as part of normal tool-call resolution.
