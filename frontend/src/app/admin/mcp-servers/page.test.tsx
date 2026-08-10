import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { store as appStore } from "@/store";
import { DEVELOPER, REQUESTER } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import McpServersPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

/** Render the list as a developer — the role every MCP server write requires. */
function renderPage() {
  return render(<McpServersPage />, { preloadedState: DEVELOPER });
}

/** Turn on a column hidden by default, through the page's own column picker. */
async function showColumn(user: ReturnType<typeof userEvent.setup>, label: string) {
  await user.click(screen.getByRole("button", { name: "Columns" }));
  await user.click(await screen.findByRole("checkbox", { name: label }));
}

describe("McpServersPage", () => {
  it("shows loading state initially", () => {
    renderPage();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders server row after load", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("my-mcp-server")).toBeInTheDocument());
    expect(screen.getByText("https://mcp.example.com/mcp")).toBeInTheDocument();
  });

  it("renders a stdio server's command line", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("local-files")).toBeInTheDocument());
    expect(screen.getByText("npx -y files-mcp@0.3.0")).toBeInTheDocument();
  });

  it("hides the transport and headers columns by default", async () => {
    renderPage();
    await waitFor(() => screen.getByText("my-mcp-server"));
    expect(screen.queryByText("HTTP")).not.toBeInTheDocument();
    expect(screen.queryByText("1 header")).not.toBeInTheDocument();
  });

  it("renders each server's transport once the column is shown", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText("my-mcp-server"));

    await showColumn(user, "Transport");

    expect(screen.getByText("HTTP")).toBeInTheDocument();
    expect(screen.getByText("stdio")).toBeInTheDocument();
  });

  it("renders the header and variable counts once the column is shown", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText("my-mcp-server"));

    await showColumn(user, "Headers / Env");

    expect(screen.getByText("1 header")).toBeInTheDocument();
    expect(screen.getByText("1 variable")).toBeInTheDocument();
  });

  it("name links to the edit page", async () => {
    renderPage();
    await waitFor(() => screen.getByText("my-mcp-server"));
    expect(screen.getByRole("link", { name: "my-mcp-server" })).toHaveAttribute(
      "href",
      "/admin/mcp-servers/mcp-1"
    );
  });

  it("shows empty state when no servers", async () => {
    server.use(http.get("http://localhost:8000/api/v1/mcp-servers", () => envelope([])));
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("No MCP servers registered yet.")).toBeInTheDocument()
    );
  });

  it("shows an error toast on api failure", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/mcp-servers", () =>
        envelopeErr("INTERNAL_ERROR", "Internal server error", 500)
      )
    );
    renderPage();
    await waitFor(() =>
      expect(appStore.getState().toast.items.at(-1)).toMatchObject({
        message: "Internal server error",
        variant: "error",
      })
    );
  });

  it("add server link is present", async () => {
    renderPage();
    await waitFor(() => screen.getByText("my-mcp-server"));
    expect(screen.getByRole("link", { name: /add server/i })).toHaveAttribute(
      "href",
      "/admin/mcp-servers/new"
    );
  });

  it("offers the registry browser", async () => {
    renderPage();
    await waitFor(() => screen.getByText("my-mcp-server"));
    expect(screen.getByRole("button", { name: /browse registry/i })).toBeInTheDocument();
  });

  it("calls delete api after confirm", async () => {
    const user = userEvent.setup();
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/mcp-servers/:id", deleteSpy));

    renderPage();
    await waitFor(() => screen.getByText("my-mcp-server"));
    await user.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    expect(deleteSpy).toHaveBeenCalled();
  });

  describe("without the developer role", () => {
    it("hides every write entry point", async () => {
      render(<McpServersPage />, { preloadedState: REQUESTER });
      await waitFor(() => screen.getByText("my-mcp-server"));

      expect(screen.queryByRole("link", { name: /add server/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /browse registry/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
      expect(screen.queryByRole("columnheader", { name: "Actions" })).not.toBeInTheDocument();
      // The list itself stays readable — only the write actions are gated.
      expect(screen.getByRole("link", { name: "my-mcp-server" })).toBeInTheDocument();
    });
  });
});
