import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { store as appStore } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import McpServersPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

/** Turn on a column hidden by default, through the page's own column picker. */
async function showColumn(user: ReturnType<typeof userEvent.setup>, label: string) {
  await user.click(screen.getByRole("button", { name: "Columns" }));
  await user.click(await screen.findByRole("checkbox", { name: label }));
}

describe("McpServersPage", () => {
  it("shows loading state initially", () => {
    render(<McpServersPage />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders server row after load", async () => {
    render(<McpServersPage />);
    await waitFor(() => expect(screen.getByText("my-mcp-server")).toBeInTheDocument());
    expect(screen.getByText("https://mcp.example.com/mcp")).toBeInTheDocument();
  });

  it("renders a stdio server's command line", async () => {
    render(<McpServersPage />);
    await waitFor(() => expect(screen.getByText("local-files")).toBeInTheDocument());
    expect(screen.getByText("npx -y files-mcp@0.3.0")).toBeInTheDocument();
  });

  it("hides the transport and headers columns by default", async () => {
    render(<McpServersPage />);
    await waitFor(() => screen.getByText("my-mcp-server"));
    expect(screen.queryByText("HTTP")).not.toBeInTheDocument();
    expect(screen.queryByText("1 header")).not.toBeInTheDocument();
  });

  it("renders each server's transport once the column is shown", async () => {
    const user = userEvent.setup();
    render(<McpServersPage />);
    await waitFor(() => screen.getByText("my-mcp-server"));

    await showColumn(user, "Transport");

    expect(screen.getByText("HTTP")).toBeInTheDocument();
    expect(screen.getByText("stdio")).toBeInTheDocument();
  });

  it("renders the header and variable counts once the column is shown", async () => {
    const user = userEvent.setup();
    render(<McpServersPage />);
    await waitFor(() => screen.getByText("my-mcp-server"));

    await showColumn(user, "Headers / Env");

    expect(screen.getByText("1 header")).toBeInTheDocument();
    expect(screen.getByText("1 variable")).toBeInTheDocument();
  });

  it("name links to the edit page", async () => {
    render(<McpServersPage />);
    await waitFor(() => screen.getByText("my-mcp-server"));
    expect(screen.getByRole("link", { name: "my-mcp-server" })).toHaveAttribute(
      "href",
      "/admin/mcp-servers/mcp-1"
    );
  });

  it("shows empty state when no servers", async () => {
    server.use(http.get("http://localhost:8000/api/v1/mcp-servers", () => envelope([])));
    render(<McpServersPage />);
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
    render(<McpServersPage />);
    await waitFor(() =>
      expect(appStore.getState().toast.items.at(-1)).toMatchObject({
        message: "Internal server error",
        variant: "error",
      })
    );
  });

  it("add server link is present", async () => {
    render(<McpServersPage />);
    await waitFor(() => screen.getByText("my-mcp-server"));
    expect(screen.getByRole("link", { name: /add server/i })).toHaveAttribute(
      "href",
      "/admin/mcp-servers/new"
    );
  });

  it("calls delete api after confirm", async () => {
    const user = userEvent.setup();
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/mcp-servers/:id", deleteSpy));

    render(<McpServersPage />);
    await waitFor(() => screen.getByText("my-mcp-server"));
    await user.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    expect(deleteSpy).toHaveBeenCalled();
  });
});
