import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { DEVELOPER, REQUESTER } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { MCP_SERVER_1, MCP_STDIO_SERVER, MCP_TOOL_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import McpServerDetailPage from "./page";

function setup() {
  vi.mocked(useParams).mockReturnValue({ serverId: "mcp-1" });
}

/** Render the page as a developer — the role every MCP server write requires. */
function renderPage() {
  return render(<McpServerDetailPage />, { preloadedState: DEVELOPER });
}

describe("McpServerDetailPage", () => {
  it("titles the page and ends the breadcrumb trail with the server's name", async () => {
    setup();
    renderPage();
    expect(await screen.findByRole("heading", { name: "my-mcp-server" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByText("my-mcp-server")).toHaveAttribute("aria-current", "page");
  });

  it("prefills form with server data including headers", async () => {
    setup();
    renderPage();
    await waitFor(() => expect(screen.getByDisplayValue("my-mcp-server")).toBeInTheDocument());
    expect(screen.getByDisplayValue("https://mcp.example.com/mcp")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Authorization")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Bearer secret")).toBeInTheDocument();
  });

  it("submits update api with edited headers", async () => {
    setup();
    let receivedBody: unknown;
    server.use(
      http.patch("http://localhost:8000/api/v1/mcp-servers/:serverId", async ({ request }) => {
        receivedBody = await request.json();
        return envelope(MCP_SERVER_1);
      })
    );

    renderPage();
    await waitFor(() => screen.getByDisplayValue("my-mcp-server"));
    await userEvent.click(screen.getByRole("button", { name: "Remove headers row 1" }));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "my-mcp-server",
        description: null,
        transport: "streamable_http",
        url: "https://mcp.example.com/mcp",
        headers: {},
      })
    );
  });

  it("prefills command, args, and env for a stdio server", async () => {
    vi.mocked(useParams).mockReturnValue({ serverId: "mcp-2" });
    server.use(
      http.get("http://localhost:8000/api/v1/mcp-servers/:serverId", () =>
        envelope(MCP_STDIO_SERVER)
      )
    );

    renderPage();
    await waitFor(() => expect(screen.getByDisplayValue("local-files")).toBeInTheDocument());
    expect(screen.getByRole("tab", { name: "npx" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByDisplayValue("-y")).toBeInTheDocument();
    expect(screen.getByDisplayValue("files-mcp@0.3.0")).toBeInTheDocument();
    expect(screen.getByDisplayValue("API_KEY")).toBeInTheDocument();
    expect(screen.queryByLabelText(/^url$/i)).not.toBeInTheDocument();
  });

  it("drops url and headers when switching a server to stdio", async () => {
    setup();
    let receivedBody: unknown;
    server.use(
      http.patch("http://localhost:8000/api/v1/mcp-servers/:serverId", async ({ request }) => {
        receivedBody = await request.json();
        return envelope(MCP_STDIO_SERVER);
      })
    );

    renderPage();
    await waitFor(() => screen.getByDisplayValue("my-mcp-server"));
    await userEvent.click(screen.getByRole("tab", { name: "stdio" }));
    await userEvent.click(screen.getByRole("tab", { name: "uvx" }));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "my-mcp-server",
        description: null,
        transport: "stdio",
        command: "uvx",
        args: [],
        env: {},
      })
    );
  });

  it("navigates to list after save", async () => {
    setup();
    const pushMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({
      push: pushMock,
      replace: vi.fn(),
      back: vi.fn(),
      prefetch: vi.fn(),
      refresh: vi.fn(),
      forward: vi.fn(),
      bfcacheId: "",
    });

    renderPage();
    await waitFor(() => screen.getByDisplayValue("my-mcp-server"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/mcp-servers"));
  });

  it("calls delete api and navigates after confirm", async () => {
    setup();
    const pushMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({
      push: pushMock,
      replace: vi.fn(),
      back: vi.fn(),
      prefetch: vi.fn(),
      refresh: vi.fn(),
      forward: vi.fn(),
      bfcacheId: "",
    });
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/mcp-servers/:serverId", deleteSpy));

    renderPage();
    await waitFor(() => screen.getByDisplayValue("my-mcp-server"));
    await userEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalled());
    expect(pushMock).toHaveBeenCalledWith("/admin/mcp-servers");
  });

  it("fetches and renders the server's tools on demand", async () => {
    setup();
    renderPage();
    await waitFor(() => screen.getByDisplayValue("my-mcp-server"));

    await userEvent.click(screen.getByRole("button", { name: /fetch tools/i }));

    await waitFor(() => expect(screen.getByText(MCP_TOOL_1.name)).toBeInTheDocument());
  });

  it("shows error on load failure", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/mcp-servers/:serverId", () =>
        envelopeErr("NOT_FOUND", "McpServer not found", 404)
      )
    );

    renderPage();
    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "McpServer not found",
        variant: "error",
      })
    );
  });

  it("shows the access-denied state and no toast on a FORBIDDEN load failure", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/mcp-servers/:serverId", () =>
        envelopeErr("FORBIDDEN", "Requires developer", 403)
      )
    );
    const beforeCount = store.getState().toast.items.length;

    renderPage();

    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(store.getState().toast.items.length).toBe(beforeCount);
  });

  describe("without the developer role", () => {
    it("renders the connection fields as values instead of controls", async () => {
      setup();
      render(<McpServerDetailPage />, { preloadedState: REQUESTER });

      expect(await screen.findByRole("heading", { name: "my-mcp-server" })).toBeInTheDocument();
      expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
      expect(screen.queryByRole("tab")).not.toBeInTheDocument();
      expect(screen.getByText("Streamable HTTP")).toBeInTheDocument();
      expect(screen.getByText("https://mcp.example.com/mcp")).toBeInTheDocument();
      expect(screen.getByText("Authorization: Bearer secret")).toBeInTheDocument();
    });

    it("renders a stdio server's command, arguments, and environment as values", async () => {
      vi.mocked(useParams).mockReturnValue({ serverId: "mcp-2" });
      server.use(
        http.get("http://localhost:8000/api/v1/mcp-servers/:serverId", () =>
          envelope(MCP_STDIO_SERVER)
        )
      );

      render(<McpServerDetailPage />, { preloadedState: REQUESTER });

      expect(await screen.findByRole("heading", { name: "local-files" })).toBeInTheDocument();
      expect(screen.getByText("stdio")).toBeInTheDocument();
      expect(screen.getByText("npx")).toBeInTheDocument();
      // One argument per line; getByText's normalizer collapses the newline.
      expect(screen.getByText("-y files-mcp@0.3.0")).toBeInTheDocument();
      // biome-ignore lint/suspicious/noTemplateCurlyInString: literal secret-reference syntax stored by the API
      expect(screen.getByText("API_KEY: ${secret:files-key}")).toBeInTheDocument();
    });

    it("hides Save and Delete and offers Back instead of Cancel", async () => {
      setup();
      render(<McpServerDetailPage />, { preloadedState: REQUESTER });

      expect(await screen.findByRole("heading", { name: "my-mcp-server" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /^delete$/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /back/i })).toBeInTheDocument();
    });
  });
});
