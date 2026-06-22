import { describe, expect, it } from "vitest";
import type { McpRegistryServerEntry } from "@/lib/api";
import { buildPrefillHref, parsePrefill } from "@/lib/mcp-registry-prefill";

const ENTRY: McpRegistryServerEntry = {
  name: "io.example/weather",
  title: "Weather",
  description: "Weather lookups.",
  version: "1.2.0",
  url: "https://mcp.example.com/weather",
  headers: [
    { name: "Authorization", isRequired: true, isSecret: true },
    { name: "X-Region", isRequired: false, isSecret: false, value: "us" },
  ],
};

describe("buildPrefillHref", () => {
  it("encodes title, url, and header keys into the create form href", () => {
    const href = buildPrefillHref(ENTRY);
    const url = new URL(href, "http://localhost");
    expect(url.pathname).toBe("/admin/mcp-servers/new");
    expect(url.searchParams.get("name")).toBe("Weather");
    expect(url.searchParams.get("url")).toBe("https://mcp.example.com/weather");
    expect(JSON.parse(url.searchParams.get("headers") ?? "[]")).toEqual([
      { key: "Authorization", value: "" },
      { key: "X-Region", value: "us" },
    ]);
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
      url: "https://mcp.example.com/weather",
      headers: [
        { key: "Authorization", value: "" },
        { key: "X-Region", value: "us" },
      ],
    });
  });

  it("returns empty values when params are absent", () => {
    expect(parsePrefill(new URLSearchParams())).toEqual({
      name: "",
      url: "",
      headers: [],
    });
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
});
