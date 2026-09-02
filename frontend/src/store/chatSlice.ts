import {
  A2UI_OPERATIONS_KEY,
  A2UIActivityType,
  RENDER_A2UI_TOOL_NAME,
} from "@ag-ui/a2ui-middleware";
import type { Message } from "@ag-ui/core";
import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { PendingRenderCall } from "@/lib/a2uiAction";
import { A2UI_CATALOG_ID } from "@/lib/a2uiCatalogId";
import {
  A2UI_SOURCE_TOOL_CALL_ID_KEY,
  CALL_MCP_TOOL_NAME,
  getToolCallArguments,
  getToolDisplayName,
  isMockedResult,
  parseToolResult,
  REASONING_ACTIVITY_TYPE,
  type ReasoningActivityContent,
  TOOL_CALL_ACTIVITY_TYPE,
} from "@/lib/agentActivity";
import { APPROVAL_ACTIVITY_TYPE, RENDER_APPROVAL_TOOL_NAME } from "@/lib/approvalTool";

export type { Message };

/**
 * A chat message plus the React key its bubble is rendered under.
 *
 * `id` is always the message's own id, which everything that addresses a message
 * from outside the store is keyed by -- the sender attribution and the
 * per-message task association both come back from `/messages` keyed by the ADK
 * event id. `renderKey` is set only when that id changed under a bubble that was
 * already on screen: the live stream numbers an assistant reply with an id it
 * mints itself, and the persisted history returns the same reply under the ADK
 * event id instead. Following that swap with the React key remounts the bubble --
 * replaying its entrance animation, resetting its rendered Markdown, and
 * rebuilding any A2UI surface inside it -- which is the visible judder a poll
 * used to cause even when it brought no news. See {@link syncPolledMessages}.
 */
export type RenderedMessage = Message & { renderKey?: string };

/** Parse a tool call's arguments into a plain object, or return null on failure. */
function parseToolArgs(args: unknown): Record<string, unknown> | null {
  try {
    return JSON.parse(typeof args === "string" ? args : JSON.stringify(args));
  } catch {
    return null;
  }
}

/**
 * Derive a stable comparison key for a conversational message's content.
 *
 * `syncPolledMessages` matches an already-rendered user or assistant message to
 * its polled twin by content, because their ids differ. Plain-text prompts and
 * replies compare directly; content-part arrays (media inputs) are serialized so
 * the same comparison works for them too. Content-free messages (an assistant
 * turn that only called tools) key to the empty string, which the caller treats
 * as "nothing to match on".
 */
function contentKey(content: unknown): string {
  if (content == null) return "";
  return typeof content === "string" ? content : JSON.stringify(content);
}

/**
 * Reconstruct an approval activity message from a `render_approval` tool call.
 *
 * Mirrors the live-streaming path (which dispatches an activity message keyed by
 * the tool call id) so resumed sessions show the approve/reject controls again.
 */
function synthesizeApprovalActivityMessage(
  toolCallId: string,
  args: Record<string, unknown>
): Message | null {
  const { approvalId, title, description } = args as {
    approvalId?: string;
    title?: string;
    description?: string;
  };
  if (!approvalId) return null;
  return {
    id: toolCallId,
    role: "activity",
    activityType: APPROVAL_ACTIVITY_TYPE,
    content: { approvalId, title, description },
  } as Message;
}

