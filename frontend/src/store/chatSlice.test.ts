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
  REASONING_ACTIVITY_TYPE,
  TOOL_CALL_ACTIVITY_TYPE,
  type ToolCallActivityContent,
} from "@/lib/agentActivity";
import type { Message, RenderedMessage } from "./chatSlice";
import chatReducer, {
  addActivityMessage,
  addPendingRenderCall,
  addUserMessage,
  appendDelta,
  attachToolCallResult,
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

    it("overrides a catalogId the agent put in the render_a2ui args", () => {
      // `render_a2ui` has no catalogId parameter and its usage guide tells the
      // agent not to pass one, but the guide's own examples show this id, so the
      // LLM copies it in. A2UIMiddleware's live path discards it in favour of the
      // configured defaultCatalogId; honouring it here instead would rebuild the
      // surface against a catalog this app never registered, and MessageProcessor
      // would throw "Catalog not found" on every poll and reload.
      const messages: Message[] = [
        {
          id: "m1",
          role: "assistant",
          content: "",
          toolCalls: [
            {
              id: "tc-1",
              type: "function",
              function: {
                name: RENDER_A2UI_TOOL_NAME,
                arguments: JSON.stringify({
                  surfaceId: "surface-1",
                  catalogId: "https://a2ui.org/specification/v0_9/basic_catalog.json",
                  components: [{ id: "btn1" }],
                }),
              },
            },
          ],
        },
      ];
      const state = chatReducer(emptyState, resumeSession({ sessionId: "sess-1", messages }));
      const activityMsg = state.messages[1];
      if (activityMsg.role !== "activity") throw new Error("expected activity message");
      const ops = activityMsg.content[A2UI_OPERATIONS_KEY] as {
        createSurface?: { catalogId?: string };
      }[];
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

    it("restores the MCP call's arguments and result from the persisted history", () => {
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
                  arguments: { query: "rust" },
                }),
              },
            },
          ],
        },
        {
          id: "m2",
          role: "tool",
          toolCallId: "tc-mcp",
          content: JSON.stringify({ result: { content: ["ok"], structured: null } }),
        },
      ];
      const state = chatReducer(emptyState, resumeSession({ sessionId: "sess-1", messages }));
      const activityMsg = state.messages.find((m) => m.id === "tc-mcp");
      if (activityMsg?.role !== "activity") {
        throw new Error("expected activity message");
      }
      const content = activityMsg.content as unknown as ToolCallActivityContent;
      // Only the proxied tool's own arguments, not the call_mcp_tool envelope.
      expect(content.args).toEqual({ query: "rust" });
      expect(content.result).toEqual({ result: { content: ["ok"], structured: null } });
      expect(content.mocked).toBe(false);
    });

    it("marks a restored MCP call as mocked when its result says so", () => {
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
                  tool_name: "delete_record",
                  arguments: {},
                }),
              },
            },
          ],
        },
        {
          id: "m2",
          role: "tool",
          toolCallId: "tc-mcp",
          content: JSON.stringify({ result: { content: [], structured: {} }, mocked: true }),
        },
      ];
      const state = chatReducer(emptyState, resumeSession({ sessionId: "sess-1", messages }));
      const activityMsg = state.messages.find((m) => m.id === "tc-mcp");
      if (activityMsg?.role !== "activity") {
        throw new Error("expected activity message");
      }
      expect((activityMsg.content as unknown as ToolCallActivityContent).mocked).toBe(true);
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
    it("keys a rendered message on the id it was drawn under when the polled id differs", () => {
      // Neither an optimistic send (a client id) nor a live-streamed assistant
      // reply (an id the stream minted) matches the persisted ADK event id the
      // history returns. The persisted id wins — the sender and task maps are
      // keyed by it — while the key the bubble is drawn under is carried over,
      // so React does not remount and re-animate the bubbles out of view.
      const stateWithRendered = {
        ...emptyState,
        sessionId: "sess-1",
        messages: [
          { id: "opt-1", role: "user", content: "Do the thing" },
          { id: "live-a", role: "assistant", content: "done" },
        ] as Message[],
      };
      const polled: Message[] = [
        { id: "adk-u", role: "user", content: "Do the thing" },
        { id: "adk-a", role: "assistant", content: "done" },
      ];
      const state = chatReducer(
        stateWithRendered,
        syncPolledMessages({ sessionId: "sess-1", messages: polled })
      );
      expect(state.messages).toHaveLength(2);
      expect(state.messages[0].id).toBe("adk-u");
      expect(state.messages[0].renderKey).toBe("opt-1");
      expect(state.messages[0].content).toBe("Do the thing");
      expect(state.messages[1].id).toBe("adk-a");
      expect(state.messages[1].renderKey).toBe("live-a");
      // No duplicate prompt bubble.
      expect(
        state.messages.filter((m) => m.role === "user" && m.content === "Do the thing")
      ).toHaveLength(1);
    });

    it("carries an assigned render key forward on the next poll", () => {
      // The second poll finds the message under the id the first one gave it, so
      // the match is by id — the key must survive that path too, or the bubble
      // would remount one poll after being reconciled.
      const reconciled = {
        ...emptyState,
        sessionId: "sess-1",
        messages: [
          { id: "adk-u", role: "user", content: "Do the thing", renderKey: "opt-1" },
          { id: "adk-a", role: "assistant", content: "done", renderKey: "live-a" },
        ] as RenderedMessage[],
      };
      const polled: Message[] = [
        { id: "adk-u", role: "user", content: "Do the thing" },
        { id: "adk-a", role: "assistant", content: "done" },
      ];
      const state = chatReducer(
        reconciled,
        syncPolledMessages({ sessionId: "sess-1", messages: polled })
      );
      expect(state.messages.map((m) => m.renderKey)).toEqual(["opt-1", "live-a"]);
    });

    it("does not let an already-drawn message consume a later twin's key", () => {
      // Two turns can say the same thing. The earlier reply is already drawn
      // under its persisted id, so the live-streamed key belongs to the new one.
      const rendered = {
        ...emptyState,
        sessionId: "sess-1",
        messages: [
          { id: "adk-a1", role: "assistant", content: "Done." },
          { id: "live-a2", role: "assistant", content: "Done." },
        ] as Message[],
      };
      const polled: Message[] = [
        { id: "adk-a1", role: "assistant", content: "Done." },
        { id: "adk-a2", role: "assistant", content: "Done." },
      ];
      const state = chatReducer(
        rendered,
        syncPolledMessages({ sessionId: "sess-1", messages: polled })
      );
      expect(state.messages[0].renderKey).toBeUndefined();
      expect(state.messages[1].renderKey).toBe("live-a2");
    });

    it("leaves a polled message's key alone when nothing was rendered under another id", () => {
      // A message this browser never watched appear (another participant's, or
      // anything after a reload) is keyed by its own id, as before.
      const state = chatReducer(
        { ...emptyState, sessionId: "sess-1" },
        syncPolledMessages({
          sessionId: "sess-1",
          messages: [{ id: "adk-u", role: "user", content: "from someone else" }],
        })
      );
      expect(state.messages[0].id).toBe("adk-u");
      expect(state.messages[0].renderKey).toBeUndefined();
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

    it("leaves a run error on screen instead of clearing it on the next poll", () => {
      // A failed run persists no assistant message, so the poll that follows it
      // says nothing about the failure. Clearing here used to wipe the banner a
      // few seconds after it appeared — the only explanation the user gets.
      const errored = {
        ...emptyState,
        sessionId: "sess-1",
        error: "The model provider is unavailable.",
      };
      const state = chatReducer(errored, syncPolledMessages({ sessionId: "sess-1", messages: [] }));
      expect(state.error).toBe("The model provider is unavailable.");
    });

    it("preserves a live tool-call activity chip for an internal tool call across a poll", () => {
      // Reproduces the bug: onToolCallEndEvent (agentSubscriber.ts) adds a live
      // TOOL_CALL_ACTIVITY_TYPE chip for every non-hidden tool call, including
      // internal A2Flow tools that synthesizeActivityMessages intentionally does
      // not reconstruct from history (see the "does NOT synthesize activity for
      // an internal tool call" test above). Without preservation, this poll's
      // wholesale rebuild would silently drop the still-rendered chip.
      const assistantMsg: Message = {
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
      };
      const liveChip: Message = {
        id: "tc-internal",
        role: "activity",
        activityType: TOOL_CALL_ACTIVITY_TYPE,
        content: { name: "create_workflow_task", status: "done" },
      };
      const stateWithLiveChip = {
        ...emptyState,
        sessionId: "sess-1",
        messages: [assistantMsg, liveChip],
      };
      const polled: Message[] = [assistantMsg];
      const state = chatReducer(
        stateWithLiveChip,
        syncPolledMessages({ sessionId: "sess-1", messages: polled })
      );
      expect(state.messages).toHaveLength(2);
      const activityMsg = state.messages[1];
      expect(activityMsg.role).toBe("activity");
      if (activityMsg.role !== "activity") throw new Error("expected activity message");
      expect(activityMsg.activityType).toBe(TOOL_CALL_ACTIVITY_TYPE);
      expect(activityMsg.id).toBe("tc-internal");
      // Stable identity: same object as the live chip, so its React key is
      // unchanged and the bubble is not remounted.
      expect(activityMsg).toBe(liveChip);
    });

    it("keeps the rendered A2UI surface instead of a rebuilt one for the same call", () => {
      // A2uiRenderer re-processes whenever the operations payload changes *by
      // reference*, so handing it an equivalent rebuild blanks the card and
      // builds it again — visibly. Re-using the rendered message keeps that
      // reference (and the React key) exactly as it is.
      const assistantMsg: Message = {
        id: "m1",
        role: "assistant",
        content: "",
        toolCalls: [
          {
            id: "tc-a2ui",
            type: "function",
            function: {
              name: RENDER_A2UI_TOOL_NAME,
              arguments: JSON.stringify({ surfaceId: "surf-1", components: [] }),
            },
          },
        ],
      };
      const liveSurface: Message = {
        id: "a2ui-surface-tc-a2ui",
        role: "activity",
        activityType: A2UIActivityType,
        content: {
          [A2UI_OPERATIONS_KEY]: [{ version: "v0.9", createSurface: { surfaceId: "surf-1" } }],
          [A2UI_SOURCE_TOOL_CALL_ID_KEY]: "tc-a2ui",
        },
      } as Message;
      const state = chatReducer(
        { ...emptyState, sessionId: "sess-1", messages: [assistantMsg, liveSurface] },
        syncPolledMessages({ sessionId: "sess-1", messages: [assistantMsg] })
      );
      expect(state.messages).toHaveLength(2);
      expect(state.messages[1]).toBe(liveSurface);
    });

    it("rebuilds an A2UI surface whose render call the history knows under another id", () => {
      // ADK can remap a long-running client tool's id between the streamed and
      // persisted events. With no live surface to match, the synthesized one is
      // used, exactly as before — which is what keeps the resolved/pending
      // decision consistent with the persisted ids.
      const liveSurface: Message = {
        id: "a2ui-surface-tc-live",
        role: "activity",
        activityType: A2UIActivityType,
        content: {
          [A2UI_OPERATIONS_KEY]: [{ version: "v0.9", createSurface: { surfaceId: "surf-1" } }],
          [A2UI_SOURCE_TOOL_CALL_ID_KEY]: "tc-live",
        },
      } as Message;
      const assistantMsg: Message = {
        id: "m1",
        role: "assistant",
        content: "",
        toolCalls: [
          {
            id: "tc-persisted",
            type: "function",
            function: {
              name: RENDER_A2UI_TOOL_NAME,
              arguments: JSON.stringify({ surfaceId: "surf-1", components: [] }),
            },
          },
        ],
      };
      const state = chatReducer(
        { ...emptyState, sessionId: "sess-1", messages: [assistantMsg, liveSurface] },
        syncPolledMessages({ sessionId: "sess-1", messages: [assistantMsg] })
      );
      expect(state.messages).toHaveLength(2);
      expect(state.messages[1]).not.toBe(liveSurface);
      expect(state.messages[1].id).toBe("a2ui-surface-surf-1-tc-persisted");
    });

    it("keeps a live reasoning panel across a poll", () => {
      // The history returns reasoning as a `reasoning`-role message, which no
      // bubble renders — without preservation the thinking panel would vanish
      // (and the column would jump) on the first poll after the agent used it.
      const livePanel: Message = {
        id: "reasoning-live",
        role: "activity",
        activityType: REASONING_ACTIVITY_TYPE,
        content: { text: "weighing the options" },
      } as Message;
      const polled: Message[] = [
        { id: "ev-1-reasoning", role: "reasoning", content: "weighing the options" },
        { id: "ev-1", role: "assistant", content: "here you go" },
      ];
      const state = chatReducer(
        { ...emptyState, sessionId: "sess-1", messages: [livePanel] },
        syncPolledMessages({ sessionId: "sess-1", messages: polled })
      );
      // The raw reasoning message, the preserved panel, then the reply.
      expect(state.messages).toHaveLength(3);
      expect(state.messages[1]).toBe(livePanel);
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

  describe("attachToolCallResult", () => {
    /** Seed a done tool-call line the way the subscriber's end event does. */
    function stateWithToolCall() {
      return chatReducer(
        emptyState,
        addActivityMessage({
          id: "tc-1",
          activityType: TOOL_CALL_ACTIVITY_TYPE,
          content: { name: "search_web", status: "done", isMcp: true, args: { q: "rust" } },
        })
      );
    }

    it("merges the result into the line without losing its name or arguments", () => {
      const state = chatReducer(
        stateWithToolCall(),
        attachToolCallResult({ toolCallId: "tc-1", result: { ok: true } })
      );
      const content = state.messages[0].content as unknown as ToolCallActivityContent;
      expect(content).toMatchObject({
        name: "search_web",
        status: "done",
        isMcp: true,
        args: { q: "rust" },
        result: { ok: true },
        mocked: false,
      });
    });

    it("marks the line as mocked when the result says so", () => {
      const state = chatReducer(
        stateWithToolCall(),
        attachToolCallResult({ toolCallId: "tc-1", result: { mocked: true } })
      );
      expect((state.messages[0].content as unknown as ToolCallActivityContent).mocked).toBe(true);
    });

    it("ignores a result for a call with no rendered line", () => {
      const state = chatReducer(
        emptyState,
        attachToolCallResult({ toolCallId: "unknown", result: { ok: true } })
      );
      expect(state.messages).toHaveLength(0);
    });

    it("ignores a result addressed to a non-tool activity message", () => {
      const seeded = chatReducer(
        emptyState,
        addActivityMessage({ id: "act1", activityType: A2UIActivityType, content: { v: 1 } })
      );
      const state = chatReducer(
        seeded,
        attachToolCallResult({ toolCallId: "act1", result: { ok: true } })
      );
      expect(state.messages[0].content).toEqual({ v: 1 });
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
