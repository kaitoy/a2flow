import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { store as appStore } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import ApprovalsPage from "./page";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: React.ReactNode;
  } & React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe("ApprovalsPage", () => {
  it("renders an approval row after load", async () => {
    render(<ApprovalsPage />);
    await waitFor(() => expect(screen.getByText("Deploy to production")).toBeInTheDocument());
  });

  it("links the Title cell to the approval's detail page", async () => {
    render(<ApprovalsPage />);
    const link = await screen.findByRole("link", { name: "Deploy to production" });
    expect(link).toHaveAttribute("href", "/admin/approvals/appr-1");
  });

  it("resolves every row's approver, creator, and updater in a single request", async () => {
    const requests: string[][] = [];
    server.use(
      http.get("http://localhost:8000/api/v1/approvals", () =>
        envelope(
          ["ann", "bob", "cal"].map((approver, i) => ({
            id: `appr-${i}`,
            tenantId: "tenant-1",
            workflowExecutionId: "execution-1",
            workflowTaskId: null,
            title: `Approve ${i}`,
            description: null,
            status: "pending",
            response: null,
            approver,
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "owner",
            updatedBy: "owner",
          }))
        )
      ),
      http.post("http://localhost:8000/api/v1/users/resolve-names", async ({ request }) => {
        const { ids } = (await request.json()) as { ids: string[] };
        requests.push(ids);
        return envelope(ids.map((id) => ({ id, displayName: id.toUpperCase() })));
      })
    );

    render(<ApprovalsPage />);
    await waitFor(() => screen.getByText("Approve 0"));

    // "owner" is every row's createdBy/updatedBy, deduplicated with the approvers.
    await waitFor(() => expect(requests).toEqual([["ann", "owner", "bob", "cal"]]));
  });

  it("shows the Description column by default", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/approvals", () =>
        envelope([
          {
            id: "appr-1",
            tenantId: "tenant-1",
            workflowExecutionId: "execution-1",
            workflowTaskId: null,
            title: "Deploy to production",
            description: "Ship the release build to prod",
            status: "approved",
            response: "Looks good to me",
            approver: "user-1",
            decidedAt: "2026-01-02T00:00:00Z",
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "owner",
            updatedBy: "owner",
          },
        ])
      )
    );
    render(<ApprovalsPage />);
    await waitFor(() =>
      expect(screen.getByText("Ship the release build to prod")).toBeInTheDocument()
    );
  });

  it("links the Workflow Execution cell to the execution's detail page, resolving its name", async () => {
    render(<ApprovalsPage />);
    const link = await screen.findByRole("link", { name: "My Workflow" });
    expect(link).toHaveAttribute("href", "/admin/workflow-executions/execution-1");
  });

  it("links the Open Workflow Session action to the chat page", async () => {
    render(<ApprovalsPage />);
    await waitFor(() => screen.getByText("Deploy to production"));
    const link = screen.getByRole("link", { name: "Open workflow session" });
    expect(link).toHaveAttribute("href", "/workflow-executions/execution-1/session");
  });

  it("shows the empty-state message when no approvals exist", async () => {
    server.use(http.get("http://localhost:8000/api/v1/approvals", () => envelope([])));
    render(<ApprovalsPage />);
    await waitFor(() => expect(screen.getByText("No approval requests yet.")).toBeInTheDocument());
  });

  it("shows an error toast when load fails", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/approvals", () =>
        envelopeErr("INTERNAL_ERROR", "Internal server error", 500)
      )
    );
    render(<ApprovalsPage />);
    await waitFor(() =>
      expect(appStore.getState().toast.items.at(-1)).toMatchObject({
        message: "Internal server error",
        variant: "error",
      })
    );
  });

  it("shows the approver group's name, linked to the group, for a group-addressed row", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("http://localhost:8000/api/v1/approvals", () =>
        envelope([
          {
            id: "appr-g",
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
          },
        ])
      )
    );

    render(<ApprovalsPage />);
    await waitFor(() => screen.getByText("Restart the cluster"));

    await user.click(screen.getByRole("button", { name: "Columns" }));
    await user.click(await screen.findByRole("checkbox", { name: "Approver" }));

    // "Developers" is USER_GROUP_1's name in the default MSW fixtures.
    const link = await screen.findByRole("link", { name: "Developers" });
    expect(link).toHaveAttribute("href", "/admin/user-groups/group-1");
  });
});
