import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { MCP_SERVER_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import NewMcpServerPage from "./page";

describe("NewMcpServerPage", () => {
  it("renders name and url inputs", () => {
    render(<NewMcpServerPage />);
    expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/url/i)).toBeInTheDocument();
  });

  it("submits create api with headers from key/value rows", async () => {
    const user = userEvent.setup();
    let receivedBody: unknown;
    server.use(
      http.post("http://localhost:8000/api/v1/mcp-servers", async ({ request }) => {
        receivedBody = await request.json();
        return envelope({ ...MCP_SERVER_1, id: "new-id" }, 201);
      })
    );

    render(<NewMcpServerPage />);
    await user.type(screen.getByLabelText(/name/i), "test-server");
    await user.type(screen.getByLabelText(/url/i), "https://mcp.test/mcp");
    await user.click(screen.getByRole("button", { name: /add row/i }));
    await user.type(screen.getByLabelText("headers key 1"), "Authorization");
    await user.type(screen.getByLabelText("headers value 1"), "Bearer abc");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "test-server",
        url: "https://mcp.test/mcp",
        headers: { Authorization: "Bearer abc" },
      })
    );
  });

  it("navigates to list on success", async () => {
    const user = userEvent.setup();
    const pushMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({
      push: pushMock,
      replace: vi.fn(),
      back: vi.fn(),
      prefetch: vi.fn(),
      refresh: vi.fn(),
      forward: vi.fn(),
    });

    render(<NewMcpServerPage />);
    await user.type(screen.getByLabelText(/name/i), "test-server");
    await user.type(screen.getByLabelText(/url/i), "https://mcp.test/mcp");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/mcp-servers"));
  });

  it("shows validation error on blur when url is invalid", async () => {
    const user = userEvent.setup();
    render(<NewMcpServerPage />);
    await user.type(screen.getByLabelText(/url/i), "not-a-url");
    await user.tab();
    await waitFor(() => expect(screen.getByText(/invalid/i)).toBeInTheDocument());
  });

  it("shows error on api failure", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(
        "http://localhost:8000/api/v1/mcp-servers",
        () => new HttpResponse(null, { status: 422 })
      )
    );

    render(<NewMcpServerPage />);
    await user.type(screen.getByLabelText(/name/i), "test-server");
    await user.type(screen.getByLabelText(/url/i), "https://mcp.test/mcp");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(screen.getByText(/422/)).toBeInTheDocument());
  });
});
