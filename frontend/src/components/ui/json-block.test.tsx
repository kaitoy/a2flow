import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { formatJson, JsonBlock } from "./json-block";

describe("formatJson", () => {
  it("pretty-prints an object with two-space indentation", () => {
    expect(formatJson({ a: 1 })).toBe('{\n  "a": 1\n}');
  });

  it("passes a string through unquoted", () => {
    expect(formatJson("plain text")).toBe("plain text");
  });

  it("falls back to String() for a value JSON cannot encode", () => {
    const cyclic: Record<string, unknown> = {};
    cyclic.self = cyclic;
    expect(formatJson(cyclic)).toBe("[object Object]");
  });
});

describe("JsonBlock", () => {
  it("renders the formatted value in a pre", () => {
    const { container } = render(<JsonBlock value={{ a: 1 }} />);
    const pre = container.querySelector("pre");
    expect(pre).not.toBeNull();
    expect(pre?.textContent).toBe('{\n  "a": 1\n}');
  });

  it("scrolls inside its own height cap", () => {
    const { container } = render(<JsonBlock value={{}} />);
    expect(container.firstChild).toHaveClass("max-h-64", "overflow-auto", "font-mono");
  });

  it("merges a passed className", () => {
    const { container } = render(<JsonBlock value={{}} className="max-h-40" />);
    expect(container.firstChild).toHaveClass("max-h-64", "max-h-40");
  });
});
