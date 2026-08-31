import { act, renderHook, waitFor } from "@testing-library/react";
import { http } from "msw";
import { describe, expect, it } from "vitest";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { useMcpServerTools } from "./useMcpServerTools";

const TOOLS_URL = "http://localhost:8000/api/v1/mcp-servers/:serverId/tools";

/** Minimal `McpToolInfo`, as the listing endpoint returns it. */
function tool(name: string) {
  return { name, description: null, inputSchema: {}, outputSchema: null };
}

describe("useMcpServerTools", () => {
  it("stays idle and queries nothing while the server id is null", () => {
    let called = false;
    server.use(
      http.get(TOOLS_URL, () => {
        called = true;
        return envelope([tool("search")]);
      })
    );

    const { result } = renderHook(() => useMcpServerTools(null));

    expect(result.current.state).toEqual({ phase: "idle" });
    expect(called).toBe(false);
  });

  it("lists the tools of the given server", async () => {
    server.use(http.get(TOOLS_URL, () => envelope([tool("search"), tool("fetch")])));

    const { result } = renderHook(() => useMcpServerTools("mcp-1"));

    await waitFor(() => expect(result.current.state.phase).toBe("ready"));
    expect(result.current.state).toEqual({
      phase: "ready",
      tools: [tool("search"), tool("fetch")],
    });
  });

  it("keeps each tool's declared output schema, not just its name", async () => {
    const outputSchema = { type: "object", properties: { hits: { type: "array" } } };
    server.use(
      http.get(TOOLS_URL, () =>
        envelope([{ name: "search", description: "Search", inputSchema: {}, outputSchema }])
      )
    );

    const { result } = renderHook(() => useMcpServerTools("mcp-1"));

    await waitFor(() => expect(result.current.state.phase).toBe("ready"));
    expect(result.current.state).toEqual({
      phase: "ready",
      tools: [{ name: "search", description: "Search", inputSchema: {}, outputSchema }],
    });
  });

  it("reports an unreachable server as an error", async () => {
    server.use(http.get(TOOLS_URL, () => envelopeErr("MCP_UNREACHABLE", "unreachable", 502)));

    const { result } = renderHook(() => useMcpServerTools("mcp-1"));

    await waitFor(() => expect(result.current.state.phase).toBe("error"));
  });

  it("applies only the latest server's reply when the id changes mid-flight", async () => {
    server.use(
      http.get(TOOLS_URL, ({ params }) =>
        envelope(params.serverId === "mcp-1" ? [tool("search")] : [tool("read")])
      )
    );

    const { result, rerender } = renderHook(({ id }) => useMcpServerTools(id), {
      initialProps: { id: "mcp-1" as string | null },
    });
    rerender({ id: "mcp-2" });

    await waitFor(() => expect(result.current.state.phase).toBe("ready"));
    expect(result.current.state).toEqual({ phase: "ready", tools: [tool("read")] });
  });

  it("returns to idle when the server id is cleared", async () => {
    server.use(http.get(TOOLS_URL, () => envelope([tool("search")])));

    const { result, rerender } = renderHook(({ id }) => useMcpServerTools(id), {
      initialProps: { id: "mcp-1" as string | null },
    });
    await waitFor(() => expect(result.current.state.phase).toBe("ready"));

    rerender({ id: null });

    expect(result.current.state).toEqual({ phase: "idle" });
  });

  it("re-runs the listing on reload", async () => {
    let attempt = 0;
    server.use(
      http.get(TOOLS_URL, () => {
        attempt += 1;
        return attempt === 1
          ? envelopeErr("MCP_UNREACHABLE", "unreachable", 502)
          : envelope([tool("search")]);
      })
    );

    const { result } = renderHook(() => useMcpServerTools("mcp-1"));
    await waitFor(() => expect(result.current.state.phase).toBe("error"));

    await act(async () => {
      result.current.reload();
    });

    await waitFor(() => expect(result.current.state.phase).toBe("ready"));
    expect(result.current.state).toEqual({ phase: "ready", tools: [tool("search")] });
  });
});
