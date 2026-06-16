import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import { ApprovalControls } from "./ApprovalControls";

vi.mock("@/lib/api", () => ({
  getApproval: vi.fn(),
  resolveApproval: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(api.getApproval).mockResolvedValue({ status: "pending" } as never);
  vi.mocked(api.resolveApproval).mockResolvedValue({ status: "approved" } as never);
});

describe("ApprovalControls", () => {
  it("renders the title and description", async () => {
    render(
      <ApprovalControls approvalId="a1" title="Deploy?" description="To prod" toolCallId="tc1" />
    );
    expect(screen.getByText("Deploy?")).toBeInTheDocument();
    expect(screen.getByText("To prod")).toBeInTheDocument();
  });

  it("approves: calls resolveApproval and onResolved with the decision", async () => {
    const onResolved = vi.fn();
    render(
      <ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" onResolved={onResolved} />
    );

    await userEvent.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => expect(api.resolveApproval).toHaveBeenCalledWith("a1", "approved"));
    expect(onResolved).toHaveBeenCalledWith("tc1", "approved");
    await waitFor(() => expect(screen.getByText("Approved")).toBeInTheDocument());
  });

  it("rejects: calls resolveApproval with the rejected decision", async () => {
    const onResolved = vi.fn();
    render(
      <ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" onResolved={onResolved} />
    );

    await userEvent.click(screen.getByRole("button", { name: "Reject" }));

    await waitFor(() => expect(api.resolveApproval).toHaveBeenCalledWith("a1", "rejected"));
    expect(onResolved).toHaveBeenCalledWith("tc1", "rejected");
  });

  it("shows the resolved state when the approval is already decided", async () => {
    vi.mocked(api.getApproval).mockResolvedValue({ status: "approved" } as never);
    render(<ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" />);
    await waitFor(() => expect(screen.getByText("Approved")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });
});
