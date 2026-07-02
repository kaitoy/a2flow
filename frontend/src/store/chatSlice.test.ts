import {
  A2UI_OPERATIONS_KEY,
  A2UIActivityType,
  RENDER_A2UI_TOOL_NAME,
} from "@ag-ui/a2ui-middleware";
import { describe, expect, it } from "vitest";
import { A2UI_CATALOG_ID } from "@/lib/a2uiCatalogId";
import {
  CALL_MCP_TOOL_NAME,
  TOOL_CALL_ACTIVITY_TYPE,
  type ToolCallActivityContent,
} from "@/lib/agentActivity";
import type { Message } from "./chatSlice";
import chatReducer, {
  addActivityMessage,
  addPendingRenderToolCallId,
  addUserMessage,
  appendDelta,
  clearError,
  clearPendingRenderToolCallIds,
  endAssistantMessage,
  finishRun,
  resumeSession,
  setError,
  setSession,
  startAssistantMessage,
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
      expect(state.pendingRenderToolCallIds).toEqual([]);
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
      expect(state.pendingRenderToolCallIds).toEqual([]);
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

  describe("addPendingRenderToolCallId", () => {
    it("appends a tool call id", () => {
      const state = chatReducer(emptyState, addPendingRenderToolCallId("tc-1"));
      expect(state.pendingRenderToolCallIds).toEqual(["tc-1"]);
    });

    it("appends to existing ids without clobbering", () => {
      const state = chatReducer(
        { ...emptyState, pendingRenderToolCallIds: ["tc-1"] },
        addPendingRenderToolCallId("tc-2")
      );
      expect(state.pendingRenderToolCallIds).toEqual(["tc-1", "tc-2"]);
    });
  });

  describe("clearPendingRenderToolCallIds", () => {
    it("resets to an empty array", () => {
      const state = chatReducer(
        { ...emptyState, pendingRenderToolCallIds: ["tc-1", "tc-2"] },
        clearPendingRenderToolCallIds()
      );
      expect(state.pendingRenderToolCallIds).toEqual([]);
    });
  });
});
