import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { MCP_SERVER_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import EditMcpServerPage from "./page";

function setup() {
  vi.mocked(useParams).mockReturnValue({ serverId: "mcp-1" });
}

describe("EditMcpServerPage", () => {
  it("prefills form with server data including headers", async () => {
    setup();
    render(<EditMcpServerPage />);
    await waitFor(() => expect(screen.getByDisplayValue("My MCP Server")).toBeInTheDocument());
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

    render(<EditMcpServerPage />);
    await waitFor(() => screen.getByDisplayValue("My MCP Server"));
    await userEvent.click(screen.getByRole("button", { name: "Remove headers row 1" }));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "My MCP Server",
        url: "https://mcp.example.com/mcp",
        headers: {},
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
    });

    render(<EditMcpServerPage />);
    await waitFor(() => screen.getByDisplayValue("My MCP Server"));
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
    });
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/mcp-servers/:serverId", deleteSpy));

    render(<EditMcpServerPage />);
    await waitFor(() => screen.getByDisplayValue("My MCP Server"));
    await userEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalled());
    expect(pushMock).toHaveBeenCalledWith("/admin/mcp-servers");
  });

  it("shows error on load failure", async () => {
    setup();
    server.use(
      http.get(
        "http://localhost:8000/api/v1/mcp-servers/:serverId",
        () => new HttpResponse(null, { status: 404 })
      )
    );

    render(<EditMcpServerPage />);
    await waitFor(() => expect(screen.getByText(/404/)).toBeInTheDocument());
  });
});
