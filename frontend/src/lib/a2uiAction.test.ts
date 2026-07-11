import { describe, expect, it } from "vitest";
import {
  formatActionContent,
  mergeRecoveredValuesIntoPayload,
  parseActionContent,
  RENDER_ACK_CONTENT,
} from "./a2uiAction";

describe("parseActionContent", () => {
  it("round-trips formatActionContent's output", () => {
    const action = {
      name: "confirm",
      surfaceId: "result",
      sourceComponentId: "btn",
      context: { userName: "Alice", age: 30 },
    };
    const parsed = parseActionContent(formatActionContent(action));
    expect(parsed).toEqual(action);
  });

  it("recovers a missing sourceComponentId as undefined", () => {
    const action = { name: "confirm", surfaceId: "result", context: {} };
    const parsed = parseActionContent(formatActionContent(action));
    expect(parsed?.sourceComponentId).toBeUndefined();
  });

  it("returns null for RENDER_ACK_CONTENT (a no-op acknowledgement, not a real action)", () => {
    expect(parseActionContent(RENDER_ACK_CONTENT)).toBeNull();
  });

  it("returns null for content that doesn't match the format at all", () => {
    expect(parseActionContent("something unrelated")).toBeNull();
  });

  it("returns null when the trailing context isn't valid JSON", () => {
    const content = 'User performed action "confirm" on surface "result". Context: not json';
    expect(parseActionContent(content)).toBeNull();
  });

  it("returns null when the trailing context is a JSON array, not an object", () => {
    const content = 'User performed action "confirm" on surface "result". Context: [1,2,3]';
    expect(parseActionContent(content)).toBeNull();
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
