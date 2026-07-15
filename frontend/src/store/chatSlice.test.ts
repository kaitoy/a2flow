import {
  A2UI_OPERATIONS_KEY,
  A2UIActivityType,
  RENDER_A2UI_TOOL_NAME,
} from "@ag-ui/a2ui-middleware";
import { describe, expect, it } from "vitest";
import { A2UI_CATALOG_ID } from "@/lib/a2uiCatalogId";
import {
  A2UI_SOURCE_TOOL_CALL_ID_KEY,
  CALL_MCP_TOOL_NAME,
  TOOL_CALL_ACTIVITY_TYPE,
  type ToolCallActivityContent,
} from "@/lib/agentActivity";
import type { Message } from "./chatSlice";
import chatReducer, {
  addActivityMessage,
  addPendingRenderCall,
  addUserMessage,
  appendDelta,
  clearError,
  clearPendingRenderCalls,
  endAssistantMessage,
  finishRun,
  resumeSession,
  setError,
  setSession,
  startAssistantMessage,
  syncPolledMessages,
} from "./chatSlice";

const emptyState = chatReducer(undefined, { type: "@@INIT" });

describe("chatSlice", () => {
  describe("setSession", () => {
    it("sets sessionId, clears messages and resets flags", () => {
      const state = chatReducer(
        { ...emptyState, messages: [{ id: "1", role: "user", content: "hi" }], isRunning: true },
        setSession("new-session")
      );
      expect(state.sessionId).toBe("new-session");
      expect(state.messages).toHaveLength(0);
      expect(state.isRunning).toBe(false);
      expect(state.isStreaming).toBe(false);
      expect(state.error).toBeNull();
      expect(state.pendingRenderCalls).toEqual([]);
    });
  });

  describe("resumeSession", () => {
    it("populates messages with plain messages", () => {
      const messages: Message[] = [
        { id: "m1", role: "user", content: "hello" },
        { id: "m2", role: "assistant", content: "hi there" },
      ];
      const state = chatReducer(emptyState, resumeSession({ sessionId: "sess-1", messages }));
      expect(state.sessionId).toBe("sess-1");
      expect(state.messages).toHaveLength(2);
      expect(state.messages[0].id).toBe("m1");
      expect(state.isRunning).toBe(false);
      expect(state.pendingRenderCalls).toEqual([]);
    });

    it("derives pending render calls from unanswered render_a2ui tool calls", () => {
      // The history is the source of truth: a render call with no answering
      // tool message is still pending — even in a browser that never streamed
      // it (page reload, or another participant's run) — while an answered one
      // is not. This keeps a later user action deliverable as the acted-on
      // call's tool result.
      const messages: Message[] = [
        {
          id: "m1",
          role: "assistant",
          content: "",
          toolCalls: [
            {
              id: "tc-answered",
              type: "function",
              function: {
                name: RENDER_A2UI_TOOL_NAME,
                arguments: JSON.stringify({ surfaceId: "surf-old", components: [] }),
              },
            },
          ],
        },
        { id: "t1", role: "tool", toolCallId: "tc-answered", content: "rendered" },
        {
          id: "m2",
          role: "assistant",
          content: "",
          toolCalls: [
            {
              id: "tc-pending",
              type: "function",
              function: {
                name: RENDER_A2UI_TOOL_NAME,
                arguments: JSON.stringify({ surfaceId: "surf-new", components: [] }),
              },
            },
          ],
        },
      ];
      // A stale live-streamed pending call is replaced by the derived list.
      const stateWithPending = {
        ...emptyState,
        sessionId: "sess-1",
        pendingRenderCalls: [{ toolCallId: "tc-stale", surfaceId: null }],
      };
      const state = chatReducer(stateWithPending, resumeSession({ sessionId: "sess-1", messages }));
      expect(state.pendingRenderCalls).toEqual([
        { toolCallId: "tc-pending", surfaceId: "surf-new" },
      ]);
    });

    it("synthesizes A2UI activity message from RENDER_A2UI_TOOL_NAME tool call", () => {
      const toolCallId = "tc-1";
      const surfaceId = "surf-1";
      const messages: Message[] = [
        {
          id: "m1",
          role: "assistant",
          content: "",
          toolCalls: [
            {
              id: toolCallId,
              type: "function",
              function: {
                name: RENDER_A2UI_TOOL_NAME,
                arguments: JSON.stringify({
                  surfaceId,
                  catalogId: "basic",
                  components: [{ id: "btn1" }],
                }),
              },
            },
          ],
        },
      ];
      const state = chatReducer(emptyState, resumeSession({ sessionId: "sess-1", messages }));
      expect(state.messages).toHaveLength(2);
      const activityMsg = state.messages[1];
      expect(activityMsg.role).toBe("activity");
      if (activityMsg.role !== "activity") throw new Error("expected activity message");
      expect(activityMsg.activityType).toBe(A2UIActivityType);
      expect(activityMsg.id).toBe(`a2ui-surface-${surfaceId}-${toolCallId}`);
      // Stamped so the UI can look up who resolved this render call without
      // parsing it back out of the id above.
      expect(activityMsg.content[A2UI_SOURCE_TOOL_CALL_ID_KEY]).toBe(toolCallId);
      const ops = activityMsg.content[A2UI_OPERATIONS_KEY] as {
        createSurface?: { catalogId?: string };
      }[];
      expect(ops).toHaveLength(2);
      // The "basic" alias must resolve to the app's registered catalog id,
      // matching what tailwindCatalog is constructed with.
      expect(ops[0].createSurface?.catalogId).toBe(A2UI_CATALOG_ID);
    });

    it("synthesizes a done MCP tool activity from a call_mcp_tool tool call", () => {
      const messages: Message[] = [
        {
          id: "m1",
          role: "assistant",
          content: "",
          toolCalls: [
            {
              id: "tc-mcp",
              type: "function",
              function: {
                name: CALL_MCP_TOOL_NAME,
                arguments: JSON.stringify({
                  server_id: "srv-1",
                  tool_name: "search_web",
                  arguments: {},
                }),
              },
            },
          ],
        },
      ];
      const state = chatReducer(emptyState, resumeSession({ sessionId: "sess-1", messages }));
      expect(state.messages).toHaveLength(2);
      const activityMsg = state.messages[1];
      if (activityMsg.role !== "activity") throw new Error("expected activity message");
      expect(activityMsg.activityType).toBe(TOOL_CALL_ACTIVITY_TYPE);
      expect(activityMsg.id).toBe("tc-mcp");
      const content = activityMsg.content as unknown as ToolCallActivityContent;
      expect(content).toMatchObject({ name: "search_web", status: "done", isMcp: true });
    });

    it("does NOT synthesize activity for an internal tool call", () => {
      const messages: Message[] = [
        {
          id: "m1",
          role: "assistant",
          content: "",
          toolCalls: [
            {
              id: "tc-internal",
              type: "function",
              function: {
                name: "create_workflow_task",
                arguments: JSON.stringify({ title: "do it" }),
              },
            },
          ],
        },
      ];
      const state = chatReducer(emptyState, resumeSession({ sessionId: "sess-1", messages }));
      expect(state.messages).toHaveLength(1);
      expect(state.messages.some((m) => m.role === "activity")).toBe(false);
    });
  });

  describe("syncPolledMessages", () => {
    it("reuses an optimistic user message's id when a polled twin has the same content", () => {
      // The optimistic send carries a client id that never matches the persisted
      // ADK event id; merging by content must keep the rendered object (stable
      // React key) so its bubble is not remounted and re-animated out of view.
      const stateWithOptimistic = {
        ...emptyState,
        sessionId: "sess-1",
        messages: [{ id: "opt-1", role: "user", content: "Do the thing" }] as Message[],
      };
      const polled: Message[] = [
        { id: "adk-u", role: "user", content: "Do the thing" },
        { id: "adk-a", role: "assistant", content: "done" },
      ];
      const state = chatReducer(
        stateWithOptimistic,
        syncPolledMessages({ sessionId: "sess-1", messages: polled })
      );
      expect(state.messages).toHaveLength(2);
      // Stable identity: the prompt keeps the optimistic id, not the polled one.
      expect(state.messages[0].id).toBe("opt-1");
      expect(state.messages[0].content).toBe("Do the thing");
      // No duplicate prompt bubble.
      expect(
        state.messages.filter((m) => m.role === "user" && m.content === "Do the thing")
      ).toHaveLength(1);
      // The polled assistant reply is included (backend stays authoritative).
      expect(state.messages[1].id).toBe("adk-a");
    });

    it("keeps an optimistic user message with no persisted twin visible", () => {
      const stateWithOptimistic = {
        ...emptyState,
        sessionId: "sess-1",
        messages: [{ id: "opt-1", role: "user", content: "just sent" }] as Message[],
      };
      // Brand-new session: the poll's snapshot lags and does not include it yet.
      const state = chatReducer(
        stateWithOptimistic,
        syncPolledMessages({ sessionId: "sess-1", messages: [] })
      );
      expect(state.messages).toHaveLength(1);
      expect(state.messages[0].id).toBe("opt-1");
      expect(state.messages[0].content).toBe("just sent");
    });

    it("appends the un-echoed optimistic send after the polled history", () => {
      const stateWithOptimistic = {
        ...emptyState,
        sessionId: "sess-1",
        messages: [
          { id: "m1", role: "user", content: "earlier" },
          { id: "opt-1", role: "user", content: "just sent" },
        ] as Message[],
      };
      // Poll returns the persisted earlier message but not the just-sent one.
      const polled: Message[] = [{ id: "m1", role: "user", content: "earlier" }];
      const state = chatReducer(
        stateWithOptimistic,
        syncPolledMessages({ sessionId: "sess-1", messages: polled })
      );
      expect(state.messages).toHaveLength(2);
      expect(state.messages[0].id).toBe("m1");
      // The un-echoed optimistic send survives at the tail.
      expect(state.messages[1].id).toBe("opt-1");
    });

    it("with no optimistic messages, applies the polled history and derives pending calls", () => {
      const polled: Message[] = [
        {
          id: "m1",
          role: "assistant",
          content: "",
          toolCalls: [
            {
              id: "tc-pending",
              type: "function",
              function: {
                name: RENDER_A2UI_TOOL_NAME,
                arguments: JSON.stringify({ surfaceId: "surf-new", components: [] }),
              },
            },
          ],
        },
      ];
      const state = chatReducer(
        { ...emptyState, sessionId: "sess-1" },
        syncPolledMessages({ sessionId: "sess-1", messages: polled })
      );
      // Assistant message plus its synthesized A2UI activity (same as resumeSession).
      expect(state.messages).toHaveLength(2);
      expect(state.messages.some((m) => m.role === "activity")).toBe(true);
      expect(state.pendingRenderCalls).toEqual([
        { toolCallId: "tc-pending", surfaceId: "surf-new" },
      ]);
    });
  });

  describe("addUserMessage", () => {
    it("appends user message and sets isRunning true", () => {
      const state = chatReducer(emptyState, addUserMessage({ id: "u1", content: "test" }));
      expect(state.messages).toHaveLength(1);
      expect(state.messages[0].role).toBe("user");
      expect(state.messages[0].content).toBe("test");
      expect(state.isRunning).toBe(true);
    });
  });

  describe("streaming sequence", () => {
    it("accumulates content through start → appendDelta → end", () => {
      let state = chatReducer(emptyState, startAssistantMessage("a1"));
      expect(state.messages[0].content).toBe("");
      expect(state.isStreaming).toBe(true);

      state = chatReducer(state, appendDelta({ messageId: "a1", delta: "Hello" }));
      state = chatReducer(state, appendDelta({ messageId: "a1", delta: " world" }));
      expect(state.messages[0].content).toBe("Hello world");

      state = chatReducer(state, endAssistantMessage());
      expect(state.isStreaming).toBe(false);
    });

    it("appendDelta with unknown messageId is a no-op", () => {
      const state = chatReducer(emptyState, appendDelta({ messageId: "unknown", delta: "x" }));
      expect(state.messages).toHaveLength(0);
    });
  });

  describe("addActivityMessage", () => {
    it("inserts a new activity message", () => {
      const state = chatReducer(
        emptyState,
        addActivityMessage({ id: "act1", activityType: A2UIActivityType, content: { key: "val" } })
      );
      expect(state.messages).toHaveLength(1);
      expect(state.messages[0].role).toBe("activity");
    });

    it("upserts an existing activity message with the same id", () => {
      let state = chatReducer(
        emptyState,
        addActivityMessage({ id: "act1", activityType: A2UIActivityType, content: { v: 1 } })
      );
      state = chatReducer(
        state,
        addActivityMessage({ id: "act1", activityType: A2UIActivityType, content: { v: 2 } })
      );
      expect(state.messages).toHaveLength(1);
      expect((state.messages[0].content as { v: number }).v).toBe(2);
    });
  });

  describe("finishRun", () => {
    it("sets isRunning and isStreaming to false", () => {
      const state = chatReducer({ ...emptyState, isRunning: true, isStreaming: true }, finishRun());
      expect(state.isRunning).toBe(false);
      expect(state.isStreaming).toBe(false);
    });
  });

  describe("setError", () => {
    it("sets error message and stops running/streaming", () => {
      const state = chatReducer(
        { ...emptyState, isRunning: true, isStreaming: true },
        setError("oops")
      );
      expect(state.error).toBe("oops");
      expect(state.isRunning).toBe(false);
      expect(state.isStreaming).toBe(false);
    });
  });

  describe("clearError", () => {
    it("clears error", () => {
      const state = chatReducer({ ...emptyState, error: "oops" }, clearError());
      expect(state.error).toBeNull();
    });
  });

  describe("addPendingRenderCall", () => {
    it("appends a pending render call", () => {
      const state = chatReducer(
        emptyState,
        addPendingRenderCall({ toolCallId: "tc-1", surfaceId: "surf-1" })
      );
      expect(state.pendingRenderCalls).toEqual([{ toolCallId: "tc-1", surfaceId: "surf-1" }]);
    });

    it("appends to existing calls without clobbering", () => {
      const state = chatReducer(
        { ...emptyState, pendingRenderCalls: [{ toolCallId: "tc-1", surfaceId: "surf-1" }] },
        addPendingRenderCall({ toolCallId: "tc-2", surfaceId: null })
      );
      expect(state.pendingRenderCalls).toEqual([
        { toolCallId: "tc-1", surfaceId: "surf-1" },
        { toolCallId: "tc-2", surfaceId: null },
      ]);
    });
  });

  describe("clearPendingRenderCalls", () => {
    it("resets to an empty array", () => {
      const state = chatReducer(
        {
          ...emptyState,
          pendingRenderCalls: [
            { toolCallId: "tc-1", surfaceId: "surf-1" },
            { toolCallId: "tc-2", surfaceId: null },
          ],
        },
        clearPendingRenderCalls()
      );
      expect(state.pendingRenderCalls).toEqual([]);
    });
  });
});
