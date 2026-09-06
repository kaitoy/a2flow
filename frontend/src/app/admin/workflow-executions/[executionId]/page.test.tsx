import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { ADMIN, REQUESTER } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import WorkflowExecutionDetailPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

beforeEach(() => {
  vi.mocked(useParams).mockReturnValue({ executionId: "execution-1" });
});

/** Render the detail page as an admin — the role deletion requires. */
function renderPage(preloadedState = ADMIN) {
  return render(<WorkflowExecutionDetailPage />, { preloadedState });
}

describe("WorkflowExecutionDetailPage", () => {
  it("titles the page and ends the breadcrumb trail with the workflow's name", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "My Workflow" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByText("My Workflow")).toHaveAttribute("aria-current", "page");
  });

  it("shows the run's own name as plain text, not a link", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "My Workflow" });
    expect(screen.queryByRole("link", { name: "My Workflow" })).not.toBeInTheDocument();
    const nameTerm = screen.getByText("Name", { selector: "dt" });
    expect(nameTerm.parentElement).toHaveTextContent("My Workflow");
  });

  it("resolves the workflow id to its current name in the Workflow field and links to it", async () => {
    renderPage();
    expect(await screen.findByRole("link", { name: "my-workflow" })).toHaveAttribute(
      "href",
      "/admin/workflows/wf-1"
    );
  });

  it("links the Agent Skill field to its detail page", async () => {
    renderPage();
    expect(await screen.findByRole("link", { name: "My Skill" })).toHaveAttribute(
      "href",
      "/admin/agent-skills/skill-1"
    );
  });

  it("resolves and links the Initiator field to the user's edit page", async () => {
    renderPage();
    const link = await screen.findByRole("link", { name: "Alice Smith" });
    expect(link).toHaveAttribute("href", "/admin/users/user");
  });

  it("shows the execution's status", async () => {
    renderPage();
    expect(await screen.findByText("completed")).toBeInTheDocument();
  });

  it("shows the status in its own status card", async () => {
    render(<WorkflowExecutionDetailPage />);
    await screen.findByRole("heading", { name: "My Workflow" });
    const card = screen.getByRole("region", { name: "Workflow execution status" });
    expect(within(card).getByText("completed")).toBeInTheDocument();
    // A published-workflow run carries no Draft marker.
    expect(within(card).queryByText("Draft")).not.toBeInTheDocument();
  });

  it("marks a draft run with a Draft badge in the status card", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflow-executions/:id", () =>
        envelope({
          id: "execution-1",
          tenantId: "tenant-1",
          sessionId: "executed-session-id",
          workflowId: "wf-1",
          name: "My Workflow",
          description: null,
          agentSkillId: "skill-1",
          agentSkillName: "My Skill",
          agentSkillRepoUrl: "https://github.com/example/repo",
          agentSkillRepoPath: "",
          initiatorId: "user",
          status: "completed",
          isDraft: true,
          finishedAt: "2026-01-01T00:05:00Z",
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        })
      )
    );
    render(<WorkflowExecutionDetailPage />);
    await screen.findByRole("heading", { name: "My Workflow" });
    const card = screen.getByRole("region", { name: "Workflow execution status" });
    expect(within(card).getByText("Draft")).toBeInTheDocument();
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
      bfcacheId: "",
    });

    renderPage();
    await screen.findByRole("heading", { name: "My Workflow" });
    await user.click(screen.getByRole("button", { name: "View tasks" }));
    expect(pushMock).toHaveBeenCalledWith("/admin/workflow-executions/execution-1/workflow-tasks");
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
      bfcacheId: "",
    });

    renderPage();
    await screen.findByRole("heading", { name: "My Workflow" });
    await user.click(screen.getByRole("button", { name: "Open workflow session" }));
    expect(pushMock).toHaveBeenCalledWith("/workflow-executions/execution-1/session");
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
      bfcacheId: "",
    });
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/workflow-executions/:id", deleteSpy));

    renderPage();
    await screen.findByRole("heading", { name: "My Workflow" });
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^delete$/i }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalled());
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/workflow-executions"));
  });

  it("hides the Delete button from a non-admin", async () => {
    renderPage(REQUESTER);
    await screen.findByRole("heading", { name: "My Workflow" });
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
  });

  it("shows the access-denied state and no toast on a FORBIDDEN load failure", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflow-executions/:id", () =>
        envelopeErr("FORBIDDEN", "Only the execution initiator or a designated approver", 403)
      )
    );
    const beforeCount = store.getState().toast.items.length;

    renderPage();

    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(store.getState().toast.items.length).toBe(beforeCount);
  });
});
