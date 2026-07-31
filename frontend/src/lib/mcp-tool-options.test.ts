import { http } from "msw";
import { describe, expect, it } from "vitest";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import {
  bindingToValue,
  loadMcpToolOptions,
  mergeBindingOptions,
  valueToBinding,
} from "./mcp-tool-options";

const BASE = "http://localhost:8000";

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

describe("mergeBindingOptions", () => {
  it("keeps a bound tool selectable when its server advertises nothing", () => {
    const merged = mergeBindingOptions(
      [],
      [{ mcpServerId: "mcp-1", toolName: "search" }],
      new Map([["mcp-1", "my-mcp-server"]])
    );
    expect(merged).toEqual([
      { value: "mcp-1::search", label: "my-mcp-server: search", serverId: "mcp-1" },
    ]);
  });

  it("falls back to a truncated id when the server name is unknown", () => {
    const merged = mergeBindingOptions(
      [],
      [{ mcpServerId: "0123456789abcdef", toolName: "search" }],
      new Map()
    );
    expect(merged[0].label).toBe("01234567…: search");
  });

  it("does not duplicate a binding the catalog already advertises", () => {
    const options = [{ value: "mcp-1::search", label: "my-mcp-server: search", serverId: "mcp-1" }];
    const merged = mergeBindingOptions(
      options,
      [{ mcpServerId: "mcp-1", toolName: "search" }],
      new Map([["mcp-1", "my-mcp-server"]])
    );
    expect(merged).toHaveLength(1);
  });
});

describe("loadMcpToolOptions", () => {
  it("lists every reachable server's tools", async () => {
    const catalog = await loadMcpToolOptions();
    expect(catalog.options.map((o) => o.value)).toEqual(["mcp-1::search", "mcp-2::search"]);
    expect(catalog.options[0].label).toBe("my-mcp-server: search");
    expect(catalog.failures).toEqual([]);
    expect(catalog.serverNames.get("mcp-2")).toBe("local-files");
  });

  it("reports an unreachable server instead of dropping it silently", async () => {
    server.use(
      http.get(`${BASE}/api/v1/mcp-servers/:serverId/tools`, ({ params }) =>
        params.serverId === "mcp-2"
          ? envelopeErr("MCP_UNREACHABLE", "MCP server 'local-files' unreachable", 502)
          : envelope([{ name: "search", description: "Search the web", inputSchema: {} }])
      )
    );

    const catalog = await loadMcpToolOptions();

    // The reachable server's tools still come through...
    expect(catalog.options.map((o) => o.value)).toEqual(["mcp-1::search"]);
    // ...and the broken one is named, so the picker can explain the gap.
    expect(catalog.failures).toHaveLength(1);
    expect(catalog.failures[0].serverId).toBe("mcp-2");
    expect(catalog.failures[0].serverName).toBe("local-files");
    expect(catalog.failures[0].message).toContain("unreachable");
  });

  it("propagates a failure to list the registry itself", async () => {
    server.use(
      http.get(`${BASE}/api/v1/mcp-servers`, () => envelopeErr("INTERNAL_ERROR", "boom", 500))
    );
    await expect(loadMcpToolOptions()).rejects.toThrow();
  });

  it("returns an empty catalog when nothing is registered", async () => {
    server.use(http.get(`${BASE}/api/v1/mcp-servers`, () => envelope([])));
    const catalog = await loadMcpToolOptions();
    expect(catalog).toEqual({ options: [], serverNames: new Map(), failures: [] });
  });
});
