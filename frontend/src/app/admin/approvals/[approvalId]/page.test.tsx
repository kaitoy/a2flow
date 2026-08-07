import userEvent from "@testing-library/user-event";
import { useParams, useRouter } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";
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

  it("shows the status, comment, and resolved approver name", async () => {
    render(<ApprovalDetailPage />);
    await screen.findByRole("heading", { name: "Deploy to production" });
    expect(screen.getByText("approved")).toBeInTheDocument();
    expect(screen.getByText("Looks good to me")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Alice Smith" })).toHaveAttribute(
      "href",
      "/admin/users/user-1"
    );
  });

  it("links to the workflow execution", async () => {
    render(<ApprovalDetailPage />);
    const link = await screen.findByRole("link", { name: "Open session" });
    expect(link).toHaveAttribute("href", "/admin/workflow-executions/execution-1");
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
});
