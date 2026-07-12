import { describe, expect, it } from "vitest";
import {
  formatRevision,
  formatSyncStatusLabel,
  SYNC_STATUS_DOT_CLASS,
} from "./agent-skill-sync-status";

describe("SYNC_STATUS_DOT_CLASS", () => {
  it("covers every sync status", () => {
    expect(Object.keys(SYNC_STATUS_DOT_CLASS).sort()).toEqual(["failed", "pending", "ready"]);
  });
});

describe("formatSyncStatusLabel", () => {
  it("reads pending as the clone that is actually happening", () => {
    expect(formatSyncStatusLabel("pending")).toBe("Cloning");
  });

  it("passes settled statuses through", () => {
    expect(formatSyncStatusLabel("ready")).toBe("ready");
    expect(formatSyncStatusLabel("failed")).toBe("failed");
  });
});

describe("formatRevision", () => {
  it("shortens a sha to seven characters", () => {
    expect(formatRevision("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2")).toBe("a1b2c3d");
  });

  it("renders an em dash when nothing has been published", () => {
    expect(formatRevision(null)).toBe("—");
    expect(formatRevision(undefined)).toBe("—");
  });
});
