import userEvent from "@testing-library/user-event";
import { delay, http } from "msw";
import { useParams } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { DEVELOPER, REQUESTER } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { MCP_TOOL_1, MCP_TOOL_MOCK_1, MCP_TOOL_MOCK_BUILTIN } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import McpToolMockDetailPage from "./page";

function setup() {
  vi.mocked(useParams).mockReturnValue({ mockId: "mock-1" });
}

/** Render the page as a developer — the role every tool-mock write requires. */
function renderPage() {
  return render(<McpToolMockDetailPage />, { preloadedState: DEVELOPER });
}

describe("McpToolMockDetailPage", () => {
  it("titles the page and ends the breadcrumb trail with the mock's name", async () => {
    setup();
    renderPage();
    expect(
      await screen.findByRole("heading", { name: "search returns nothing" })
    ).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByText("search returns nothing")).toHaveAttribute("aria-current", "page");
  });

  it("prefills the form, showing the stored JSON response pretty-printed", async () => {
    setup();
    renderPage();
    await waitFor(() =>
      expect(screen.getByDisplayValue("search returns nothing")).toBeInTheDocument()
    );
    // The MCP tool is now a two-step picker: the server named on a chip, the
    // tool selected in the dropdown loaded from it.
    expect(await screen.findByRole("button", { name: "Remove my-mcp-server" })).toBeInTheDocument();
    expect(await screen.findByRole("combobox", { name: /tool name/i })).toHaveTextContent("search");
    expect(screen.getByLabelText("Response 1 value")).toHaveValue('{\n  "hits": []\n}');
  });

  it("restores a built-in mock's target and its successive responses", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/mcp-tool-mocks/:mockId", () =>
        envelope(MCP_TOOL_MOCK_BUILTIN)
      )
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("Call #2")).toBeInTheDocument());
    expect(screen.getByRole("tab", { name: /built-in tool/i })).toHaveAttribute(
      "aria-selected",
      "true"
    );
    expect(screen.queryByLabelText(/mcp server/i)).not.toBeInTheDocument();
  });

  it("submits the edited responses", async () => {
    setup();
    const user = userEvent.setup();
    let body: unknown;
    server.use(
      http.patch("http://localhost:8000/api/v1/mcp-tool-mocks/:mockId", async ({ request }) => {
        body = await request.json();
        return envelope(MCP_TOOL_MOCK_1);
      })
    );

    renderPage();
    const value = await screen.findByLabelText("Response 1 value");
    await user.clear(value);
    await user.type(value, '{{"hits": 1}');
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(body).toEqual({
        name: "search returns nothing",
        description: null,
        mcpServerId: "mcp-1",
        toolName: "search",
        responses: [{ kind: "structured", value: { hits: 1 } }],
      })
    );
  });

  it("writes a changed tag set to the mock's tags sub-resource on save", async () => {
    setup();
    const user = userEvent.setup();
    let tagBody: unknown;
    server.use(
      http.patch("http://localhost:8000/api/v1/mcp-tool-mocks/:mockId", () =>
        envelope(MCP_TOOL_MOCK_1)
      ),
      http.put("http://localhost:8000/api/v1/mcp-tool-mocks/:mockId/tags", async ({ request }) => {
        tagBody = await request.json();
        return envelope(MCP_TOOL_MOCK_1);
      })
    );

    renderPage();
    await user.click(await screen.findByRole("button", { name: "Select tags…" }));
    const dialog = await screen.findByRole("dialog", { name: "Select tags" });
    await user.click(within(dialog).getByRole("button", { name: "aws" }));
    await user.click(within(dialog).getByRole("button", { name: "Select" }));
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(tagBody).toEqual({ tagIds: ["tag-2"] }));
  });

  it("deletes the mock after confirming", async () => {
    setup();
    const user = userEvent.setup();
    let deleted = false;
    server.use(
      http.delete("http://localhost:8000/api/v1/mcp-tool-mocks/:mockId", () => {
        deleted = true;
        return envelope(null);
      })
    );

    renderPage();
    await user.click(await screen.findByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(deleted).toBe(true));
  });

  it("holds the output-format panel with a skeleton until the listing lands", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/mcp-servers/:serverId/tools", async () => {
        await delay(50);
        return envelope([MCP_TOOL_1]);
      })
    );
    renderPage();

    // The stored tool name is on screen long before the server answers, so the
    // panel takes its place rather than appearing out of nowhere later.
    expect(
      await screen.findByRole("status", { name: /loading output format/i })
    ).toBeInTheDocument();

    await waitFor(() =>
      expect(
        screen.queryByRole("status", { name: /loading output format/i })
      ).not.toBeInTheDocument()
    );
    // `array` appears only in the tool's declared output schema, never in the
    // stored response the editor below is prefilled with.
    expect(screen.getByText(/"array"/)).toBeInTheDocument();
  });

  it("drops the skeleton instead of spinning forever when the listing fails", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/mcp-servers/:serverId/tools", () =>
        envelopeErr("MCP_ERROR", "unreachable", 502)
      )
    );
    renderPage();

    // The tool picker owns the error and its Retry; the panel just stays away.
    await screen.findByRole("combobox", { name: /tool name/i });
    expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(
      screen.queryByRole("status", { name: /loading output format/i })
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /output format/i })).not.toBeInTheDocument();
  });

  it("renders read-only for a viewer without the developer role", async () => {
    setup();
    render(<McpToolMockDetailPage />, { preloadedState: REQUESTER });
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "search returns nothing" })).toBeInTheDocument()
    );
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
  });

  it("shows the access-denied state when the record is forbidden", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/mcp-tool-mocks/:mockId", () =>
        envelopeErr("FORBIDDEN", "no", 403)
      )
    );
    renderPage();
    expect(await screen.findByText(/access denied/i)).toBeInTheDocument();
  });
});
