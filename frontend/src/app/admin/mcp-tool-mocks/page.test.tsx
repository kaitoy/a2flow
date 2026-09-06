import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { DEVELOPER, REQUESTER } from "@/test/auth-state";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import McpToolMocksPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

/** Render the list as a developer — the role every tool-mock write requires. */
function renderPage() {
  return render(<McpToolMocksPage />, { preloadedState: DEVELOPER });
}

/** Turn on a column hidden by default, through the page's own column picker. */
async function showColumn(user: ReturnType<typeof userEvent.setup>, label: string) {
  await user.click(screen.getByRole("button", { name: "Columns" }));
  await user.click(await screen.findByRole("checkbox", { name: label }));
}

describe("McpToolMocksPage", () => {
  it("shows loading state initially", () => {
    renderPage();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders each mock's name and tool", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("search returns nothing")).toBeInTheDocument());
    expect(screen.getByText("search")).toBeInTheDocument();
    expect(screen.getByText("request_approval")).toBeInTheDocument();
  });

  it("names the MCP server a mock targets", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("my-mcp-server")).toBeInTheDocument());
  });

  it("carries the shared Tags column", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("search returns nothing")).toBeInTheDocument());
    expect(screen.getByRole("columnheader", { name: "Tags" })).toBeInTheDocument();
  });

  it("marks a mock with no server as built-in", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("Built-in")).toBeInTheDocument());
  });

  it("hides the Responses column by default", async () => {
    renderPage();
    await waitFor(() => screen.getByText("search returns nothing"));
    expect(screen.queryByRole("columnheader", { name: "Responses" })).not.toBeInTheDocument();
  });

  it("shows how many successive responses each mock defines once the column is shown", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText("search returns nothing"));

    await showColumn(user, "Responses");

    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("offers the Add button to a developer", async () => {
    renderPage();
    await waitFor(() => screen.getByText("search returns nothing"));
    expect(screen.getByRole("link", { name: "+ Add tool mock" })).toBeInTheDocument();
  });

  it("hides Add and Delete from a viewer without the developer role", async () => {
    render(<McpToolMocksPage />, { preloadedState: REQUESTER });
    await waitFor(() => screen.getByText("search returns nothing"));
    expect(screen.queryByRole("link", { name: "+ Add tool mock" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
  });

  it("deletes a mock after confirming", async () => {
    const user = userEvent.setup();
    let deleted = false;
    server.use(
      http.delete("http://localhost:8000/api/v1/mcp-tool-mocks/:mockId", () => {
        deleted = true;
        return envelope(null);
      })
    );
    renderPage();
    await waitFor(() => screen.getByText("search returns nothing"));

    await user.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(deleted).toBe(true));
  });

  it("says so when a run's own copy is unaffected by the delete", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText("search returns nothing"));

    await user.click(screen.getAllByRole("button", { name: "Delete" })[0]);

    expect(await screen.findByText(/Runs already started keep their own copy/)).toBeVisible();
  });
});
