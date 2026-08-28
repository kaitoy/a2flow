import { describe, expect, it } from "vitest";
import {
  CALL_MCP_TOOL_NAME,
  getToolCallArguments,
  getToolDisplayName,
  isHiddenToolName,
  isMockedResult,
  parseToolResult,
} from "./agentActivity";

describe("getToolDisplayName", () => {
  it("shows the proxied tool's own name for call_mcp_tool", () => {
    expect(getToolDisplayName(CALL_MCP_TOOL_NAME, { tool_name: "search_web" })).toBe("search_web");
  });

  it("falls back to the function name when the proxy names no tool", () => {
    expect(getToolDisplayName(CALL_MCP_TOOL_NAME, {})).toBe(CALL_MCP_TOOL_NAME);
  });

  it("shows any other tool under its own name", () => {
    expect(getToolDisplayName("create_workflow_task", { title: "x" })).toBe("create_workflow_task");
  });
});

describe("isHiddenToolName", () => {
  it("hides the tools that have their own UI", () => {
    expect(isHiddenToolName("render_approval")).toBe(true);
  });

  it("shows an ordinary tool", () => {
    expect(isHiddenToolName("create_workflow_task")).toBe(false);
  });
});

describe("getToolCallArguments", () => {
  it("unwraps the proxied tool's arguments for call_mcp_tool", () => {
    expect(
      getToolCallArguments(CALL_MCP_TOOL_NAME, {
        server_id: "srv-1",
        tool_name: "search_web",
        arguments: { query: "rust" },
      })
    ).toEqual({ query: "rust" });
  });

  it("keeps the whole envelope when the proxy carries no nested arguments", () => {
    const args = { server_id: "srv-1", tool_name: "search_web" };
    expect(getToolCallArguments(CALL_MCP_TOOL_NAME, args)).toEqual(args);
  });

  it("passes another tool's arguments through unchanged", () => {
    const args = { title: "Step 1" };
    expect(getToolCallArguments("create_workflow_task", args)).toEqual(args);
  });
});

describe("parseToolResult", () => {
  it("parses a JSON payload", () => {
    expect(parseToolResult('{"ok":true}')).toEqual({ ok: true });
  });

  it("returns non-JSON text as-is rather than dropping it", () => {
    expect(parseToolResult("plain answer")).toBe("plain answer");
  });
});

describe("isMockedResult", () => {
  it("recognizes the backend's mocked marker", () => {
    expect(isMockedResult({ result: {}, mocked: true })).toBe(true);
  });

  it("treats a real result as not mocked", () => {
    expect(isMockedResult({ result: {} })).toBe(false);
  });

  it("treats a non-object result as not mocked", () => {
    expect(isMockedResult("plain answer")).toBe(false);
    expect(isMockedResult(null)).toBe(false);
  });
});
