import userEvent from "@testing-library/user-event";
import { useParams, useRouter } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DEVELOPER, REQUESTER } from "@/test/auth-state";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import WorkflowVersionsPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

const push = vi.fn();

beforeEach(() => {
  push.mockReset();
  vi.mocked(useParams).mockReturnValue({ workflowId: "wf-1" });
  vi.mocked(useRouter).mockReturnValue({
    push,
    replace: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
    refresh: vi.fn(),
    forward: vi.fn(),
  } as unknown as ReturnType<typeof useRouter>);
});

describe("WorkflowVersionsPage", () => {
  it("lists every published version newest first", async () => {
    render(<WorkflowVersionsPage />);
    expect(await screen.findByText("v2")).toBeInTheDocument();
    const rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("v2")).toBeInTheDocument();
    expect(within(rows[1]).getByText("first-name")).toBeInTheDocument();
  });

  it("names the parent workflow in the breadcrumb trail", async () => {
    render(<WorkflowVersionsPage />);
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(await within(nav).findByRole("link", { name: "my-workflow" })).toHaveAttribute(
      "href",
      "/workflows/wf-1"
    );
  });

  it("hides Restore from a non-developer", async () => {
    render(<WorkflowVersionsPage />, { preloadedState: REQUESTER });
    await screen.findByText("v2");
    expect(screen.queryByRole("button", { name: "Restore" })).not.toBeInTheDocument();
  });

  it("restores the chosen version after confirmation and returns to the workflow", async () => {
    const requested: string[] = [];
    server.events.on("request:start", ({ request }) => {
      if (request.method === "POST") requested.push(new URL(request.url).pathname);
    });
    const user = userEvent.setup();
    render(<WorkflowVersionsPage />, { preloadedState: DEVELOPER });
    await screen.findByText("v1");

    const rows = screen.getAllByRole("row").slice(1);
    await user.click(within(rows[1]).getByRole("button", { name: "Restore" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/version 1/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Restore" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/workflows/wf-1"));
    expect(requested).toContain("/api/v1/workflows/wf-1/versions/1/restore");
  });
});
