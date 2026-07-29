import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";
import { McpServerToolsPanel } from "@/components/admin/mcp-server-tools-panel";
import { store } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { MCP_TOOL_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";

const BASE = "http://localhost:8000";
const TOOLS_URL = `${BASE}/api/v1/mcp-servers/:serverId/tools`;

describe("McpServerToolsPanel", () => {
  it("shows the fetch hint and no tools before the button is clicked", () => {
    render(<McpServerToolsPanel serverId="mcp-1" />);
    expect(screen.getByRole("button", { name: /fetch tools/i })).toBeInTheDocument();
    expect(screen.getByText("Fetch to see the tools this server advertises.")).toBeInTheDocument();
    expect(screen.queryByText(MCP_TOOL_1.name)).not.toBeInTheDocument();
  });

  it("renders the tool list after a successful fetch", async () => {
    const user = userEvent.setup();
    render(<McpServerToolsPanel serverId="mcp-1" />);

    await user.click(screen.getByRole("button", { name: /fetch tools/i }));

    await waitFor(() => expect(screen.getByText(MCP_TOOL_1.name)).toBeInTheDocument());
    expect(screen.getByText(MCP_TOOL_1.description)).toBeInTheDocument();
  });

  it("shows an empty state when the server advertises no tools", async () => {
    server.use(http.get(TOOLS_URL, () => envelope([])));
    const user = userEvent.setup();
    render(<McpServerToolsPanel serverId="mcp-1" />);

    await user.click(screen.getByRole("button", { name: /fetch tools/i }));

    await waitFor(() => expect(screen.getByText("No tools advertised")).toBeInTheDocument());
  });

  it("shows an inline error and a toast when the fetch fails, then recovers on retry", async () => {
    server.use(
      http.get(TOOLS_URL, () => envelopeErr("MCP_UNREACHABLE", "MCP server unreachable", 502))
    );
    const user = userEvent.setup();
    render(<McpServerToolsPanel serverId="mcp-1" />);

    await user.click(screen.getByRole("button", { name: /fetch tools/i }));

    await waitFor(() => expect(screen.getByText("MCP server unreachable")).toBeInTheDocument());
    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "MCP server unreachable",
        variant: "error",
      })
    );

    server.use(http.get(TOOLS_URL, () => envelope([MCP_TOOL_1])));
    await user.click(screen.getByRole("button", { name: /fetch tools/i }));

    await waitFor(() => expect(screen.getByText(MCP_TOOL_1.name)).toBeInTheDocument());
    expect(screen.queryByText("MCP server unreachable")).not.toBeInTheDocument();
  });
});
