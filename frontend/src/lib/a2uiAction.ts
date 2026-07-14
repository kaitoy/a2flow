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

/**
 * Discriminator marking a tool result as a genuine user action on a surface.
 * Deliberately distinct from {@link RENDER_ACK_CONTENT}'s `"rendered"` so the
 * backend's sender attribution keeps telling the two apart.
 */
const ACTION_STATUS = "action";

/**
 * The tool result the frontend sends for a `render_a2ui` call the user acted on.
 *
 * Serialized as JSON rather than prose because `ag-ui-adk` wraps any tool result
 * it cannot `json.loads` into `{success, result: <the string>, status: "completed"}`
 * before persisting it to the ADK session. A JSON object survives that round trip
 * byte-for-byte, so {@link parseActionContent} can still recover the submitted
 * values from a reloaded history — a plain sentence cannot.
 */
export interface A2uiActionResult {
  /** Always {@link ACTION_STATUS}; distinguishes a real action from a no-op ack. */
  status: typeof ACTION_STATUS;
  /** The action's name, as declared on the acted-on component. */
  name: string;
  /** The surface the action was performed on. */
  surfaceId: string;
  /** The component that triggered the action, when known. */
  sourceComponentId?: string;
  /** The action context the agent declared in the component's `action.event.context`. */
  context: Record<string, unknown>;
  /**
   * The surface's entire data model at submit time — every value the user typed
   * or selected, keyed by the same paths the components bind to. Unlike
   * {@link A2uiActionResult.context}, this does not depend on the agent having
   * declared any bindings, so it is the only complete record of the input.
   */
  values: Record<string, unknown>;
}

/** What {@link parseActionContent} recovers from a stored action tool result. */
export interface ParsedActionResult {
  /** The action the user performed. */
  action: A2UIUserAction;
  /** The surface's data model at submit time (see {@link A2uiActionResult.values}). */
  values: Record<string, unknown>;
}

/**
 * Serialize a user action, plus the acted-on surface's full data model, into the
 * JSON tool result sent to the agent for the `render_a2ui` call that rendered it.
 *
 * `values` gives the agent the values the user actually entered, which the
 * declared `context` alone does not (it carries only the bindings the agent wrote
 * onto the component).
 */
export function formatActionContent(
  action: A2UIUserAction,
  values: Record<string, unknown> = {}
): string {
  const result: A2uiActionResult = {
    status: ACTION_STATUS,
    name: action.name ?? "unknown_action",
    surfaceId: action.surfaceId ?? "unknown_surface",
    context: action.context ?? {},
    values,
  };
  if (action.sourceComponentId) result.sourceComponentId = action.sourceComponentId;
  return JSON.stringify(result);
}

/** Matches the legacy prose format {@link formatActionContent} used to emit. */
const LEGACY_ACTION_CONTENT_PATTERN =
  /^User performed action "([^"]*)" on surface "([^"]*)"(?: \(component: ([^)]*)\))?\. Context: ([\s\S]*)$/;

/** Narrow an unknown to a plain (non-array, non-null) object. */
function asRecord(value: unknown): Record<string, unknown> | null {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

/** Parse a legacy prose action tool result. Returns `null` when it isn't one. */
function parseLegacyActionContent(content: string): ParsedActionResult | null {
  const match = LEGACY_ACTION_CONTENT_PATTERN.exec(content);
  if (!match) return null;
  const [, name, surfaceId, sourceComponentId, contextRaw] = match;
  let context: Record<string, unknown> | null;
  try {
    context = asRecord(JSON.parse(contextRaw));
  } catch {
    return null;
  }
  if (!context) return null;
  return {
    action: { name, surfaceId, sourceComponentId: sourceComponentId || undefined, context },
    // The prose format never carried the data model, so the declared context is
    // the most a session written before this format change can give back.
    values: context,
  };
}

/**
 * Recover what the user submitted from a `render_a2ui` call's stored tool result,
 * so a resolved surface can be redisplayed pre-filled.
 *
 * Accepts three shapes, in order:
 *
 * 1. The current JSON format ({@link A2uiActionResult}).
 * 2. `ag-ui-adk`'s wrapper around a legacy prose result
 *    (`{success, result: "<prose>", status: "completed"}`) — what sessions written
 *    before the JSON format read back as after a reload.
 * 3. The bare legacy prose string.
 *
 * Returns `null` for anything else, including {@link RENDER_ACK_CONTENT} — a no-op
 * acknowledgement with nothing to recover.
 */
export function parseActionContent(content: string): ParsedActionResult | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(content);
  } catch {
    return parseLegacyActionContent(content);
  }

  const record = asRecord(parsed);
  if (!record) return null;

  if (record.status === ACTION_STATUS) {
    const { name, surfaceId, sourceComponentId } = record;
    return {
      action: {
        name: typeof name === "string" ? name : "unknown_action",
        surfaceId: typeof surfaceId === "string" ? surfaceId : "unknown_surface",
        sourceComponentId: typeof sourceComponentId === "string" ? sourceComponentId : undefined,
        context: asRecord(record.context) ?? {},
      },
      values: asRecord(record.values) ?? {},
    };
  }

  // ag-ui-adk's fallback wrapper for a tool result it could not parse as JSON.
  if (typeof record.result === "string") return parseLegacyActionContent(record.result);

  return null;
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
 * {@link formatActionContent} instead — including `values`, the acted-on
 * surface's full data model — so the agent receives what the user entered and
 * the backend attributes exactly that response to the acting user; the rest
 * still get the no-op acknowledgement. When no pending call matches the action's
 * surface (e.g. its arguments could not be parsed), the last pending call
 * carries the action so it is never silently dropped.
 */
export function buildRenderAckMessages(
  pending: PendingRenderCall[],
  action?: A2UIUserAction,
  values?: Record<string, unknown>
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
      index === actionTargetIndex && action
        ? formatActionContent(action, values ?? {})
        : RENDER_ACK_CONTENT,
  }));
}
