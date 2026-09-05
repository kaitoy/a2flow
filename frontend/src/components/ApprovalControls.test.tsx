import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import * as api from "@/lib/api";
import { __resetApprovalCacheForTests } from "@/lib/approvalCache";
import type { Role } from "@/lib/roles";
import type { RootState } from "@/store";
import { render, screen, waitFor } from "@/test/test-utils";
import { ApprovalControls } from "./ApprovalControls";

vi.mock("@/lib/api", () => ({
  getApproval: vi.fn(),
  resolveApproval: vi.fn(),
  getUserNames: vi.fn(),
  isApprovalAlreadyResolvedError: vi.fn(),
}));

/**
 * Build a preloaded auth slice for the signed-in user with the given id, roles,
 * and group memberships. `groupIds` is what decides eligibility for an approval
 * addressed to a group, alongside the `approver` role.
 */
function authState(
  userId: string,
  roles: Role[] = [],
  groupIds: string[] = [],
  groupRoles: Role[] = []
): Partial<RootState> {
  return {
    auth: {
      user: { id: userId, roles, groupIds, groupRoles } as User,
      status: "authenticated",
      selectedTenantId: null,
      impersonatedUserId: null,
      impersonatedBy: null,
    },
  };
}

beforeEach(() => {
  __resetApprovalCacheForTests();
  vi.mocked(api.getApproval).mockClear();
  vi.mocked(api.getUserNames).mockClear();
  vi.mocked(api.getUserNames).mockResolvedValue(new Map());
  vi.mocked(api.isApprovalAlreadyResolvedError).mockReturnValue(false);
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

  it("returns: calls resolveApproval with the returned decision", async () => {
    const onResolved = vi.fn();
    render(
      <ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" onResolved={onResolved} />,
      { preloadedState: authState("u1") }
    );

    await userEvent.click(await screen.findByRole("button", { name: "Return" }));

    await waitFor(() =>
      expect(api.resolveApproval).toHaveBeenCalledWith("a1", "returned", undefined)
    );
    expect(onResolved).toHaveBeenCalledWith("tc1", "returned");
    await waitFor(() => expect(screen.getByText("Returned for rework")).toBeInTheDocument());
  });

  it("shows the returned state for an approval already sent back", async () => {
    vi.mocked(api.getApproval).mockResolvedValue({
      status: "returned",
      approver: "u1",
      response: "Please add the cost breakdown",
    } as never);

    render(<ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" />, {
      preloadedState: authState("u1"),
    });

    await waitFor(() => expect(screen.getByText("Returned for rework")).toBeInTheDocument());
    expect(screen.getByText("Please add the cost breakdown")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Return" })).not.toBeInTheDocument();
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
    expect(screen.queryByRole("button", { name: "Return" })).not.toBeInTheDocument();
  });

  it("hides the controls from a super admin who is not the designated approver", async () => {
    vi.mocked(api.getApproval).mockResolvedValue({
      status: "pending",
      approver: "someone-else",
    } as never);
    render(<ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" />, {
      preloadedState: authState("u1", ["super_admin"]),
    });

    await waitFor(() =>
      expect(screen.getByText("Waiting for the approver's decision.")).toBeInTheDocument()
    );
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Return" })).not.toBeInTheDocument();
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

  it("dedupes concurrent fetches for the same approvalId", async () => {
    render(<ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" />, {
      preloadedState: authState("u1"),
    });
    render(<ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc2" />, {
      preloadedState: authState("u1"),
    });

    await waitFor(() =>
      expect(screen.getAllByText("Waiting for the approver's decision.").length).toBeGreaterThan(0)
    );
    expect(api.getApproval).toHaveBeenCalledTimes(1);
  });

  it("does not refetch an approval that already resolved", async () => {
    vi.mocked(api.getApproval).mockResolvedValue({
      status: "approved",
      response: "Approved earlier",
    } as never);
    const { unmount } = render(
      <ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" />,
      { preloadedState: authState("u1") }
    );
    await waitFor(() => expect(screen.getByText("Approved")).toBeInTheDocument());
    unmount();

    render(<ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" />, {
      preloadedState: authState("u1"),
    });
    await waitFor(() => expect(screen.getByText("Approved")).toBeInTheDocument());
    expect(api.getApproval).toHaveBeenCalledTimes(1);
  });

  describe("addressed to a user group", () => {
    /** An approval whose destination is the group `g1` rather than one user. */
    function groupApproval(overrides: Record<string, unknown> = {}) {
      return { status: "pending", approver: null, approverGroupId: "g1", ...overrides };
    }

    it("shows the controls to a group member holding the approver role", async () => {
      vi.mocked(api.getApproval).mockResolvedValue(groupApproval() as never);
      render(<ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" />, {
        preloadedState: authState("u2", ["approver"] as Role[], ["g1"]),
      });
      expect(await screen.findByRole("button", { name: "Approve" })).toBeInTheDocument();
    });

    it("shows the controls when the approver role is inherited from a group", async () => {
      vi.mocked(api.getApproval).mockResolvedValue(groupApproval() as never);
      render(<ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" />, {
        preloadedState: authState("u2", [], ["g1"], ["approver"] as Role[]),
      });
      expect(await screen.findByRole("button", { name: "Approve" })).toBeInTheDocument();
    });

    it("hides the controls from a group member without the approver role", async () => {
      vi.mocked(api.getApproval).mockResolvedValue(groupApproval() as never);
      render(<ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" />, {
        preloadedState: authState("u2", [] as Role[], ["g1"]),
      });
      expect(
        await screen.findByText("Waiting for a decision from the approver group.")
      ).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    });

    it("hides the controls from an approver who is not in the group", async () => {
      vi.mocked(api.getApproval).mockResolvedValue(groupApproval() as never);
      render(<ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" />, {
        preloadedState: authState("u2", ["approver"] as Role[], ["other-group"]),
      });
      expect(
        await screen.findByText("Waiting for a decision from the approver group.")
      ).toBeInTheDocument();
    });

    it("hides the controls from a super admin outside the group", async () => {
      // hasRole would let a super admin through; the backend grants no such
      // bypass for resolving an approval, so the component must not either.
      vi.mocked(api.getApproval).mockResolvedValue(groupApproval() as never);
      render(<ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" />, {
        preloadedState: authState("u9", ["super_admin"] as Role[], []),
      });
      expect(
        await screen.findByText("Waiting for a decision from the approver group.")
      ).toBeInTheDocument();
    });

    it("reports the winner when another member decided first", async () => {
      vi.mocked(api.getApproval).mockResolvedValue(groupApproval() as never);
      vi.mocked(api.resolveApproval).mockRejectedValue(new Error("409"));
      vi.mocked(api.isApprovalAlreadyResolvedError).mockReturnValue(true);
      const onResolved = vi.fn();
      render(
        <ApprovalControls
          approvalId="a1"
          title="Deploy?"
          toolCallId="tc1"
          onResolved={onResolved}
        />,
        { preloadedState: authState("u2", ["approver"] as Role[], ["g1"]) }
      );

      await userEvent.click(await screen.findByRole("button", { name: "Approve" }));

      expect(
        await screen.findByText("Another approver already decided this request.")
      ).toBeInTheDocument();
      // The run was already resumed by the member who won the race.
      expect(onResolved).not.toHaveBeenCalled();
    });

    it("names who decided once a group approval is resolved", async () => {
      vi.mocked(api.getApproval).mockResolvedValue(
        groupApproval({ status: "approved", decidedBy: "u7" }) as never
      );
      vi.mocked(api.getUserNames).mockResolvedValue(new Map([["u7", "Dana Scully"]]));
      render(<ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" />, {
        preloadedState: authState("u2", ["approver"] as Role[], ["g1"]),
      });
      expect(await screen.findByText("by Dana Scully")).toBeInTheDocument();
    });

    it("does not resolve a decider name for a user-addressed approval", async () => {
      vi.mocked(api.getApproval).mockResolvedValue({
        status: "approved",
        approver: "u1",
        approverGroupId: null,
        decidedBy: "u1",
      } as never);
      render(<ApprovalControls approvalId="a1" title="Deploy?" toolCallId="tc1" />, {
        preloadedState: authState("u1"),
      });
      await screen.findByText("Approved");
      expect(api.getUserNames).not.toHaveBeenCalled();
    });
  });
});

