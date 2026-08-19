import { describe, expect, it } from "vitest";
import { bindingLabel, bindingToValue, valueToBinding } from "./mcp-tool-options";

describe("bindingToValue / valueToBinding", () => {
  it("round-trips a binding through its composite value", () => {
    const binding = { mcpServerId: "mcp-1", toolName: "search" };
    expect(valueToBinding(bindingToValue(binding))).toEqual(binding);
  });

  it("splits on the first separator so a tool name may contain one", () => {
    const binding = { mcpServerId: "mcp-1", toolName: "aws::s3::list" };
    expect(valueToBinding(bindingToValue(binding))).toEqual(binding);
  });
});

describe("bindingLabel", () => {
  it("names the server the tool belongs to", () => {
    expect(
      bindingLabel(
        { mcpServerId: "mcp-1", toolName: "search" },
        new Map([["mcp-1", "my-mcp-server"]])
      )
    ).toBe("my-mcp-server: search");
  });

  it("falls back to a truncated id when the server name is unknown", () => {
    expect(bindingLabel({ mcpServerId: "0123456789abcdef", toolName: "search" }, new Map())).toBe(
      "01234567…: search"
    );
  });
});
