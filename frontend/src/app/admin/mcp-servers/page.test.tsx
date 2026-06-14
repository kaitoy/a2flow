import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import McpServersPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

describe("McpServersPage", () => {
  it("shows loading state initially", () => {
    render(<McpServersPage />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders server row after load", async () => {
    render(<McpServersPage />);
    await waitFor(() => expect(screen.getByText("my-mcp-server")).toBeInTheDocument());
    expect(screen.getByText("https://mcp.example.com/mcp")).toBeInTheDocument();
    expect(screen.getByText("1 header")).toBeInTheDocument();
  });

  it("shows empty state when no servers", async () => {
    server.use(http.get("http://localhost:8000/api/v1/mcp-servers", () => envelope([])));
    render(<McpServersPage />);
    await waitFor(() =>
      expect(screen.getByText("No MCP servers registered yet.")).toBeInTheDocument()
    );
  });

  it("shows error banner on api failure", async () => {
    server.use(
      http.get(
        "http://localhost:8000/api/v1/mcp-servers",
        () => new HttpResponse(null, { status: 500 })
      )
    );
    render(<McpServersPage />);
    await waitFor(() => expect(screen.getByText(/500/)).toBeInTheDocument());
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
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    expect(deleteSpy).toHaveBeenCalled();
  });
});
