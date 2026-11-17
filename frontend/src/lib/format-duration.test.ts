import { describe, expect, it } from "vitest";
import { formatDuration } from "./format-duration";

describe("formatDuration", () => {
  it("picks the largest unit that fits", () => {
    expect(formatDuration(45, "en")).toBe("45s");
    expect(formatDuration(12 * 60, "en")).toBe("12m");
    expect(formatDuration(3 * 86_400, "en")).toBe("3d");
  });

  it("keeps one decimal below ten of the unit and none above", () => {
    expect(formatDuration(5_400, "en")).toBe("1.5h");
    expect(formatDuration(11 * 3_600 + 1_800, "en")).toBe("12h");
  });

  it("treats zero and negative durations as zero seconds", () => {
    expect(formatDuration(0, "en")).toBe("0s");
    expect(formatDuration(-5, "en")).toBe("0s");
  });
});
