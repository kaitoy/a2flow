import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { DEVELOPER, REQUESTER } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { MCP_SERVER_1, MCP_STDIO_SERVER } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import NewMcpServerPage from "./page";

/** Render the form as a developer — the role registering an MCP server requires. */
function renderPage() {
  return render(<NewMcpServerPage />, { preloadedState: DEVELOPER });
}

describe("NewMcpServerPage", () => {
  it("renders name and url inputs", () => {
    renderPage();
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

    renderPage();
    await user.type(screen.getByLabelText(/name/i), "test-server");
    await user.type(screen.getByLabelText(/url/i), "https://mcp.test/mcp");
    await user.click(screen.getByRole("button", { name: /add row/i }));
    await user.type(screen.getByLabelText("headers key 1"), "Authorization");
    await user.type(screen.getByLabelText("headers value 1"), "Bearer abc");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "test-server",
        description: null,
        transport: "streamable_http",
        url: "https://mcp.test/mcp",
        headers: { Authorization: "Bearer abc" },
      })
    );
  });

  it("submits create api with command, args, and env when transport is stdio", async () => {
    const user = userEvent.setup();
    let receivedBody: unknown;
    server.use(
      http.post("http://localhost:8000/api/v1/mcp-servers", async ({ request }) => {
        receivedBody = await request.json();
        return envelope({ ...MCP_STDIO_SERVER, id: "new-id" }, 201);
      })
    );

    renderPage();
    await user.type(screen.getByLabelText(/name/i), "local-files");
    await user.click(screen.getByRole("tab", { name: "stdio" }));
    await user.click(screen.getByRole("tab", { name: "npx" }));
    await user.click(screen.getByRole("button", { name: /add argument/i }));
    await user.type(screen.getByLabelText("args value 1"), "-y");
    await user.click(screen.getByRole("button", { name: /add row/i }));
    await user.type(screen.getByLabelText("env key 1"), "API_KEY");
    await user.type(screen.getByLabelText("env value 1"), "secret");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "local-files",
        description: null,
        transport: "stdio",
        command: "npx",
        args: ["-y"],
        env: { API_KEY: "secret" },
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

    renderPage();
    await user.type(screen.getByLabelText(/name/i), "test-server");
    await user.type(screen.getByLabelText(/url/i), "https://mcp.test/mcp");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/mcp-servers"));
  });

  it("shows validation error on blur when url is invalid", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText(/url/i), "not-a-url");
    await user.tab();
    await waitFor(() => expect(screen.getByText(/invalid/i)).toBeInTheDocument());
  });

  it("shows error on api failure", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("http://localhost:8000/api/v1/mcp-servers", () =>
        envelopeErr("VALIDATION_ERROR", "Invalid request", 422)
      )
    );

    renderPage();
    await user.type(screen.getByLabelText(/name/i), "test-server");
    await user.type(screen.getByLabelText(/url/i), "https://mcp.test/mcp");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Invalid request",
        variant: "error",
      })
    );
  });

  it("refuses the form for a viewer without the developer role", () => {
    render(<NewMcpServerPage />, { preloadedState: REQUESTER });

    expect(screen.getByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
  });
});
