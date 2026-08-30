import type { UserEvent } from "@testing-library/user-event";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";
import { DEVELOPER, REQUESTER } from "@/test/auth-state";
import { envelope } from "@/test/msw/envelope";
import { MCP_TOOL_MOCK_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import NewMcpToolMockPage from "./page";

/** Render the form as a developer — the role registering a tool mock requires. */
function renderPage() {
  return render(<NewMcpToolMockPage />, { preloadedState: DEVELOPER });
}

/**
 * Point the MCP mock at `my-mcp-server`'s `search` tool the way an operator
 * does: open the server dialog, choose the server, then pick the tool from the
 * list loaded from it (the default handler advertises `search`).
 */
async function pickServerAndTool(user: UserEvent) {
  await user.click(await screen.findByRole("button", { name: "Select MCP server…" }));
  await user.click(await screen.findByRole("radio", { name: "my-mcp-server" }));
  await user.click(screen.getByRole("button", { name: "Select" }));
  const toolSelect = await screen.findByRole("combobox", { name: /tool name/i });
  await waitFor(() => expect(toolSelect).toBeEnabled());
  await user.click(toolSelect);
  await user.click(await screen.findByRole("option", { name: "search" }));
}

/** Capture the body the create request sends, returning a getter for it. */
function captureCreate(): () => unknown {
  let body: unknown;
  server.use(
    http.post("http://localhost:8000/api/v1/mcp-tool-mocks", async ({ request }) => {
      body = await request.json();
      return envelope({ ...MCP_TOOL_MOCK_1, id: "new-id" }, 201);
    })
  );
  return () => body;
}

describe("NewMcpToolMockPage", () => {
  it("renders the name field and the MCP server picker", async () => {
    renderPage();
    expect(screen.getByLabelText(/^name/i)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Select MCP server…" })).toBeInTheDocument();
  });

  it("starts with one structured response", () => {
    renderPage();
    expect(screen.getByText("Call #1")).toBeInTheDocument();
    expect(screen.queryByText("Call #2")).not.toBeInTheDocument();
  });

  it("submits an MCP tool mock with the chosen server and parsed JSON", async () => {
    const user = userEvent.setup();
    const body = captureCreate();

    renderPage();
    await user.type(screen.getByLabelText(/^name/i), "no hits");
    await pickServerAndTool(user);
    const value = screen.getByLabelText("Response 1 value");
    await user.clear(value);
    await user.type(value, '{{"hits": 0}');
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(body()).toEqual({
        name: "no hits",
        description: null,
        mcpServerId: "mcp-1",
        toolName: "search",
        responses: [{ kind: "structured", value: { hits: 0 } }],
      })
    );
  });

  it("submits a built-in mock with a null server id", async () => {
    const user = userEvent.setup();
    const body = captureCreate();

    renderPage();
    await user.type(screen.getByLabelText(/^name/i), "auto approve");
    await user.click(screen.getByRole("tab", { name: /built-in tool/i }));
    const value = screen.getByLabelText("Response 1 value");
    await user.clear(value);
    await user.type(value, '{{"status": "approved"}');
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(body()).toEqual({
        name: "auto approve",
        description: null,
        mcpServerId: null,
        toolName: "request_approval",
        responses: [{ kind: "structured", value: { status: "approved" } }],
      })
    );
  });

  it("adds and removes successive responses", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /add response/i }));
    expect(screen.getByText("Call #2")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Remove response 2" }));
    expect(screen.queryByText("Call #2")).not.toBeInTheDocument();
  });

  it("refuses to remove the only response", () => {
    renderPage();
    expect(screen.getByRole("button", { name: "Remove response 1" })).toBeDisabled();
  });

  it("rejects a structured response that is not valid JSON", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText(/^name/i), "broken");
    await pickServerAndTool(user);
    const value = screen.getByLabelText("Response 1 value");
    await user.clear(value);
    await user.type(value, "not json");
    await user.click(screen.getByRole("button", { name: /save/i }));

    expect(await screen.findByText("Must be valid JSON")).toBeVisible();
  });

  it("rejects a structured response that is not an object", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText(/^name/i), "scalar");
    await pickServerAndTool(user);
    const value = screen.getByLabelText("Response 1 value");
    await user.clear(value);
    await user.type(value, "42");
    await user.click(screen.getByRole("button", { name: /save/i }));

    expect(await screen.findByText("Must be a JSON object")).toBeVisible();
  });

  it("refuses the form to a viewer without the developer role", () => {
    render(<NewMcpToolMockPage />, { preloadedState: REQUESTER });
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
  });
});
