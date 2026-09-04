import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, within } from "@/test/test-utils";
import ApprovalDetailPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

beforeEach(() => {
  vi.mocked(useParams).mockReturnValue({ approvalId: "appr-1" });
});

describe("ApprovalDetailPage", () => {
  it("titles the page and ends the breadcrumb trail with the approval's title", async () => {
    render(<ApprovalDetailPage />);
    expect(
      await screen.findByRole("heading", { name: "Deploy to production" })
    ).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByText("Deploy to production")).toHaveAttribute("aria-current", "page");
  });

  it("shows the status in its own status card", async () => {
    render(<ApprovalDetailPage />);
    await screen.findByRole("heading", { name: "Deploy to production" });
    const card = screen.getByRole("region", { name: "Approval status" });
    expect(within(card).getByText("approved")).toBeInTheDocument();
  });

  it("shows the status, comment, and resolved approver name", async () => {
    render(<ApprovalDetailPage />);
    await screen.findByRole("heading", { name: "Deploy to production" });
    expect(screen.getByText("approved")).toBeInTheDocument();
    expect(screen.getByText("Looks good to me")).toBeInTheDocument();
    // The same user is both the approver and the decider, so two links carry
    // the name: the Approver row and the Decided By row.
    const links = await screen.findAllByRole("link", { name: "Alice Smith" });
    expect(links).toHaveLength(2);
    for (const link of links) {
      expect(link).toHaveAttribute("href", "/admin/users/user-1");
    }
  });

  it("links the Workflow Execution field to its resolved name", async () => {
    render(<ApprovalDetailPage />);
    // "My Workflow" is WORKFLOW_EXECUTION_1's name in the default MSW fixtures.
    const link = await screen.findByRole("link", { name: "My Workflow" });
    expect(link).toHaveAttribute("href", "/admin/workflow-executions/execution-1");
  });

  it("shows an empty placeholder for Takes Effect From when the approval names none", async () => {
    render(<ApprovalDetailPage />);
    await screen.findByRole("heading", { name: "Deploy to production" });
    // APPROVAL_1's workflowTaskId is null in the default MSW fixtures.
    const dt = screen.getByText("Takes Effect From");
    expect(dt.nextElementSibling).toHaveTextContent("—");
  });

  it("links the Takes Effect From field to its resolved title", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/approvals/appr-1", () =>
        envelope({
          id: "appr-1",
          tenantId: "tenant-1",
          workflowExecutionId: "execution-1",
          workflowTaskId: "task-1",
          title: "Deploy to production",
          description: "The agent wants to deploy. Approve?",
          status: "approved",
          response: "Looks good to me",
          approver: "user-1",
          approverGroupId: null,
          decidedBy: "user-1",
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "owner",
          updatedBy: "owner",
        })
      )
    );

    render(<ApprovalDetailPage />);
    // "Step 1" is WORKFLOW_TASK_1's title in the default MSW fixtures. The
    // certificate panel links the same task, so more than one link carries it.
    const links = await screen.findAllByRole("link", { name: "Step 1" });
    for (const link of links) {
      expect(link).toHaveAttribute(
        "href",
        "/admin/workflow-executions/execution-1/workflow-tasks/task-1"
      );
    }
  });

  it("lists a certificate row per task the approval covers", async () => {
    render(<ApprovalDetailPage />);
    await screen.findByRole("heading", { name: "Authorized MCP tools" });

    // TOOL_CERTIFICATE_1 names task-1, whose title resolves through the run's
    // task list rather than a lookup per certificate.
    expect(await screen.findByText("Takes Effect From")).toBeInTheDocument();
    expect(screen.getByText("Task")).toBeInTheDocument();
    expect(screen.getByText("Certificate Status")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Step 1" })).toHaveAttribute(
      "href",
      "/admin/workflow-executions/execution-1/workflow-tasks/task-1"
    );
  });

  it("says so when a granted approval has issued no certificate yet", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/approvals/appr-1/certificates", () => envelope([]))
    );

    render(<ApprovalDetailPage />);

    expect(
      await screen.findByText("No certificate has been issued under this approval yet.")
    ).toBeInTheDocument();
  });

  it("shows no certificate panel while the approval is undecided", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/approvals/appr-1", () =>
        envelope({
          id: "appr-1",
          tenantId: "tenant-1",
          workflowExecutionId: "execution-1",
          workflowTaskId: "task-1",
          title: "Deploy to production",
          description: null,
          status: "pending",
          response: null,
          approver: "user-1",
          approverGroupId: null,
          decidedBy: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "owner",
          updatedBy: "owner",
        })
      )
    );

    render(<ApprovalDetailPage />);
    await screen.findByRole("heading", { name: "Deploy to production" });

    expect(screen.queryByRole("heading", { name: "Authorized MCP tools" })).not.toBeInTheDocument();
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

    render(<ApprovalDetailPage />);
    await screen.findByRole("heading", { name: "Deploy to production" });
    await user.click(screen.getByRole("button", { name: "Open workflow session" }));
    expect(pushMock).toHaveBeenCalledWith("/workflow-executions/execution-1/session");
  });

  it("offers no delete or resolve controls", async () => {
    render(<ApprovalDetailPage />);
    await screen.findByRole("heading", { name: "Deploy to production" });
    expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /reject/i })).not.toBeInTheDocument();
  });

  it("cancels back to the approvals list", async () => {
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

    render(<ApprovalDetailPage />);
    await screen.findByRole("heading", { name: "Deploy to production" });
    await user.click(screen.getByRole("button", { name: /^back$/i }));
    expect(pushMock).toHaveBeenCalledWith("/admin/approvals");
  });

  it("shows the access-denied state and no toast on a FORBIDDEN load failure", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/approvals/:approvalId", () =>
        envelopeErr("FORBIDDEN", "Requires developer", 403)
      )
    );
    const beforeCount = store.getState().toast.items.length;

    render(<ApprovalDetailPage />);

    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(store.getState().toast.items.length).toBe(beforeCount);
  });

  it("links a group-addressed approval to the group rather than a user", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/approvals/appr-1", () =>
        envelope({
          id: "appr-1",
          tenantId: "tenant-1",
          workflowExecutionId: "execution-1",
          workflowTaskId: null,
          title: "Restart the cluster",
          description: null,
          status: "pending",
          response: null,
          approver: null,
          approverGroupId: "group-1",
          decidedBy: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "owner",
          updatedBy: "owner",
        })
      )
    );

    render(<ApprovalDetailPage />);
    await screen.findByRole("heading", { name: "Restart the cluster" });

    // "Developers" is USER_GROUP_1's name in the default MSW fixtures.
    expect(await screen.findByRole("link", { name: "Developers" })).toHaveAttribute(
      "href",
      "/admin/user-groups/group-1"
    );
  });
});
