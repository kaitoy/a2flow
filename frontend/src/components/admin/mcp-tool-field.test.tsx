import type { UserEvent } from "@testing-library/user-event";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { McpToolField, type McpToolSelection } from "./mcp-tool-field";

const BASE = "http://localhost:8000";
const SERVERS_URL = `${BASE}/api/v1/mcp-servers`;
const TOOLS_URL = `${BASE}/api/v1/mcp-servers/:serverId/tools`;

/** Minimal `McpToolInfo` — the field only ever reads the name. */
function tool(name: string) {
  return { name, description: null, inputSchema: {} };
}

/** Give each registered server its own tools, so "only the picked one's" is assertable. */
function serveToolsPerServer() {
  server.use(
    http.get(TOOLS_URL, ({ params }) =>
      envelope(params.serverId === "mcp-1" ? [tool("search"), tool("fetch")] : [tool("read")])
    )
  );
}

/**
 * Controlled harness. The field owns no selection of its own, so a static pair
 * would make every pick silently fail to stick.
 */
function Harness({
  initial = { mcpServerId: "", toolName: "" },
  onChange,
}: {
  initial?: McpToolSelection;
  onChange?: (next: McpToolSelection) => void;
}) {
  const [value, setValue] = useState(initial);
  return (
    <McpToolField
      idPrefix="mcpToolMock"
      mcpServerId={value.mcpServerId}
      toolName={value.toolName}
      onChange={(next) => {
        setValue(next);
        onChange?.(next);
      }}
    />
  );
}

/** Open the server dialog, choose `name`, and confirm — what an operator does. */
async function pickServer(user: UserEvent, name: string) {
  await user.click(await screen.findByRole("button", { name: "Select MCP server…" }));
  await user.click(await screen.findByRole("radio", { name }));
  await user.click(screen.getByRole("button", { name: "Select" }));
}

/** The tool dropdown, once it is enabled. */
async function toolSelect() {
  const select = await screen.findByRole("combobox", { name: /tool name/i });
  await waitFor(() => expect(select).toBeEnabled());
  return select;
}

describe("McpToolField", () => {
  it("queries no server for tools until one is picked", async () => {
    let toolCalls = 0;
    server.use(
      http.get(TOOLS_URL, () => {
        toolCalls += 1;
        return envelope([tool("search")]);
      })
    );

    render(<Harness />);

    expect(await screen.findByRole("button", { name: "Select MCP server…" })).toBeInTheDocument();
    expect(toolCalls).toBe(0);
  });

  it("offers the picked server's tools and reports the chosen pair", async () => {
    serveToolsPerServer();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness onChange={onChange} />);

    await pickServer(user, "my-mcp-server");
    await user.click(await toolSelect());
    await user.click(await screen.findByRole("option", { name: "search" }));

    expect(onChange).toHaveBeenLastCalledWith({ mcpServerId: "mcp-1", toolName: "search" });
  });

  it("offers only the picked server's tools", async () => {
    serveToolsPerServer();
    const user = userEvent.setup();
    render(<Harness />);

    await pickServer(user, "my-mcp-server");
    await user.click(await toolSelect());

    expect(await screen.findByRole("option", { name: "search" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "fetch" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "read" })).not.toBeInTheDocument();
  });

  it("clears both server and tool when the server chip is removed", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness initial={{ mcpServerId: "mcp-1", toolName: "search" }} onChange={onChange} />);

    await user.click(await screen.findByRole("button", { name: "Remove my-mcp-server" }));

    expect(onChange).toHaveBeenCalledWith({ mcpServerId: "", toolName: "" });
  });

  it("drops the chosen tool when a different server is picked", async () => {
    serveToolsPerServer();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness initial={{ mcpServerId: "mcp-1", toolName: "search" }} onChange={onChange} />);

    await pickServer(user, "local-files");

    expect(onChange).toHaveBeenLastCalledWith({ mcpServerId: "mcp-2", toolName: "" });
  });

  it("restores a prefilled pair: the server name on the chip, the tool selected", async () => {
    serveToolsPerServer();
    render(<Harness initial={{ mcpServerId: "mcp-1", toolName: "search" }} />);

    expect(await screen.findByRole("button", { name: "Remove my-mcp-server" })).toBeInTheDocument();
    expect(await screen.findByRole("combobox", { name: /tool name/i })).toHaveTextContent("search");
  });

  it("keeps a stored tool the server no longer advertises, marked not found", async () => {
    server.use(http.get(TOOLS_URL, () => envelope([tool("fetch")])));
    render(<Harness initial={{ mcpServerId: "mcp-1", toolName: "search" }} />);

    expect(await screen.findByRole("combobox", { name: /tool name/i })).toHaveTextContent(
      "search (not found)"
    );
  });

  it("explains an unreachable server instead of an empty dropdown, and recovers on retry", async () => {
    let attempt = 0;
    server.use(
      http.get(TOOLS_URL, () => {
        attempt += 1;
        return attempt === 1
          ? envelopeErr("MCP_UNREACHABLE", "MCP server 'my-mcp-server' unreachable", 502)
          : envelope([tool("search")]);
      })
    );
    const user = userEvent.setup();
    render(<Harness />);

    await pickServer(user, "my-mcp-server");

    expect(await screen.findByText(/unreachable/)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /tool name/i })).toHaveTextContent(
      "Could not load tools"
    );

    await user.click(screen.getByRole("button", { name: "Retry" }));
    await user.click(await toolSelect());
    await user.click(await screen.findByRole("option", { name: "search" }));

    expect(await screen.findByRole("combobox", { name: /tool name/i })).toHaveTextContent("search");
  });

  it("points at the registry when no MCP server is registered", async () => {
    server.use(http.get(SERVERS_URL, () => envelope([])));
    render(<Harness />);

    expect(await screen.findByText(/No MCP servers are registered/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Register one" })).toHaveAttribute(
      "href",
      "/admin/mcp-servers"
    );
  });

  it("surfaces a registry failure and recovers on retry", async () => {
    let attempt = 0;
    server.use(
      http.get(SERVERS_URL, () => {
        attempt += 1;
        return attempt === 1
          ? envelopeErr("INTERNAL_ERROR", "registry exploded", 500)
          : envelope([]);
      })
    );
    const user = userEvent.setup();
    render(<Harness />);

    expect(await screen.findByText("Could not load the MCP server registry.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText(/No MCP servers are registered/)).toBeInTheDocument();
  });

  it("renders read-only as plain text with no controls", async () => {
    render(
      <McpToolField
        readOnly
        idPrefix="mcpToolMock"
        mcpServerId="mcp-1"
        toolName="search"
        onChange={() => {}}
      />
    );

    expect(await screen.findByText("my-mcp-server")).toBeInTheDocument();
    expect(screen.getByText("search")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Select MCP server…" })).not.toBeInTheDocument();
  });
});
