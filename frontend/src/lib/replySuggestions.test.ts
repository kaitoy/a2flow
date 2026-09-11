import { describe, expect, it } from "vitest";
import { MAX_REPLY_SUGGESTIONS, parseReplySuggestions } from "./replySuggestions";

describe("parseReplySuggestions", () => {
  it("returns the replies in the agent's order", () => {
    expect(parseReplySuggestions({ suggestions: ["Yes, go ahead", "Skip this step"] })).toEqual([
      "Yes, go ahead",
      "Skip this step",
    ]);
  });

  it("yields nothing when the argument is missing or not an array", () => {
    expect(parseReplySuggestions({})).toEqual([]);
    expect(parseReplySuggestions({ suggestions: "Yes" })).toEqual([]);
    expect(parseReplySuggestions({ suggestions: null })).toEqual([]);
  });

  it("drops non-string, blank and repeated entries and trims the rest", () => {
    expect(
      parseReplySuggestions({
        suggestions: [" Yes ", 42, "", "   ", null, { text: "x" }, "No", "Yes"],
      })
    ).toEqual(["Yes", "No"]);
  });

  it("caps a runaway list", () => {
    const many = Array.from({ length: MAX_REPLY_SUGGESTIONS + 3 }, (_, i) => `Option ${i}`);
    expect(parseReplySuggestions({ suggestions: many })).toHaveLength(MAX_REPLY_SUGGESTIONS);
  });
});
