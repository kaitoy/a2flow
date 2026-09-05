import type { UserEvent } from "@testing-library/user-event";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { McpToolPicker } from "./mcp-tool-picker";

const BASE = "http://localhost:8000";
const SERVERS_URL = `${BASE}/api/v1/mcp-servers`;
const TOOLS_URL = `${BASE}/api/v1/mcp-servers/:serverId/tools`;

/** Minimal `McpToolInfo` — the picker only ever reads the name. */
function tool(name: string) {
  return { name, description: null, inputSchema: {} };
}

/**
 * Give each registered server its own tools, so "only the picked server's
 * tools are offered" is actually assertable. The shared handler serves the same
 * single tool for every server.
 */
function serveToolsPerServer() {
  server.use(
    http.get(TOOLS_URL, ({ params }) =>
      envelope(params.serverId === "mcp-1" ? [tool("search"), tool("fetch")] : [tool("read")])
    )
  );
}

/**
 * Controlled harness. The picker owns no selection of its own, so a static
 * `value` prop would make every pick silently fail to stick.
 */
function Harness({
  initial = [],
  initialExempt = [],
  onChange,
  onExemptChange,
}: {
  initial?: string[];
  initialExempt?: string[];
  onChange?: (next: string[]) => void;
  onExemptChange?: (next: string[]) => void;
}) {
  const [value, setValue] = useState(initial);
  const [exempt, setExempt] = useState(initialExempt);
  return (
    <McpToolPicker
      value={value}
      onChange={(next) => {
        setValue(next);
        onChange?.(next);
      }}
      exempt={exempt}
      onExemptChange={(next) => {
        setExempt(next);
        onExemptChange?.(next);
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

/** The tool dropdown, once its options have arrived. */
async function toolSelect() {
  const select = await screen.findByRole("combobox", { name: "Tool" });
  await waitFor(() => expect(select).toBeEnabled());
  return select;
}

/** Open the tool dropdown and add `name`. */
async function pickTool(user: UserEvent, name: string) {
  await user.click(await toolSelect());
  await user.click(await screen.findByRole("option", { name }));
}

describe("McpToolPicker", () => {
  it("queries no MCP server for tools until one is picked", async () => {
    let toolCalls = 0;
    server.use(
      http.get(TOOLS_URL, () => {
        toolCalls += 1;
        return envelope([tool("search")]);
      })
    );

    render(<Harness />);

    // The registry read has landed — the pick entry point is on screen...
    expect(await screen.findByRole("button", { name: "Select MCP server…" })).toBeInTheDocument();
    // ...and not one live MCP connection was made to get there.
    expect(toolCalls).toBe(0);
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

  it("reports the composite binding and shows a chip when a tool is added", async () => {
    serveToolsPerServer();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness onChange={onChange} />);

    await pickServer(user, "my-mcp-server");
    await pickTool(user, "search");

    expect(onChange).toHaveBeenCalledWith(["mcp-1::search"]);
    expect(
      await screen.findByRole("button", { name: "Remove my-mcp-server: search" })
    ).toBeInTheDocument();
  });

  it("keeps earlier picks when tools are added from a second server", async () => {
    serveToolsPerServer();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness onChange={onChange} />);

    await pickServer(user, "my-mcp-server");
    await pickTool(user, "search");
    await pickServer(user, "local-files");
    await pickTool(user, "read");

    expect(onChange).toHaveBeenLastCalledWith(["mcp-1::search", "mcp-2::read"]);
    expect(
      screen.getByRole("button", { name: "Remove my-mcp-server: search" })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove local-files: read" })).toBeInTheDocument();
  });

  it("stops offering a tool that is already bound", async () => {
    serveToolsPerServer();
    const user = userEvent.setup();
    render(<Harness />);

    await pickServer(user, "my-mcp-server");
    await pickTool(user, "search");
    await user.click(await toolSelect());

    expect(await screen.findByRole("option", { name: "fetch" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "search" })).not.toBeInTheDocument();
  });

  it("says so when every advertised tool has been added", async () => {
    server.use(http.get(TOOLS_URL, () => envelope([tool("search")])));
    const user = userEvent.setup();
    render(<Harness />);

    await pickServer(user, "my-mcp-server");
    await pickTool(user, "search");

    expect(await screen.findByRole("combobox", { name: "Tool" })).toHaveTextContent(
      "All tools added"
    );
  });

  it("removes a binding when its chip is dismissed", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness initial={["mcp-1::search", "mcp-2::read"]} onChange={onChange} />);

    await user.click(await screen.findByRole("button", { name: "Remove my-mcp-server: search" }));

    expect(onChange).toHaveBeenCalledWith(["mcp-2::read"]);
  });

  it("labels a prefilled binding with its server's name", async () => {
    render(<Harness initial={["mcp-2::read"]} />);

    expect(
      await screen.findByRole("button", { name: "Remove local-files: read" })
    ).toBeInTheDocument();
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
    expect(screen.getByRole("combobox", { name: "Tool" })).toHaveTextContent(
      "Could not load tools"
    );

    await user.click(screen.getByRole("button", { name: "Retry" }));
    await pickTool(user, "search");

    expect(
      await screen.findByRole("button", { name: "Remove my-mcp-server: search" })
    ).toBeInTheDocument();
  });

  it("offers no input-approval choice until a tool is bound", async () => {
    render(<Harness />);

    expect(await screen.findByRole("button", { name: "Select MCP server…" })).toBeInTheDocument();
    expect(screen.queryByText("Skip Input Approval")).not.toBeInTheDocument();
  });

  it("bounds a newly added tool's input by default", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await pickServer(user, "my-mcp-server");
    await pickTool(user, "search");

    expect(await screen.findByText("Skip Input Approval")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "my-mcp-server: search" })).not.toBeChecked();
  });

  it("reports the tool checked as needing no input approval", async () => {
    const onExemptChange = vi.fn();
    render(<Harness initial={["mcp-1::search"]} onExemptChange={onExemptChange} />);

    await userEvent.click(await screen.findByRole("checkbox", { name: "my-mcp-server: search" }));

    expect(onExemptChange).toHaveBeenCalledWith(["mcp-1::search"]);
  });

  it("shows a prefilled exemption as checked", async () => {
    render(<Harness initial={["mcp-1::search"]} initialExempt={["mcp-1::search"]} />);

    expect(await screen.findByRole("checkbox", { name: "my-mcp-server: search" })).toBeChecked();
  });

  it("drops the exemption when its tool is unbound", async () => {
    const onExemptChange = vi.fn();
    render(
      <Harness
        initial={["mcp-1::search"]}
        initialExempt={["mcp-1::search"]}
        onExemptChange={onExemptChange}
      />
    );

    await userEvent.click(
      await screen.findByRole("button", { name: "Remove my-mcp-server: search" })
    );

    // Otherwise re-binding the same tool later would silently bring the
    // exemption back with it.
    expect(onExemptChange).toHaveBeenCalledWith([]);
    expect(screen.queryByText("Skip Input Approval")).not.toBeInTheDocument();
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
    render(<Harness />);

    expect(await screen.findByText("Could not load the MCP server registry.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText(/No MCP servers are registered/)).toBeInTheDocument();
  });

  it("points at the registry when no MCP server is registered", async () => {
    server.use(http.get(SERVERS_URL, () => envelope([])));
    render(<Harness />);

    expect(await screen.findByText(/No MCP servers are registered/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Register one" })).toHaveAttribute(
      "href",
      "/admin/mcp-servers"
    );
    expect(screen.queryByRole("button", { name: "Select MCP server…" })).not.toBeInTheDocument();
  });
});