/** Reconstruct an A2UI activity message from a RENDER_A2UI tool call's args. */
function synthesizeA2UIActivityMessage(
  toolCallId: string,
  args: Record<string, unknown>
): Message | null {
  const { surfaceId, components, data } = args as {
    surfaceId?: string;
    components?: unknown[];
    data?: unknown;
  };
  if (!surfaceId) return null;
  // The catalog is the host's to choose, never the agent's: A2UIMiddleware is
  // configured with `defaultCatalogId`, and its live path lets that win over any
  // `catalogId` in the tool-call args. Mirror that here rather than reading the
  // args back. `render_a2ui` has no `catalogId` parameter and its usage guide
  // says not to pass one, but the guide's own examples show a `catalogId` of
  // "https://a2ui.org/specification/v0_9/basic_catalog.json", so the LLM copies
  // it into the args anyway. Honoring it would resolve against a catalog id this
  // app never registered — the live surface renders, then this rebuild (a poll or
  // a reload) throws `Catalog not found` and the surface vanishes.
  const ops: Record<string, unknown>[] = [
    { version: "v0.9", createSurface: { surfaceId, catalogId: A2UI_CATALOG_ID } },
    { version: "v0.9", updateComponents: { surfaceId, components: components ?? [] } },
  ];
  if (data != null) ops.push({ version: "v0.9", updateDataModel: { surfaceId, value: data } });
  return {
    // Unique per render call so addActivityMessage's upsert logic (which
    // matches by id) works correctly if the same surface is re-synthesized.
    // Live streaming uses `a2ui-surface-${toolCallId}`; the two never coexist
    // for the same surface because a resume rebuilds the whole message list.
    id: `a2ui-surface-${surfaceId}-${toolCallId}`,
    role: "activity",
    activityType: A2UIActivityType,
    // Stamped alongside the ops so the UI can look up who resolved this
    // render call (see A2UI_SOURCE_TOOL_CALL_ID_KEY) without parsing it back
    // out of the id above, whose format differs from the live-streaming path.
    content: { [A2UI_OPERATIONS_KEY]: ops, [A2UI_SOURCE_TOOL_CALL_ID_KEY]: toolCallId },
  } as Message;
}

/**
 * Reconstruct a completed tool-call activity message from a `call_mcp_tool` call.
 *
 * Only user-added MCP tool calls (always routed through the `call_mcp_tool`
 * proxy) are reproduced on resume; internal A2Flow tool calls are intentionally
 * left out so they stay live-only. The line is shown under the real MCP tool
 * name carried in the call's `tool_name` argument.
 */
function synthesizeMcpToolActivityMessage(
  toolCallId: string,
  args: Record<string, unknown>,
  rawResult: string | undefined
): Message {
  const result = rawResult === undefined ? undefined : parseToolResult(rawResult);
  return {
    id: toolCallId,
    role: "activity",
    activityType: TOOL_CALL_ACTIVITY_TYPE,
    content: {
      name: getToolDisplayName(CALL_MCP_TOOL_NAME, args),
      status: "done",
      isMcp: true,
      args: getToolCallArguments(CALL_MCP_TOOL_NAME, args),
      result,
      mocked: isMockedResult(result),
    },
  } as Message;
}

/**
 * Index a persisted history's tool results by the call each one answers.
 *
 * Results are separate `tool` messages rather than fields of the assistant
 * message that made the call, so rebuilding a call's activity line means
 * looking its answer up here.
 *
 * @param messages - The persisted message history.
 * @returns The raw result content, keyed by tool call id.
 */
function toolResultsByCallId(messages: Message[]): Map<string, string> {
  const byId = new Map<string, string>();
  for (const msg of messages) {
    if (msg.role === "tool" && msg.toolCallId && typeof msg.content === "string") {
      byId.set(msg.toolCallId, msg.content);
    }
  }
  return byId;
}

/**
 * Derive the `render_a2ui` calls still awaiting an acknowledging tool result
 * from a persisted message history.
 *
 * A render call is pending when no `tool` message answers its id (the same
 * rule as the A2UI middleware's `findPendingToolCalls`). Because the history
 * is the source of truth, this re-derivation also restores pending calls that
 * live streaming never saw in this browser — after a page reload, or when
 * another participant's run rendered the surface — so a user action can always
 * be delivered as the acted-on call's tool result.
 */
