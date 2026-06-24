import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import * as api from "@/lib/api";
import type { RootState } from "@/store";
import { render, screen, waitFor } from "@/test/test-utils";
import { ApprovalControls } from "./ApprovalControls";

vi.mock("@/lib/api", () => ({
  getApproval: vi.fn(),
  resolveApproval: vi.fn(),
}));

/** Build a preloaded auth slice for the signed-in user with the given id. */
function authState(userId: string): Partial<RootState> {
  return { auth: { user: { id: userId } as User, status: "authenticated" } };
}

beforeEach(() => {
  // By default the current user "u1" is the designated approver.
  vi.mocked(api.getApproval).mockResolvedValue({ status: "pending", approver: "u1" } as never);
  vi.mocked(api.resolveApproval).mockResolvedValue({ status: "approved" } as never);
});

describe("ApprovalControls", () => {
  it("renders the title and description", async () => {
    render(
      <ApprovalControls approvalId="a1" title="Deploy?" description="To prod" toolCallId="tc1" />,
      { preloadedState: authState("u1") }
    );
    expect(screen.getByText("Deploy?")).toBeInTheDocument();
    expect(screen.getByText("To prod")).toBeInTheDocument();
  });

  it("approves: calls resolveApproval and onResolved with the decision", async () => {
    const onResolved = vi.fn();
    render(
      <ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" onResolved={onResolved} />,
      { preloadedState: authState("u1") }
    );

    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));

    await waitFor(() =>
      expect(api.resolveApproval).toHaveBeenCalledWith("a1", "approved", undefined)
    );
    expect(onResolved).toHaveBeenCalledWith("tc1", "approved");
    await waitFor(() => expect(screen.getByText("Approved")).toBeInTheDocument());
  });

  it("rejects: calls resolveApproval with the rejected decision", async () => {
    const onResolved = vi.fn();
    render(
      <ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" onResolved={onResolved} />,
      { preloadedState: authState("u1") }
    );

    await userEvent.click(await screen.findByRole("button", { name: "Reject" }));

    await waitFor(() =>
      expect(api.resolveApproval).toHaveBeenCalledWith("a1", "rejected", undefined)
    );
    expect(onResolved).toHaveBeenCalledWith("tc1", "rejected");
  });

  it("passes the typed comment to resolveApproval and shows it once resolved", async () => {
    render(<ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" />, {
      preloadedState: authState("u1"),
    });

    await userEvent.type(await screen.findByLabelText("Comment"), "Ship it");
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() =>
      expect(api.resolveApproval).toHaveBeenCalledWith("a1", "approved", "Ship it")
    );
    await waitFor(() => expect(screen.getByText("Ship it")).toBeInTheDocument());
  });

  it("hides the controls and shows a waiting message for a non-approver", async () => {
    vi.mocked(api.getApproval).mockResolvedValue({
      status: "pending",
      approver: "someone-else",
    } as never);
    render(<ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" />, {
      preloadedState: authState("u1"),
    });

    await waitFor(() =>
      expect(screen.getByText("Waiting for the approver's decision.")).toBeInTheDocument()
    );
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
  });

  it("shows the resolved state and prior comment when already decided", async () => {
    vi.mocked(api.getApproval).mockResolvedValue({
      status: "approved",
      response: "Approved earlier",
    } as never);
    render(<ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" />, {
      preloadedState: authState("u1"),
    });
    await waitFor(() => expect(screen.getByText("Approved")).toBeInTheDocument());
    expect(screen.getByText("Approved earlier")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });
});
