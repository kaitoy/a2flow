import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { McpToolPicker } from "./mcp-tool-picker";

const BASE = "http://localhost:8000";

/** Replace the shared tools handler so each server advertises the given names. */
function serveTools(names: string[]) {
  server.use(
    http.get(`${BASE}/api/v1/mcp-servers/:serverId/tools`, () =>
      envelope(names.map((name) => ({ name, description: null, inputSchema: {} })))
    )
  );
}

describe("McpToolPicker", () => {
  it("says it is loading rather than showing an empty list", () => {
    render(<McpToolPicker value={[]} onChange={vi.fn()} />);
    expect(screen.getByText("Loading tools…")).toBeInTheDocument();
  });

  it("lists every reachable server's tools once loaded", async () => {
    render(<McpToolPicker value={[]} onChange={vi.fn()} />);

    expect(
      await screen.findByRole("checkbox", { name: "my-mcp-server: search" })
    ).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "local-files: search" })).toBeInTheDocument();
  });

  it("reports the selection when a tool is checked", async () => {
    const onChange = vi.fn();
    render(<McpToolPicker value={[]} onChange={onChange} />);

    await userEvent.click(await screen.findByRole("checkbox", { name: "my-mcp-server: search" }));

    expect(onChange).toHaveBeenCalledWith(["mcp-1::search"]);
  });

  it("points at the registry when no MCP server is registered", async () => {
    server.use(http.get(`${BASE}/api/v1/mcp-servers`, () => envelope([])));
    render(<McpToolPicker value={[]} onChange={vi.fn()} />);

    expect(await screen.findByText(/No MCP servers are registered/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Register one" })).toHaveAttribute(
      "href",
      "/admin/mcp-servers"
    );
  });

  it("names the unreachable server instead of claiming none are registered", async () => {
    server.use(
      http.get(`${BASE}/api/v1/mcp-servers/:serverId/tools`, ({ params }) =>
        params.serverId === "mcp-2"
          ? envelopeErr("MCP_UNREACHABLE", "MCP server 'local-files' unreachable", 502)
          : envelope([{ name: "search", description: null, inputSchema: {} }])
      )
    );
    render(<McpToolPicker value={[]} onChange={vi.fn()} />);

    // The reachable server's tool is still offered...
    expect(
      await screen.findByRole("checkbox", { name: "my-mcp-server: search" })
    ).toBeInTheDocument();
    // ...and the failure is explained rather than silently swallowed.
    expect(screen.getByText("local-files")).toBeInTheDocument();
    expect(screen.getByText(/unreachable/)).toBeInTheDocument();
    expect(screen.queryByText(/No MCP servers are registered/)).not.toBeInTheDocument();
  });

  it("surfaces a registry failure and recovers on retry", async () => {
    let attempt = 0;
    server.use(
      http.get(`${BASE}/api/v1/mcp-servers`, () => {
        attempt += 1;
        return attempt === 1
          ? envelopeErr("INTERNAL_ERROR", "registry exploded", 500)
          : envelope([
              {
                id: "mcp-1",
                tenantId: "tenant-1",
                name: "my-mcp-server",
                transport: "streamable_http",
                url: "https://mcp.example.com/mcp",
                headers: {},
                args: [],
                env: {},
                createdAt: "2026-01-01T00:00:00Z",
                updatedAt: "2026-01-01T00:00:00Z",
                createdBy: "",
                updatedBy: "",
              },
            ]);
      })
    );
    render(<McpToolPicker value={[]} onChange={vi.fn()} />);

    expect(await screen.findByText("Could not load the MCP server registry.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(
      await screen.findByRole("checkbox", { name: "my-mcp-server: search" })
    ).toBeInTheDocument();
  });

  it("keeps a bound tool selectable when its server no longer advertises it", async () => {
    serveTools([]);
    render(
      <McpToolPicker
        value={["mcp-1::retired"]}
        onChange={vi.fn()}
        boundBindings={[{ mcpServerId: "mcp-1", toolName: "retired" }]}
      />
    );

    const checkbox = await screen.findByRole("checkbox", { name: "my-mcp-server: retired" });
    expect(checkbox).toBeChecked();
  });

  it("offers no filter for a short list", async () => {
    render(<McpToolPicker value={[]} onChange={vi.fn()} />);
    await screen.findByRole("checkbox", { name: "my-mcp-server: search" });
    expect(screen.queryByLabelText("Filter tools")).not.toBeInTheDocument();
  });

  it("filters a long list while keeping the current selection visible", async () => {
    // 8 tools on each of the two servers = 16 options, past the filter threshold.
    serveTools(["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta"]);
    render(<McpToolPicker value={["mcp-1::zeta"]} onChange={vi.fn()} />);

    const filter = await screen.findByLabelText("Filter tools");
    await userEvent.type(filter, "alpha");

    await waitFor(() =>
      expect(
        screen.queryByRole("checkbox", { name: "my-mcp-server: beta" })
      ).not.toBeInTheDocument()
    );
    expect(screen.getByRole("checkbox", { name: "my-mcp-server: alpha" })).toBeInTheDocument();
    // Selected but non-matching options stay rendered: CheckboxGroup derives the
    // next selection from the options it is given, so hiding one would drop it.
    expect(screen.getByRole("checkbox", { name: "my-mcp-server: zeta" })).toBeChecked();
  });
});