function derivePendingRenderCalls(messages: Message[]): PendingRenderCall[] {
  const answeredIds = new Set<string>();
  for (const msg of messages) {
    if (msg.role === "tool" && msg.toolCallId) answeredIds.add(msg.toolCallId);
  }
  const pending: PendingRenderCall[] = [];
  for (const msg of messages) {
    if (msg.role !== "assistant" || !msg.toolCalls) continue;
    for (const tc of msg.toolCalls) {
      if (tc.function.name !== RENDER_A2UI_TOOL_NAME || answeredIds.has(tc.id)) continue;
      const args = parseToolArgs(tc.function.arguments);
      const surfaceId = typeof args?.surfaceId === "string" ? args.surfaceId : null;
      pending.push({ toolCallId: tc.id, surfaceId });
    }
  }
  return pending;
}

/**
 * The activity messages already on screen that a poll should re-use instead of
 * replacing with an equivalent rebuild.
 *
 * Every entry exists to keep something the viewer is already looking at exactly
 * where it is: a rebuilt message is a different object under a different React
 * key, and remounting its bubble is visible. {@link syncPolledMessages} builds
 * this index from the rendered messages; {@link resumeSession} passes none,
 * since a resume has nothing on screen to preserve.
 */
interface RenderedActivityIndex {
  /**
   * Live-only tool-call chips, by the tool call each reports. An internal A2Flow
   * tool call has no persisted representation to rebuild from (see
   * {@link synthesizeActivityMessages}), so without this a poll would silently
   * drop a chip that is still on screen.
   */
  toolChipByCallId: Map<string, RenderedMessage>;
  /**
   * Rendered A2UI surfaces, by the `render_a2ui` call that produced them.
   * Re-using the rendered message keeps its operations payload identical *by
   * reference*, which is what stops `A2uiRenderer` from tearing the surface down
   * and rebuilding it — it re-processes whenever that reference changes, so a
   * rebuilt payload makes the card blink out and back in.
   */
  a2uiSurfaceByCallId: Map<string, RenderedMessage>;
  /**
   * Live reasoning panels, bucketed by their text (duplicates line up in order).
   * The persisted history returns reasoning as a `reasoning`-role message, which
   * renders nothing, so the panel would otherwise vanish on the first poll after
   * the agent thought out loud.
   */
  reasoningByText: Map<string, RenderedMessage[]>;
}

/**
 * Reconstruct activity messages from the client-tool calls embedded in assistant messages.
 *
 * When resuming a session, the backend returns raw AG-UI messages. Tool calls are stored on
 * assistant messages, not as standalone activity messages. This generator re-synthesizes the
 * activity messages — A2UI surfaces (``render_a2ui``), approval controls (``render_approval``),
 * and user-added MCP tool calls (``call_mcp_tool``) — so resumed sessions display them
 * identically to live sessions. Internal A2Flow tool calls are intentionally not reproduced
 * this way: their live-only chip normally has no persisted representation to rebuild from.
 *
 * When {@link rendered} is supplied, an already-rendered message is re-yielded in place of the
 * rebuild wherever the index has one — an internal tool chip (which has nothing to rebuild
 * from), an A2UI surface (whose rebuilt payload would restart the renderer), and a reasoning
 * panel (which the persisted history cannot express). This is how {@link syncPolledMessages}
 * leaves the screen untouched across a poll. {@link resumeSession} omits the index, so a fresh
 * resume behaves exactly as before.
 *
 * The synthesized message IDs mirror the ones used during live streaming so
 * ``addActivityMessage``'s upsert logic works.
 */
