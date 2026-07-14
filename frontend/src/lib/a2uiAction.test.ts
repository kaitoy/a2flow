import { describe, expect, it } from "vitest";
import {
  buildRenderAckMessages,
  formatActionContent,
  mergeRecoveredValuesIntoPayload,
  parseActionContent,
  RENDER_ACK_CONTENT,
} from "./a2uiAction";

/**
 * How `ag-ui-adk` persists a tool result it cannot parse as JSON: the raw string
 * is wrapped, so this is what a legacy prose result reads back as after a reload.
 */
function adkWrapped(content: string): string {
  return JSON.stringify({ success: true, result: content, status: "completed" });
}

describe("formatActionContent", () => {
  it("emits valid JSON so ag-ui-adk stores it verbatim instead of wrapping it", () => {
    const content = formatActionContent(
      { name: "confirm", surfaceId: "result", sourceComponentId: "btn", context: {} },
      { email: "a@b.c" }
    );
    expect(() => JSON.parse(content) as unknown).not.toThrow();
    expect(JSON.parse(content)).toMatchObject({ status: "action", values: { email: "a@b.c" } });
  });

  it("never collides with the no-op acknowledgement's status", () => {
    const content = formatActionContent({ name: "confirm", surfaceId: "result" }, {});
    expect(content).not.toEqual(RENDER_ACK_CONTENT);
    expect((JSON.parse(content) as { status: string }).status).toBe("action");
  });
});

describe("parseActionContent", () => {
  it("round-trips formatActionContent's output, including the submitted values", () => {
    const action = {
      name: "confirm",
      surfaceId: "result",
      sourceComponentId: "btn",
      context: { userName: "Alice" },
    };
    const values = { userName: "Alice", plan: ["pro"], nested: { note: "hi" } };
    const parsed = parseActionContent(formatActionContent(action, values));
    expect(parsed).toEqual({ action, values });
  });

  it("recovers a missing sourceComponentId as undefined", () => {
    const action = { name: "confirm", surfaceId: "result", context: {} };
    const parsed = parseActionContent(formatActionContent(action, {}));
    expect(parsed?.action.sourceComponentId).toBeUndefined();
  });

  it("defaults values to an empty object when the stored result has none", () => {
    const content = JSON.stringify({ status: "action", name: "go", surfaceId: "s1" });
    expect(parseActionContent(content)).toEqual({
      action: { name: "go", surfaceId: "s1", sourceComponentId: undefined, context: {} },
      values: {},
    });
  });

  it("recovers the legacy prose format's context as its values", () => {
    const content =
      'User performed action "confirm" on surface "result" (component: btn). Context: {"userName":"Alice"}';
    expect(parseActionContent(content)).toEqual({
      action: {
        name: "confirm",
        surfaceId: "result",
        sourceComponentId: "btn",
        context: { userName: "Alice" },
      },
      values: { userName: "Alice" },
    });
  });

  it("unwraps ag-ui-adk's wrapper around a legacy prose result", () => {
    const content = adkWrapped(
      'User performed action "confirm" on surface "result". Context: {"userName":"Alice"}'
    );
    expect(parseActionContent(content)?.values).toEqual({ userName: "Alice" });
  });

  it("returns null for RENDER_ACK_CONTENT (a no-op acknowledgement, not a real action)", () => {
    expect(parseActionContent(RENDER_ACK_CONTENT)).toBeNull();
  });

  it("returns null for content that doesn't match any known format", () => {
    expect(parseActionContent("something unrelated")).toBeNull();
    expect(parseActionContent(adkWrapped("some other tool's output"))).toBeNull();
    expect(parseActionContent(JSON.stringify({ status: "completed" }))).toBeNull();
  });

  it("returns null when a legacy result's trailing context isn't a JSON object", () => {
    expect(
      parseActionContent('User performed action "c" on surface "s". Context: not json')
    ).toBeNull();
    expect(
      parseActionContent('User performed action "c" on surface "s". Context: [1,2,3]')
    ).toBeNull();
  });
});

