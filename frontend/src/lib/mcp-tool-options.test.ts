import { describe, expect, it } from "vitest";
import {
  bindingLabel,
  bindingToValue,
  exemptValues,
  toBindings,
  valueToBinding,
} from "./mcp-tool-options";

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

describe("toBindings / exemptValues", () => {
  it("bounds a tool's input unless it was checked as exempt", () => {
    expect(toBindings(["mcp-1::search", "mcp-1::launch"], ["mcp-1::search"])).toEqual([
      { mcpServerId: "mcp-1", toolName: "search", requiresInputApproval: false },
      { mcpServerId: "mcp-1", toolName: "launch", requiresInputApproval: true },
    ]);
  });

  it("bounds everything when nothing is checked", () => {
    expect(toBindings(["mcp-1::search"], [])).toEqual([
      { mcpServerId: "mcp-1", toolName: "search", requiresInputApproval: true },
    ]);
  });

  it("ignores an exemption for a tool that is no longer bound", () => {
    expect(toBindings(["mcp-1::search"], ["mcp-1::gone"])).toEqual([
      { mcpServerId: "mcp-1", toolName: "search", requiresInputApproval: true },
    ]);
  });

  it("reads the checked subset back out of what the API returned", () => {
    expect(
      exemptValues([
        { mcpServerId: "mcp-1", toolName: "search", requiresInputApproval: false },
        { mcpServerId: "mcp-1", toolName: "launch", requiresInputApproval: true },
      ])
    ).toEqual(["mcp-1::search"]);
  });

  it("treats a binding with no flag at all as bounded", () => {
    // What an older record looks like: absence is not an exemption.
    expect(exemptValues([{ mcpServerId: "mcp-1", toolName: "search" }])).toEqual([]);
  });
});