describe("the calls an approval authorizes", () => {
  it("shows the declaration the approver is deciding on", async () => {
    vi.mocked(api.getApproval).mockResolvedValue({
      status: "pending",
      approver: "u1",
      approvedCalls: [
        {
          mcpServerId: "srv-1",
          toolName: "run_instances",
          arguments: { region: { eq: "ap-northeast-1" }, count: { lte: 2 } },
        },
      ],
    } as never);

    render(<ApprovalControls approvalId="a1" toolCallId="t1" />, {
      preloadedState: authState("u1", ["approver"] as Role[]),
    });

    expect(await screen.findByText("This authorizes")).toBeInTheDocument();
    expect(screen.getByText("srv-1: run_instances")).toBeInTheDocument();
    expect(screen.getByText('is "ap-northeast-1"')).toBeInTheDocument();
    expect(screen.getByText("is at most 2")).toBeInTheDocument();
  });

  it("keeps showing it after the decision, as the record of what was approved", async () => {
    vi.mocked(api.getApproval).mockResolvedValue({
      status: "approved",
      approver: "u1",
      approvedCalls: [{ mcpServerId: "srv-1", toolName: "run_instances", arguments: {} }],
    } as never);

    render(<ApprovalControls approvalId="a1" toolCallId="t1" />, {
      preloadedState: authState("u1", ["approver"] as Role[]),
    });

    expect(await screen.findByText("srv-1: run_instances")).toBeInTheDocument();
  });

  it("shows no such section for an approval carrying no declaration", async () => {
    // Approvals predating argument constraints bounded no arguments, and an
    // empty section would imply otherwise.
    vi.mocked(api.getApproval).mockResolvedValue({
      status: "pending",
      approver: "u1",
    } as never);

    render(<ApprovalControls approvalId="a1" toolCallId="t1" />, {
      preloadedState: authState("u1", ["approver"] as Role[]),
    });

    await waitFor(() => expect(api.getApproval).toHaveBeenCalled());
    expect(screen.queryByText("This authorizes")).not.toBeInTheDocument();
  });
});
