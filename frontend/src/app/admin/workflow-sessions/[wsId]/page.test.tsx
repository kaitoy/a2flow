import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import WorkflowSessionDetailPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

beforeEach(() => {
  vi.mocked(useParams).mockReturnValue({ wsId: "ws-1" });
});

describe("WorkflowSessionDetailPage", () => {
  it("titles the page and ends the breadcrumb trail with the workflow's name", async () => {
    render(<WorkflowSessionDetailPage />);
    expect(await screen.findByRole("heading", { name: "My Workflow" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByText("My Workflow")).toHaveAttribute("aria-current", "page");
  });

  it("links the Workflow field to its detail page", async () => {
    render(<WorkflowSessionDetailPage />);
    await waitFor(() =>
      expect(screen.getAllByRole("link", { name: "My Workflow" })[0]).toHaveAttribute(
        "href",
        "/admin/workflows/wf-1"
      )
    );
  });

  it("links the Agent Skill field to its detail page", async () => {
    render(<WorkflowSessionDetailPage />);
    expect(await screen.findByRole("link", { name: "My Skill" })).toHaveAttribute(
      "href",
      "/admin/agent-skills/skill-1"
    );
  });

  it("resolves and links the Initiator field to the user's edit page", async () => {
    render(<WorkflowSessionDetailPage />);
    const link = await screen.findByRole("link", { name: "Alice Smith" });
    expect(link).toHaveAttribute("href", "/admin/users/user");
  });

  it("shows the session's own identifier", async () => {
    render(<WorkflowSessionDetailPage />);
    expect(await screen.findByText("executed-session-id")).toBeInTheDocument();
  });

  it("navigates to the task list from the header action", async () => {
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

    render(<WorkflowSessionDetailPage />);
    await screen.findByRole("heading", { name: "My Workflow" });
    await user.click(screen.getByRole("button", { name: "View tasks" }));
    expect(pushMock).toHaveBeenCalledWith("/admin/workflow-sessions/ws-1/workflow-tasks");
  });

  it("navigates to the chat page from the header action", async () => {
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

    render(<WorkflowSessionDetailPage />);
    await screen.findByRole("heading", { name: "My Workflow" });
    await user.click(screen.getByRole("button", { name: "Open workflow session" }));
    expect(pushMock).toHaveBeenCalledWith("/workflow-sessions/ws-1");
  });

  it("deletes the session after confirmation and returns to the list", async () => {
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
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/workflow-sessions/:id", deleteSpy));

    render(<WorkflowSessionDetailPage />);
    await screen.findByRole("heading", { name: "My Workflow" });
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^delete$/i }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalled());
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/workflow-sessions"));
  });
});
