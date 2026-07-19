import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import { setSelectedTenantId } from "@/store/authSlice";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { NotificationBell } from "./NotificationBell";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

const BASE = "http://localhost:8000";

/** Build a notification envelope row. */
function row(id: string, read: boolean) {
  return {
    id,
    tenantId: "tenant-1",
    userId: "user-1",
    type: "approval_request",
    title: `Notification ${id}`,
    body: null,
    workflowSessionId: "ws-1",
    read,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
  };
}

describe("NotificationBell", () => {
  it("shows an unread badge reflecting the fetched notifications", async () => {
    server.use(
      http.get(`${BASE}/api/v1/notifications`, () =>
        envelope([row("a", false), row("b", true), row("c", false)])
      )
    );
    render(<NotificationBell />);
    await waitFor(() => expect(screen.getByText("2")).toBeInTheDocument());
  });

  it("opens the panel listing notifications when clicked", async () => {
    server.use(http.get(`${BASE}/api/v1/notifications`, () => envelope([row("a", false)])));
    const user = userEvent.setup();
    render(<NotificationBell />);
    await waitFor(() => screen.getByText("1"));

    await user.click(screen.getByRole("button", { name: /notifications/i }));
    await waitFor(() => expect(screen.getByText("Notification a")).toBeInTheDocument());
  });

  it("renders no badge when there are no notifications", async () => {
    server.use(http.get(`${BASE}/api/v1/notifications`, () => envelope([])));
    const user = userEvent.setup();
    render(<NotificationBell />);

    await user.click(screen.getByRole("button", { name: /notifications/i }));
    await waitFor(() => expect(screen.getByText("No notifications")).toBeInTheDocument());
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("does not fetch for a platform-scoped user with no tenant selected", async () => {
    let calls = 0;
    server.use(
      http.get(`${BASE}/api/v1/notifications`, () => {
        calls++;
        return envelope([row("a", false)]);
      })
    );
    render(<NotificationBell />, {
      preloadedState: {
        auth: {
          user: { id: "u1", roles: ["super_admin"], tenantId: null } as User,
          status: "authenticated",
          selectedTenantId: null,
        },
      },
    });
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(calls).toBe(0);
  });

  it("fetches once a platform-scoped user selects a tenant", async () => {
    server.use(http.get(`${BASE}/api/v1/notifications`, () => envelope([row("a", false)])));
    const { store } = render(<NotificationBell />, {
      preloadedState: {
        auth: {
          user: { id: "u1", roles: ["super_admin"], tenantId: null } as User,
          status: "authenticated",
          selectedTenantId: null,
        },
      },
    });
    store.dispatch(setSelectedTenantId("tenant-1"));
    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
  });
});