describe("buildRenderAckMessages", () => {
  const pending = [
    { toolCallId: "call-a", surfaceId: "other" },
    { toolCallId: "call-b", surfaceId: "result" },
  ];

  it("puts the action and its values on the call that rendered the acted-on surface", () => {
    const messages = buildRenderAckMessages(
      pending,
      { name: "confirm", surfaceId: "result" },
      { email: "a@b.c" }
    );
    expect(messages[0]).toMatchObject({ toolCallId: "call-a", content: RENDER_ACK_CONTENT });
    expect(messages[1].toolCallId).toBe("call-b");
    expect(JSON.parse(messages[1].content)).toMatchObject({
      status: "action",
      surfaceId: "result",
      values: { email: "a@b.c" },
    });
  });

  it("acknowledges every pending call with the no-op ack when there is no action", () => {
    expect(buildRenderAckMessages(pending).map((m) => m.content)).toEqual([
      RENDER_ACK_CONTENT,
      RENDER_ACK_CONTENT,
    ]);
  });
});

describe("mergeRecoveredValuesIntoPayload", () => {
  it("merges values into an existing updateDataModel op for the surface", () => {
    const payload = [
      { version: "v0.9", createSurface: { surfaceId: "s1" } },
      { version: "v0.9", updateDataModel: { surfaceId: "s1", value: { existing: "kept" } } },
    ];
    const result = mergeRecoveredValuesIntoPayload(payload, { userName: "Alice" });
    expect(result).toEqual([
      payload[0],
      {
        version: "v0.9",
        updateDataModel: { surfaceId: "s1", value: { existing: "kept", userName: "Alice" } },
      },
    ]);
  });

  it("overwrites a key already present in the data model", () => {
    const payload = [
      { version: "v0.9", createSurface: { surfaceId: "s1" } },
      { version: "v0.9", updateDataModel: { surfaceId: "s1", value: { userName: "old" } } },
    ];
    const result = mergeRecoveredValuesIntoPayload(payload, { userName: "new" }) as Array<{
      updateDataModel?: { value: unknown };
    }>;
    expect(result[1].updateDataModel?.value).toEqual({ userName: "new" });
  });

  it("appends an updateDataModel op when the surface has none yet", () => {
    const payload = [
      { version: "v0.9", createSurface: { surfaceId: "s1" } },
      { version: "v0.9", updateComponents: { surfaceId: "s1", components: [] } },
    ];
    const result = mergeRecoveredValuesIntoPayload(payload, { userName: "Alice" });
    expect(result).toEqual([
      ...payload,
      { version: "v0.9", updateDataModel: { surfaceId: "s1", value: { userName: "Alice" } } },
    ]);
  });

  it("returns the same reference when values is empty", () => {
    const payload = [{ version: "v0.9", createSurface: { surfaceId: "s1" } }];
    expect(mergeRecoveredValuesIntoPayload(payload, {})).toBe(payload);
  });

  it("returns the same reference when the payload isn't an ops array", () => {
    expect(mergeRecoveredValuesIntoPayload(null, { a: 1 })).toBeNull();
    expect(mergeRecoveredValuesIntoPayload(undefined, { a: 1 })).toBeUndefined();
    expect(mergeRecoveredValuesIntoPayload({ not: "an array" }, { a: 1 })).toEqual({
      not: "an array",
    });
  });

  it("returns the same reference when there is no createSurface op", () => {
    const payload = [{ version: "v0.9", updateComponents: { surfaceId: "s1", components: [] } }];
    expect(mergeRecoveredValuesIntoPayload(payload, { a: 1 })).toBe(payload);
  });

  it("never mutates the input payload", () => {
    const dataOp = { version: "v0.9", updateDataModel: { surfaceId: "s1", value: { a: 1 } } };
    const payload = [{ version: "v0.9", createSurface: { surfaceId: "s1" } }, dataOp];
    mergeRecoveredValuesIntoPayload(payload, { b: 2 });
    expect(dataOp).toEqual({
      version: "v0.9",
      updateDataModel: { surfaceId: "s1", value: { a: 1 } },
    });
  });
});
