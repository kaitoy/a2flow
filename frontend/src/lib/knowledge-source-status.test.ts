import { describe, expect, it } from "vitest";
import { formatKnowledgeSourceStatus, isKnowledgeSourceBusy } from "./knowledge-source-status";

describe("knowledge source status", () => {
  it("labels each state", () => {
    expect(formatKnowledgeSourceStatus("pending")).toBe("Queued");
    expect(formatKnowledgeSourceStatus("ingesting")).toBe("Reading");
    expect(formatKnowledgeSourceStatus("removing")).toBe("Removing");
  });

  it("treats only the in-flight states as busy", () => {
    expect(isKnowledgeSourceBusy("pending")).toBe(true);
    expect(isKnowledgeSourceBusy("ingesting")).toBe(true);
    expect(isKnowledgeSourceBusy("removing")).toBe(true);
    expect(isKnowledgeSourceBusy("ready")).toBe(false);
    expect(isKnowledgeSourceBusy("failed")).toBe(false);
  });
});
