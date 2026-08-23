import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import { setMe, setSelectedTenantId } from "@/store/authSlice";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { NotificationBell } from "./NotificationBell";

/** Build a User fixture with overridable fields. */
function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: "user-1",
    username: "user-1",
    firstName: "Test",
    lastName: "User",
    email: "user-1@example.com",
    enabled: true,
    emailVerified: false,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
    ...overrides,
  };
}

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
    workflowExecutionId: "execution-1",
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
    await waitFor(() => expect(screen.getByText("No unread notifications")).toBeInTheDocument());
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("polls for unread notifications only", async () => {
    let requested: URL | null = null;
    server.use(
      http.get(`${BASE}/api/v1/notifications`, ({ request }) => {
        requested = new URL(request.url);
        return envelope([row("a", false)]);
      })
    );
    render(<NotificationBell />);
    await waitFor(() => screen.getByText("1"));

    expect(requested).not.toBeNull();
    expect((requested as unknown as URL).searchParams.getAll("q")).toEqual(["read:eq:false"]);
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
          user: makeUser({ id: "u1", roles: ["super_admin"], tenantId: null }),
          status: "authenticated",
          selectedTenantId: null,
          impersonatedUserId: null,
          impersonatedBy: null,
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
          user: makeUser({ id: "u1", roles: ["super_admin"], tenantId: null }),
          status: "authenticated",
          selectedTenantId: null,
          impersonatedUserId: null,
          impersonatedBy: null,
        },
      },
    });
    store.dispatch(setSelectedTenantId("tenant-1"));
    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
  });

  it("refetches immediately when the effective user changes, e.g. impersonation start", async () => {
    let calls = 0;
    server.use(
      http.get(`${BASE}/api/v1/notifications`, () => {
        calls++;
        return envelope(calls === 1 ? [row("a", false)] : [row("a", false), row("b", false)]);
      })
    );
    const admin = makeUser({ id: "admin-1", roles: ["admin"], tenantId: "tenant-1" });
    const target = makeUser({ id: "target-1", roles: ["requester"], tenantId: "tenant-1" });
    const { store } = render(<NotificationBell />, {
      preloadedState: {
        auth: {
          user: admin,
          status: "authenticated",
          selectedTenantId: null,
          impersonatedUserId: null,
          impersonatedBy: null,
        },
      },
    });
    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());

    store.dispatch(setMe({ user: target, impersonatedBy: admin }));

    await waitFor(() => expect(screen.getByText("2")).toBeInTheDocument());
    expect(calls).toBe(2);
  });
});
