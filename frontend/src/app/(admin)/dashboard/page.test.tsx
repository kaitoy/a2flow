import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DASHBOARD_LOOK_STORAGE_KEY } from "@/hooks/useDashboardLook";
import type { MetricsSummary, User } from "@/lib/api";
import type { Role } from "@/lib/roles";
import { type RootState, store } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, within } from "@/test/test-utils";
import DashboardPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const BASE = "http://localhost:8000/api/v1";

const SUMMARY: MetricsSummary = {
  approvalsPending: 7,
  approvalsPendingOverThreshold: 2,
  approvalPendingAgeSecondsMax: 3 * 86_400,
  approvalsDecidedToday: { approved: 3, rejected: 1, returned: 0 },
  executionsActive: 12,
  executionsFinishedToday: { completed: 9, failed: 1 },
  executionsFailedRecently: 3,
  tasksFailedRecently: { timeout: 2, api_error: 1 },
  executionsStartedRecently: { Invoices: 4, Onboarding: 1 },
  leadTimeSecondsAvgRecently: { Invoices: 3_600 },
  emailQueueDepth: { pending: 3, sending: 1, sent: 40, failed: 0 },
  emailQueueOldestPendingAgeSeconds: 240,
};

/** Build a preloaded auth slice for a signed-in user of a tenant holding the given roles. */
function authState(roles: Role[], tenantId: string | null = "t1"): Partial<RootState> {
  return {
    auth: {
      user: { id: "u1", roles, tenantId } as User,
      status: "authenticated",
      selectedTenantId: null,
      impersonatedUserId: null,
      impersonatedBy: null,
    },
  };
}

let failuresRequested = false;

beforeEach(() => {
  failuresRequested = false;
  window.localStorage.removeItem(DASHBOARD_LOOK_STORAGE_KEY);
  server.use(
    http.get(`${BASE}/metrics/summary`, () => envelope(SUMMARY)),
    http.get(`${BASE}/workflow-executions/by-workflow`, () =>
      envelope([
        {
          workflowId: "w1",
          workflowName: "Invoices",
          total: 10,
          running: 2,
          completed: 7,
          failed: 1,
          avgLeadTimeSeconds: 5_400,
        },
      ])
    ),
    http.get(`${BASE}/workflow-executions/lead-time-trend`, () =>
      envelope([
        { bucketStart: "2026-10-01T12:00:00Z", count: 1, avgLeadTimeSeconds: 3_600 },
        { bucketStart: "2026-10-02T12:00:00Z", count: 3, avgLeadTimeSeconds: 7_200 },
      ])
    ),
    http.get(`${BASE}/workflow-executions/failures`, () => {
      failuresRequested = true;
      return envelope([
        {
          executionId: "e1",
          name: "Invoice run 42",
          workflowId: "w1",
          workflowName: "Invoices",
          status: "failed",
          finishedAt: null,
          failedTasks: [
            {
              taskId: "t1",
              title: "Fetch invoice",
              errorKind: "timeout",
              errorMessage: null,
              failedAt: new Date().toISOString(),
            },
          ],
        },
      ]);
    }),
    http.get(`${BASE}/approvals/by-approver`, () =>
      envelope([
        {
          groupId: "g1",
          groupKind: "group",
          groupLabel: "Finance",
          pending: 2,
          overThreshold: 1,
          avgWaitSeconds: 40_000,
          maxWaitSeconds: 90_000,
        },
      ])
    )
  );
});

describe("DashboardPage", () => {
  it("shows the KPI tiles, the charts, and the live indicator once the first reading lands", async () => {
    render(<DashboardPage />, { preloadedState: authState(["admin"]) });

    const active = await screen.findByRole("region", { name: "Active runs" });
    expect(within(active).getByText("12")).toBeInTheDocument();
    expect(active).toHaveTextContent("5 started in 24h");

    expect(screen.getByRole("region", { name: "Pending approvals" })).toHaveTextContent(
      "4 decided today"
    );
    expect(screen.getByRole("region", { name: "Finished today" })).toHaveTextContent(
      "90% completed"
    );
    expect(screen.getByRole("region", { name: "Failed runs, last 24h" })).toHaveTextContent(
      "3 failed tasks"
    );
    // Pending plus sending; nothing failed, so the detail is the oldest wait.
    const email = screen.getByRole("region", { name: "Email queue" });
    expect(within(email).getByText("4")).toBeInTheDocument();
    expect(email).toHaveTextContent("Oldest waiting 4m");

    // The header figure is the run-weighted average: (1h * 1 + 2h * 3) / 4.
    expect(await screen.findByRole("region", { name: "Lead time" })).toHaveTextContent("1.8h");
    expect(await screen.findByText("Finance")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Runs by workflow" })).toHaveTextContent("Invoices");
    expect(screen.getByRole("region", { name: "Failure causes" })).toHaveTextContent("timeout");
    expect(screen.getByRole("status")).toHaveTextContent("Live");
  });

  it("shows an admin the runs needing triage", async () => {
    render(<DashboardPage />, { preloadedState: authState(["admin"]) });
    const ticker = await screen.findByRole("region", { name: "Needs attention" });
    expect(within(ticker).getByRole("link", { name: /Invoice run 42/ })).toHaveAttribute(
      "href",
      "/workflow-executions/e1"
    );
  });

  it("neither requests nor shows the failure list for a non-admin", async () => {
    render(<DashboardPage />, { preloadedState: authState(["developer"]) });
    await screen.findByRole("region", { name: "Active runs" });
    expect(screen.queryByRole("region", { name: "Needs attention" })).not.toBeInTheDocument();
    expect(failuresRequested).toBe(false);
  });

  it("reports a lost connection without a toast when the metrics cannot be read", async () => {
    server.use(
      http.get(`${BASE}/metrics/summary`, () => envelopeErr("INTERNAL_ERROR", "boom", 500)),
      http.get(`${BASE}/workflow-executions/by-workflow`, () => HttpResponse.error())
    );
    render(<DashboardPage />, { preloadedState: authState(["admin"]) });

    expect(await screen.findByRole("heading", { name: "Connection lost" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Active runs" })).not.toBeInTheDocument();
    expect(store.getState().toast.items).toHaveLength(0);
  });

  it("opens in the standard look and switches to Mission Control and back", async () => {
    const user = userEvent.setup();
    const { container } = render(<DashboardPage />, { preloadedState: authState(["admin"]) });
    const root = container.firstElementChild;
    expect(root).not.toHaveClass("console");

    await user.click(screen.getByRole("button", { name: "Switch to Mission Control view" }));
    expect(root).toHaveClass("console");
    expect(root).toHaveAttribute("data-theme", "dark");
    expect(window.localStorage.getItem(DASHBOARD_LOOK_STORAGE_KEY)).toBe("console");

    await user.click(screen.getByRole("button", { name: "Switch to standard view" }));
    expect(root).not.toHaveClass("console");
    expect(window.localStorage.getItem(DASHBOARD_LOOK_STORAGE_KEY)).toBe("standard");
  });

  it("opens in the look chosen on an earlier visit", () => {
    window.localStorage.setItem(DASHBOARD_LOOK_STORAGE_KEY, "console");
    const { container } = render(<DashboardPage />, { preloadedState: authState(["admin"]) });
    expect(container.firstElementChild).toHaveClass("console");
  });

  it("asks a platform-scoped user to pick a tenant instead of polling", () => {
    render(<DashboardPage />, { preloadedState: authState(["super_admin"], null) });
    expect(screen.getByText("Select a tenant to see its dashboard.")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
