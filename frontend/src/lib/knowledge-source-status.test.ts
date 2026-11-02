import { describe, expect, it } from "vitest";
import {
  formatKnowledgeSourceStatus,
  isKnowledgeSourceBusy,
  isKnowledgeSourceLlmActive,
} from "./knowledge-source-status";

describe("knowledge source status", () => {
  it("labels each state", () => {
    expect(formatKnowledgeSourceStatus("unread")).toBe("Not read");
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
    expect(isKnowledgeSourceBusy("unread")).toBe(false);
  });

  it("treats only reading and removing as LLM work", () => {
    expect(isKnowledgeSourceLlmActive("ingesting")).toBe(true);
    expect(isKnowledgeSourceLlmActive("removing")).toBe(true);
    expect(isKnowledgeSourceLlmActive("pending")).toBe(false);
    expect(isKnowledgeSourceLlmActive("ready")).toBe(false);
    expect(isKnowledgeSourceLlmActive("failed")).toBe(false);
    expect(isKnowledgeSourceLlmActive("unread")).toBe(false);
  });
});