function* synthesizeActivityMessages(
  messages: Message[],
  rendered?: RenderedActivityIndex
): Generator<RenderedMessage> {
  const resultsByCallId = toolResultsByCallId(messages);
  for (const msg of messages) {
    yield msg;
    if (msg.role === "reasoning") {
      // The raw message just yielded renders nothing; the live panel holds the text.
      const preserved = rendered?.reasoningByText.get(msg.content)?.shift();
      if (preserved) yield preserved;
      continue;
    }
    if (msg.role !== "assistant" || !msg.toolCalls) continue;
    for (const tc of msg.toolCalls) {
      if (
        tc.function.name !== RENDER_A2UI_TOOL_NAME &&
        tc.function.name !== RENDER_APPROVAL_TOOL_NAME &&
        tc.function.name !== CALL_MCP_TOOL_NAME
      ) {
        const preserved = rendered?.toolChipByCallId.get(tc.id);
        if (preserved) yield preserved;
        continue;
      }
      const args = parseToolArgs(tc.function.arguments);
      if (args === null) continue;
      let synthesized: RenderedMessage | null = null;
      if (tc.function.name === RENDER_A2UI_TOOL_NAME) {
        synthesized =
          rendered?.a2uiSurfaceByCallId.get(tc.id) ?? synthesizeA2UIActivityMessage(tc.id, args);
      } else if (tc.function.name === RENDER_APPROVAL_TOOL_NAME) {
        synthesized = synthesizeApprovalActivityMessage(tc.id, args);
      } else if (tc.function.name === CALL_MCP_TOOL_NAME) {
        synthesized = synthesizeMcpToolActivityMessage(tc.id, args, resultsByCallId.get(tc.id));
      }
      if (synthesized) yield synthesized;
    }
  }
}

/**
 * Index the activity messages currently on screen into a {@link RenderedActivityIndex}.
 *
 * @param messages - The rendered message list (the store's own).
 * @returns The lookups {@link synthesizeActivityMessages} re-uses.
 */
function indexRenderedActivity(messages: RenderedMessage[]): RenderedActivityIndex {
  const index: RenderedActivityIndex = {
    toolChipByCallId: new Map(),
    a2uiSurfaceByCallId: new Map(),
    reasoningByText: new Map(),
  };
  for (const msg of messages) {
    if (msg.role !== "activity") continue;
    if (msg.activityType === TOOL_CALL_ACTIVITY_TYPE) {
      index.toolChipByCallId.set(msg.id, msg);
    } else if (msg.activityType === A2UIActivityType) {
      const source = msg.content[A2UI_SOURCE_TOOL_CALL_ID_KEY];
      if (typeof source === "string") index.a2uiSurfaceByCallId.set(source, msg);
    } else if (msg.activityType === REASONING_ACTIVITY_TYPE) {
      const text = (msg.content as unknown as ReasoningActivityContent).text ?? "";
      const bucket = index.reasoningByText.get(text);
      if (bucket) bucket.push(msg);
      else index.reasoningByText.set(text, [msg]);
    }
  }
  return index;
}

/** Redux state shape for the active chat session. */
interface ChatState {
  /** All messages in the current session (user, assistant, and activity). */
  messages: RenderedMessage[];
  /** The active ADK session ID, or null when no session is open. */
  sessionId: string | null;
  /** True while an agent run is in progress (blocks sending new messages). */
  isRunning: boolean;
  /** True while the assistant is actively streaming text tokens. */
  isStreaming: boolean;
  /** Non-null when the last agent run produced an error. */
  error: string | null;
  /** render_a2ui calls awaiting an acknowledging tool result on the next agent run. */
  pendingRenderCalls: PendingRenderCall[];
}

const initialState: ChatState = {
  messages: [],
  sessionId: null,
  isRunning: false,
  isStreaming: false,
  error: null,
  pendingRenderCalls: [],
};

