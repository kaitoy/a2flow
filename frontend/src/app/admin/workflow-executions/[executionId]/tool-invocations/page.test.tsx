import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { DEVELOPER } from "@/test/auth-state";
import { envelope } from "@/test/msw/envelope";
import { MCP_TOOL_INVOCATION_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import ToolInvocationsPage from "./page";

function setup() {
  vi.mocked(useParams).mockReturnValue({ executionId: "execution-1" });
}

function renderPage() {
  return render(<ToolInvocationsPage />, { preloadedState: DEVELOPER });
}

/** Turn on a column hidden by default, through the page's own column picker. */
async function showColumn(user: ReturnType<typeof userEvent.setup>, label: string) {
  await user.click(screen.getByRole("button", { name: "Columns" }));
  await user.click(await screen.findByRole("checkbox", { name: label }));
}

describe("ToolInvocationsPage", () => {
  it("renders the recorded tool call and its decision", async () => {
    setup();
    renderPage();
    await waitFor(() => expect(screen.getByText("search")).toBeInTheDocument());
    expect(screen.getByText("allowed")).toBeInTheDocument();
  });

  it("names the MCP server the call went to", async () => {
    setup();
    renderPage();
    await waitFor(() => expect(screen.getByText("my-mcp-server")).toBeInTheDocument());
  });

  it("hides the arguments digest until the column is shown", async () => {
    const user = userEvent.setup();
    setup();
    renderPage();
    await waitFor(() => screen.getByText("search"));

    expect(screen.queryByText(/^a{16}…$/)).not.toBeInTheDocument();
    await showColumn(user, "Arguments Digest");
    expect(screen.getByText(`${"a".repeat(16)}…`)).toBeInTheDocument();
  });

  it("links back to the run in the breadcrumb trail", async () => {
    setup();
    renderPage();
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    await waitFor(() => expect(within(nav).getByText("Tool Invocations")).toBeInTheDocument());
  });

  it("says nothing was recorded when the run made no proxied calls", async () => {
    setup();
    server.use(
      http.get(
        "http://localhost:8000/api/v1/workflow-executions/:executionId/tool-invocations",
        () => envelope([])
      )
    );
    renderPage();
    expect(
      await screen.findByText("No MCP tool calls were recorded for this run.")
    ).toBeInTheDocument();
  });

  it("filters by decision through the column menu", async () => {
    const user = userEvent.setup();
    setup();
    let query = "";
    server.use(
      http.get(
        "http://localhost:8000/api/v1/workflow-executions/:executionId/tool-invocations",
        ({ request }) => {
          query = new URL(request.url).searchParams.toString();
          return envelope([MCP_TOOL_INVOCATION_1]);
        }
      )
    );
    renderPage();
    await waitFor(() => screen.getByText("search"));

    await user.click(screen.getByRole("button", { name: /decision/i }));
    await user.click(await screen.findByRole("combobox", { name: /filter/i }));
    await user.click(await screen.findByRole("option", { name: "Denied" }));

    await waitFor(() => expect(query).toContain("decision%3Aeq%3Adenied"));
  });
});
