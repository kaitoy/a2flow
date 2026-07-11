import type { A2UIUserAction } from "@ag-ui/a2ui-middleware";

/**
 * No-op acknowledgement content sent as the tool result of a `render_a2ui` call
 * the user never acted on. Mirrors the synthetic acknowledgement
 * `@ag-ui/a2ui-middleware` itself emits for unanswered render calls
 * (`JSON.stringify({status:"rendered"})`), and doubles as a marker the backend
 * uses to skip sender attribution for these responses — only genuine user
 * actions are attributed (see `record_new_senders` in
 * `backend/services/workflow_session.py`).
 */
export const RENDER_ACK_CONTENT = JSON.stringify({ status: "rendered" });

/**
 * A `render_a2ui` tool call still awaiting its acknowledging tool result on the
 * next agent run. `surfaceId` is parsed from the call's arguments (null when
 * unavailable) and lets a user action target the render call that produced the
 * acted-on surface.
 */
export interface PendingRenderCall {
  /** Id of the pending `render_a2ui` tool call. */
  toolCallId: string;
  /** The A2UI surface the call rendered, or null when not parseable. */
  surfaceId: string | null;
}

/** Serialize an A2UIUserAction into a human-readable string sent as a tool result to the agent. */
export function formatActionContent(action: A2UIUserAction): string {
  const name = action.name ?? "unknown_action";
  const surfaceId = action.surfaceId ?? "unknown_surface";
  let text = `User performed action "${name}" on surface "${surfaceId}"`;
  if (action.sourceComponentId) text += ` (component: ${action.sourceComponentId})`;
  text += `. Context: ${action.context ? JSON.stringify(action.context) : "{}"}`;
  return text;
}

/** Matches {@link formatActionContent}'s template so its output can be parsed back apart. */
const ACTION_CONTENT_PATTERN =
  /^User performed action "([^"]*)" on surface "([^"]*)"(?: \(component: ([^)]*)\))?\. Context: ([\s\S]*)$/;

/**
 * Parse {@link formatActionContent}'s output back into the `A2UIUserAction` it was built
 * from, so a resolved surface can recover what the user submitted. Returns `null` when
 * `content` doesn't match the format (e.g. it's {@link RENDER_ACK_CONTENT}, a no-op
 * acknowledgement with nothing to recover) or its trailing context isn't valid JSON.
 */
export function parseActionContent(content: string): A2UIUserAction | null {
  const match = ACTION_CONTENT_PATTERN.exec(content);
  if (!match) return null;
  const [, name, surfaceId, sourceComponentId, contextRaw] = match;
  let context: Record<string, unknown> | undefined;
  try {
    const parsed: unknown = JSON.parse(contextRaw);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    context = parsed as Record<string, unknown>;
  } catch {
    return null;
  }
  return { name, surfaceId, sourceComponentId: sourceComponentId || undefined, context };
}

/** A single A2UI v0.9 operation, as produced by `render_a2ui` tool-call args. */
interface A2uiOp {
  version?: string;
  createSurface?: { surfaceId: string };
  updateDataModel?: { surfaceId: string; value?: unknown };
}

/**
 * Return a copy of an A2UI ops `payload` with `values` shallow-merged on top of its
 * surface's data model, so a resolved surface can be redisplayed pre-filled with what
 * the user actually submitted. No-op (returns `payload` unchanged) when the payload
 * isn't a recognizable ops array, has no `createSurface` op, or `values` is empty.
 * Never mutates `payload` — the caller relies on referential equality to avoid
 * rebuilding the surface on every render.
 */
export function mergeRecoveredValuesIntoPayload(
  payload: unknown,
  values: Record<string, unknown>
): unknown {
  if (!Array.isArray(payload) || Object.keys(values).length === 0) return payload;
  const ops = payload as A2uiOp[];
  const surfaceId = ops.find((op) => op.createSurface)?.createSurface?.surfaceId;
  if (!surfaceId) return payload;

  const dataOpIndex = ops.findIndex((op) => op.updateDataModel?.surfaceId === surfaceId);
  const existingValue = ops[dataOpIndex]?.updateDataModel?.value;
  const mergedOp: A2uiOp = {
    version: ops[0]?.version ?? "v0.9",
    updateDataModel: {
      surfaceId,
      value: {
        ...(existingValue && typeof existingValue === "object" ? existingValue : {}),
        ...values,
      },
    },
  };
  return dataOpIndex >= 0
    ? ops.map((op, i) => (i === dataOpIndex ? mergedOp : op))
    : [...ops, mergedOp];
}

/**
 * Build the tool-result messages that acknowledge every pending `render_a2ui`
 * call on the next agent run.
 *
 * Without an `action`, every pending call gets the no-op
 * {@link RENDER_ACK_CONTENT}. With an `action`, the last pending call whose
 * `surfaceId` matches the acted-on surface carries
 * {@link formatActionContent} instead, so the backend attributes exactly that
 * response to the acting user; the rest still get the no-op acknowledgement.
 * When no pending call matches the action's surface (e.g. its arguments could
 * not be parsed), the last pending call carries the action so it is never
 * silently dropped.
 */
export function buildRenderAckMessages(
  pending: PendingRenderCall[],
  action?: A2UIUserAction
): Array<{ id: string; role: "tool"; toolCallId: string; content: string }> {
  let actionTargetIndex = -1;
  if (action && pending.length > 0) {
    actionTargetIndex = pending.findLastIndex((call) => call.surfaceId === action.surfaceId);
    if (actionTargetIndex === -1) actionTargetIndex = pending.length - 1;
  }
  return pending.map((call, index) => ({
    id: crypto.randomUUID(),
    role: "tool",
    toolCallId: call.toolCallId,
    content:
      index === actionTargetIndex && action ? formatActionContent(action) : RENDER_ACK_CONTENT,
  }));
}
