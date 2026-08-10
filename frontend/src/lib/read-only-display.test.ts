import { describe, expect, it } from "vitest";
import {
  EMPTY_VALUE,
  formatChoice,
  formatFlag,
  formatLines,
  formatPairs,
} from "@/lib/read-only-display";

describe("formatFlag", () => {
  it("renders a set flag as Yes", () => {
    expect(formatFlag(true)).toBe("Yes");
  });

  it("renders a cleared flag as No", () => {
    expect(formatFlag(false)).toBe("No");
  });
});

describe("formatChoice", () => {
  const options = [
    { value: "streamable_http", label: "Streamable HTTP" },
    { value: "stdio", label: "stdio" },
  ] as const;

  it("resolves the selected option's label", () => {
    expect(formatChoice(options, "streamable_http")).toBe("Streamable HTTP");
  });

  it("falls back to the raw value when no option matches", () => {
    expect(formatChoice(options, "carrier_pigeon" as (typeof options)[number]["value"])).toBe(
      "carrier_pigeon"
    );
  });
});

describe("formatLines", () => {
  it("joins entries one per line", () => {
    expect(formatLines(["-y", "@scope/pkg"])).toBe("-y\n@scope/pkg");
  });

  it("falls back to the empty placeholder for an empty list", () => {
    expect(formatLines([])).toBe(EMPTY_VALUE);
  });
});

describe("formatPairs", () => {
  it("renders each row as key: value", () => {
    expect(formatPairs([{ key: "Authorization", value: "Bearer x" }])).toEqual([
      "Authorization: Bearer x",
    ]);
  });

  it("renders a valueless row as its key alone", () => {
    expect(formatPairs([{ key: "AWS_ACCESS_KEY_ID", value: "" }])).toEqual(["AWS_ACCESS_KEY_ID"]);
  });

  it("drops rows with no key", () => {
    expect(
      formatPairs([
        { key: "  ", value: "orphan" },
        { key: "KEEP", value: "1" },
      ])
    ).toEqual(["KEEP: 1"]);
  });
});
