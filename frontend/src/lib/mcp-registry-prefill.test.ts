import { describe, expect, it } from "vitest";
import type { McpRegistryServerEntry } from "@/lib/api";
import { buildPrefillHref, parsePrefill } from "@/lib/mcp-registry-prefill";

const ENTRY: McpRegistryServerEntry = {
  name: "io.example/weather",
  title: "Weather",
  description: "Weather lookups.",
  version: "1.2.0",
  transport: "streamable_http",
  url: "https://mcp.example.com/weather",
  headers: [
    { name: "Authorization", isRequired: true, isSecret: true },
    { name: "X-Region", isRequired: false, isSecret: false, value: "us" },
  ],
};

const STDIO_ENTRY: McpRegistryServerEntry = {
  name: "io.example/files",
  title: "Files",
  version: "0.3.0",
  transport: "stdio",
  command: "npx",
  args: ["-y", "files-mcp@0.3.0"],
  env: [
    { name: "API_KEY", isRequired: true, isSecret: true },
    { name: "ROOT", isRequired: false, isSecret: false, value: "/data" },
  ],
};

describe("buildPrefillHref", () => {
  it("encodes title, url, and header keys into the create form href", () => {
    const href = buildPrefillHref(ENTRY);
    const url = new URL(href, "http://localhost");
    expect(url.pathname).toBe("/admin/mcp-servers/new");
    expect(url.searchParams.get("name")).toBe("Weather");
    expect(url.searchParams.get("transport")).toBe("streamable_http");
    expect(url.searchParams.get("url")).toBe("https://mcp.example.com/weather");
    expect(JSON.parse(url.searchParams.get("headers") ?? "[]")).toEqual([
      { key: "Authorization", value: "" },
      { key: "X-Region", value: "us" },
    ]);
  });

  it("encodes command, args, and env keys for a stdio entry", () => {
    const href = buildPrefillHref(STDIO_ENTRY);
    const url = new URL(href, "http://localhost");
    expect(url.searchParams.get("transport")).toBe("stdio");
    expect(url.searchParams.get("command")).toBe("npx");
    expect(JSON.parse(url.searchParams.get("args") ?? "[]")).toEqual(["-y", "files-mcp@0.3.0"]);
    expect(JSON.parse(url.searchParams.get("env") ?? "[]")).toEqual([
      { key: "API_KEY", value: "" },
      { key: "ROOT", value: "/data" },
    ]);
    expect(url.searchParams.has("url")).toBe(false);
    expect(url.searchParams.has("headers")).toBe(false);
  });

  it("falls back to the server name when there is no title", () => {
    const href = buildPrefillHref({ ...ENTRY, title: undefined });
    const url = new URL(href, "http://localhost");
    expect(url.searchParams.get("name")).toBe("io.example/weather");
  });

  it("omits the headers param when there are no headers", () => {
    const href = buildPrefillHref({ ...ENTRY, headers: [] });
    const url = new URL(href, "http://localhost");
    expect(url.searchParams.has("headers")).toBe(false);
  });
});

describe("parsePrefill", () => {
  it("round-trips values produced by buildPrefillHref", () => {
    const href = buildPrefillHref(ENTRY);
    const params = new URL(href, "http://localhost").searchParams;
    expect(parsePrefill(params)).toEqual({
      name: "Weather",
      transport: "streamable_http",
      url: "https://mcp.example.com/weather",
      headers: [
        { key: "Authorization", value: "" },
        { key: "X-Region", value: "us" },
      ],
      command: "npx",
      args: [],
      env: [],
    });
  });

  it("round-trips a stdio entry", () => {
    const href = buildPrefillHref(STDIO_ENTRY);
    const params = new URL(href, "http://localhost").searchParams;
    expect(parsePrefill(params)).toEqual({
      name: "Files",
      transport: "stdio",
      url: "",
      headers: [],
      command: "npx",
      args: ["-y", "files-mcp@0.3.0"],
      env: [
        { key: "API_KEY", value: "" },
        { key: "ROOT", value: "/data" },
      ],
    });
  });

  it("returns empty values when params are absent", () => {
    expect(parsePrefill(new URLSearchParams())).toEqual({
      name: "",
      transport: "streamable_http",
      url: "",
      headers: [],
      command: "npx",
      args: [],
      env: [],
    });
  });

  it("falls back to streamable_http for an unrecognized transport", () => {
    const params = new URLSearchParams({ transport: "sse" });
    expect(parsePrefill(params).transport).toBe("streamable_http");
  });

  it("ignores malformed header JSON", () => {
    const params = new URLSearchParams({ name: "x", url: "y", headers: "{bad" });
    expect(parsePrefill(params).headers).toEqual([]);
  });

  it("drops header entries with the wrong shape", () => {
    const params = new URLSearchParams({
      headers: JSON.stringify([{ key: "ok", value: "1" }, { key: 5 }, "nope"]),
    });
    expect(parsePrefill(params).headers).toEqual([{ key: "ok", value: "1" }]);
  });

  it("drops non-string argv entries", () => {
    const params = new URLSearchParams({ args: JSON.stringify(["-y", 3, null, "pkg"]) });
    expect(parsePrefill(params).args).toEqual(["-y", "pkg"]);
  });
});