const chatSlice = createSlice({
  name: "chat",
  initialState,
  reducers: {
    setSession(state, action: PayloadAction<string | null>) {
      state.sessionId = action.payload;
      state.messages = [];
      state.isRunning = false;
      state.isStreaming = false;
      state.error = null;
      state.pendingRenderCalls = [];
    },
    resumeSession(state, action: PayloadAction<{ sessionId: string; messages: Message[] }>) {
      state.sessionId = action.payload.sessionId;
      state.messages = [...synthesizeActivityMessages(action.payload.messages)];
      state.isRunning = false;
      state.isStreaming = false;
      state.error = null;
      // The persisted history is the source of truth for unacknowledged render
      // calls: re-deriving them keeps calls still pending across a resume, and
      // restores calls this browser never streamed (page reload, or a surface
      // rendered by another participant's run) so a later user action can
      // still be delivered as the acted-on call's tool result.
      state.pendingRenderCalls = derivePendingRenderCalls(action.payload.messages);
    },
    /**
     * Merge a freshly polled history into the rendered messages without
     * disturbing anything already on screen.
     *
     * The poll's `/messages` response is authoritative for everything it
     * contains, so it is the base of the merged list (run through
     * `synthesizeActivityMessages`, exactly like {@link resumeSession}). What it
     * is *not* authoritative about is React identity: a message this viewer has
     * already watched appear comes back under a different id — an optimistic
     * send under its client-generated id, an assistant reply under the id the
     * live stream minted rather than the ADK event id. Replacing the whole array
     * (`resumeSession`) therefore swaps those bubbles' keys and remounts them,
     * which replays the entrance animation, drops rendered Markdown back to
     * plain text for a frame, and restarts every A2UI surface — the judder a
     * poll used to cause even when it brought no news.
     *
     * So the polled message wins on content and on `id` (which the sender and
     * task attribution are keyed by), while the key its bubble is already drawn
     * under is carried over as `renderKey`: by id for messages an earlier poll
     * already reconciled, and by role + content for the ones the backend has
     * only just echoed back. Activity messages the history cannot express are
     * re-used wholesale instead (see {@link RenderedActivityIndex}), and
     * optimistic sends the backend has not surfaced yet stay at the tail until a
     * later poll reconciles them.
     */
    syncPolledMessages(state, action: PayloadAction<{ sessionId: string; messages: Message[] }>) {
      state.sessionId = action.payload.sessionId;
      const polled = action.payload.messages;
      const polledIds = new Set(polled.map((m) => m.id));
      // Keys an earlier poll already settled on, carried forward by id so a
      // second poll doesn't undo the first one's reconciliation.
      const renderKeyById = new Map<string, string>();
      for (const m of state.messages) if (m.renderKey) renderKeyById.set(m.id, m.renderKey);
      // Conversational messages on screen under an id the polled snapshot
      // doesn't know: this viewer's un-echoed optimistic sends, and every
      // assistant reply the live stream numbered itself. Bucketed by role +
      // content so a polled twin can adopt the key its bubble already has;
      // repeated content lines up in order via shift(). Content-free messages
      // are left out — there is nothing to match them on.
      const rekeyable = new Map<string, RenderedMessage[]>();
      for (const m of state.messages) {
        if ((m.role !== "user" && m.role !== "assistant") || polledIds.has(m.id)) continue;
        const key = contentKey(m.content);
        if (!key) continue;
        const bucket = rekeyable.get(`${m.role}:${key}`);
        if (bucket) bucket.push(m);
        else rekeyable.set(`${m.role}:${key}`, [m]);
      }
      // The shared chat is append-only, so the only user messages missing from
      // the polled snapshot by id are this viewer's un-echoed optimistic sends.
      const optimistic = state.messages.filter((m) => m.role === "user" && !polledIds.has(m.id));
      // A polled message already drawn under its own id needs no rekeying, and
      // must not consume a bucket entry meant for a later one — two turns can
      // easily say the same thing ("Done."), and matching the earlier of them
      // would swap both bubbles' keys instead of neither.
      const renderedIds = new Set(state.messages.map((m) => m.id));
      const consumed = new Set<RenderedMessage>();
      const merged: RenderedMessage[] = [];
      for (const m of synthesizeActivityMessages(polled, indexRenderedActivity(state.messages))) {
        if ((m.role === "user" || m.role === "assistant") && !renderedIds.has(m.id)) {
          const twin = rekeyable.get(`${m.role}:${contentKey(m.content)}`)?.shift();
          if (twin) {
            // Keep the polled message, but under the key it is already drawn
            // under — same bubble, no remount.
            merged.push({ ...m, renderKey: twin.renderKey ?? twin.id });
            consumed.add(twin);
            continue;
          }
        }
        const carried = renderKeyById.get(m.id);
        merged.push(carried === undefined ? m : { ...m, renderKey: carried });
      }
      // Optimistic sends with no persisted twin yet (the just-sent prompt on a
      // brand-new session, or a lagging snapshot) stay visible, in send order.
      for (const m of optimistic) if (!consumed.has(m)) merged.push(m);
      state.messages = merged;
      state.isRunning = false;
      state.isStreaming = false;
      // Deliberately not clearing `error`: a failed run persists no assistant
      // message, so the poll that follows it carries no news about the failure
      // — clearing here just made the banner vanish a few seconds after it
      // appeared, which is the whole explanation the user gets. The banner has
      // a dismiss button, and `addUserMessage` / `startRun` clear it when the
      // user tries again.
      state.pendingRenderCalls = derivePendingRenderCalls(polled);
    },
    addUserMessage(state, action: PayloadAction<{ id: string; content: string }>) {
      state.messages.push({
        id: action.payload.id,
        role: "user",
        content: action.payload.content,
      });
      state.isRunning = true;
      state.error = null;
    },
    startAssistantMessage(state, action: PayloadAction<string>) {
      state.messages.push({
        id: action.payload,
        role: "assistant",
        content: "",
      });
      state.isStreaming = true;
    },
    appendDelta(state, action: PayloadAction<{ messageId: string; delta: string }>) {
      const msg = state.messages.find((m) => m.id === action.payload.messageId);
      if (msg && msg.role === "assistant") msg.content = (msg.content ?? "") + action.payload.delta;
    },
    endAssistantMessage(state) {
      state.isStreaming = false;
    },
    addActivityMessage(
      state,
      action: PayloadAction<{ id: string; activityType: string; content: Record<string, unknown> }>
    ) {
      const existing = state.messages.find((m) => m.id === action.payload.id);
      if (existing && existing.role === "activity") {
        existing.content = action.payload.content;
      } else {
        state.messages.push({
          id: action.payload.id,
          role: "activity",
          activityType: action.payload.activityType,
          content: action.payload.content,
        });
      }
    },
    /**
     * Attach a tool's result to the activity line already rendered for that call.
     *
     * Merged rather than replaced: the line's name, status, and arguments were
     * set by the earlier start/end events and must survive. A result for a call
     * with no line — a hidden tool such as `render_a2ui`, which has its own UI —
     * is ignored.
     */
    attachToolCallResult(state, action: PayloadAction<{ toolCallId: string; result: unknown }>) {
      const existing = state.messages.find((m) => m.id === action.payload.toolCallId);
      if (!existing || existing.role !== "activity") return;
      if (existing.activityType !== TOOL_CALL_ACTIVITY_TYPE) return;
      const content = (existing.content ?? {}) as Record<string, unknown>;
      existing.content = {
        ...content,
        result: action.payload.result,
        mocked: isMockedResult(action.payload.result),
      };
    },
    startRun(state) {
      state.isRunning = true;
      state.error = null;
    },
    finishRun(state) {
      state.isRunning = false;
      state.isStreaming = false;
    },
    setError(state, action: PayloadAction<string>) {
      state.error = action.payload;
      state.isRunning = false;
      state.isStreaming = false;
    },
    clearError(state) {
      state.error = null;
    },
    addPendingRenderCall(state, action: PayloadAction<PendingRenderCall>) {
      state.pendingRenderCalls.push(action.payload);
    },
    clearPendingRenderCalls(state) {
      state.pendingRenderCalls = [];
    },
  },
});

export const {
  setSession,
  resumeSession,
  syncPolledMessages,
  addUserMessage,
  startAssistantMessage,
  appendDelta,
  endAssistantMessage,
  addActivityMessage,
  attachToolCallResult,
  startRun,
  finishRun,
  setError,
  clearError,
  addPendingRenderCall,
  clearPendingRenderCalls,
} = chatSlice.actions;

export default chatSlice.reducer;
