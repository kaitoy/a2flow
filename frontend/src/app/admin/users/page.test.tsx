import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { Role } from "@/lib/roles";
import type { RootState } from "@/store";
import { store as appStore } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import UsersPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

/** Build a preloaded auth slice for a signed-in viewer holding the given roles/tenant. */
function authState(roles: Role[], tenantId?: string): Partial<RootState> {
  return {
    auth: { user: { id: "viewer-1", roles, tenantId } as User, status: "authenticated" },
  };
}

/** A super_admin viewer, unrestricted by tenant. */
const SUPER_ADMIN_STATE = authState(["super_admin" as Role]);
/** An admin viewer scoped to tenant-1, mirroring the default USER_1 mock's tenant. */
const ADMIN_TENANT_1_STATE = authState(["admin" as Role], "tenant-1");

function routerMock() {
  const push = vi.fn();
  vi.mocked(useRouter).mockReturnValue({
    push,
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
    refresh: vi.fn(),
  });
  return push;
}

describe("UsersPage", () => {
  it("shows loading state initially", () => {
    routerMock();
    render(<UsersPage />, { preloadedState: SUPER_ADMIN_STATE });
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders user row after load", async () => {
    routerMock();
    render(<UsersPage />, { preloadedState: SUPER_ADMIN_STATE });
    await waitFor(() => expect(screen.getByText("alice")).toBeInTheDocument());
    expect(screen.getByText("Alice Smith")).toBeInTheDocument();
  });

  it("username links to the edit page", async () => {
    routerMock();
    render(<UsersPage />, { preloadedState: SUPER_ADMIN_STATE });
    await waitFor(() => screen.getByText("alice"));
    expect(screen.getByRole("link", { name: "alice" })).toHaveAttribute(
      "href",
      "/admin/users/user-1"
    );
  });

  it("shows empty state when no users", async () => {
    routerMock();
    server.use(http.get("http://localhost:8000/api/v1/users", () => envelope([])));
    render(<UsersPage />, { preloadedState: SUPER_ADMIN_STATE });
    await waitFor(() => expect(screen.getByText("No users registered yet.")).toBeInTheDocument());
  });

  it("shows a Super Admin badge for a super_admin user", async () => {
    routerMock();
    server.use(
      http.get("http://localhost:8000/api/v1/users", () =>
        envelope([
          {
            id: "user-1",
            username: "alice",
            firstName: "Alice",
            lastName: "Smith",
            email: "alice@example.com",
            enabled: true,
            emailVerified: false,
            roles: ["super_admin"],
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "",
            updatedBy: "",
          },
        ])
      )
    );
    render(<UsersPage />, { preloadedState: SUPER_ADMIN_STATE });
    await waitFor(() => expect(screen.getByText("Super Admin")).toBeInTheDocument());
  });

  it("does not show a Super Admin badge for a regular user", async () => {
    routerMock();
    render(<UsersPage />, { preloadedState: SUPER_ADMIN_STATE });
    await waitFor(() => screen.getByText("alice"));
    expect(screen.queryByText("Super Admin")).not.toBeInTheDocument();
  });

  it("shows an error toast on api failure", async () => {
    routerMock();
    server.use(
      http.get("http://localhost:8000/api/v1/users", () =>
        envelopeErr("INTERNAL_ERROR", "Internal server error", 500)
      )
    );
    render(<UsersPage />, { preloadedState: SUPER_ADMIN_STATE });
    await waitFor(() =>
      expect(appStore.getState().toast.items.at(-1)).toMatchObject({
        message: "Internal server error",
        variant: "error",
      })
    );
  });

  it("add user link is present", async () => {
    routerMock();
    render(<UsersPage />, { preloadedState: SUPER_ADMIN_STATE });
    await waitFor(() => screen.getByText("alice"));
    expect(screen.getByRole("link", { name: /add user/i })).toHaveAttribute(
      "href",
      "/admin/users/new"
    );
  });

  it("calls delete api after confirm", async () => {
    routerMock();
    const user = userEvent.setup();
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/users/:id", deleteSpy));

    render(<UsersPage />, { preloadedState: SUPER_ADMIN_STATE });
    await waitFor(() => screen.getByText("alice"));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    expect(deleteSpy).toHaveBeenCalled();
  });

  describe("impersonate action", () => {
    it("shows the Impersonate button for a super_admin viewer", async () => {
      routerMock();
      render(<UsersPage />, { preloadedState: SUPER_ADMIN_STATE });
      await waitFor(() => screen.getByText("alice"));
      expect(screen.getByRole("button", { name: "Impersonate" })).toBeInTheDocument();
    });

    it("hides the Impersonate button for a row holding super_admin", async () => {
      routerMock();
      server.use(
        http.get("http://localhost:8000/api/v1/users", () =>
          envelope([
            {
              id: "user-1",
              username: "alice",
              firstName: "Alice",
              lastName: "Smith",
              email: "alice@example.com",
              enabled: true,
              emailVerified: false,
              roles: ["super_admin"],
              createdAt: "2026-01-01T00:00:00Z",
              updatedAt: "2026-01-01T00:00:00Z",
              createdBy: "",
              updatedBy: "",
            },
          ])
        )
      );
      render(<UsersPage />, { preloadedState: SUPER_ADMIN_STATE });
      await waitFor(() => screen.getByText("alice"));
      expect(screen.queryByRole("button", { name: "Impersonate" })).not.toBeInTheDocument();
    });

    it("shows the Impersonate button for a row holding admin when the viewer is super_admin", async () => {
      routerMock();
      server.use(
        http.get("http://localhost:8000/api/v1/users", () =>
          envelope([
            {
              id: "user-1",
              username: "alice",
              firstName: "Alice",
              lastName: "Smith",
              email: "alice@example.com",
              enabled: true,
              emailVerified: false,
              roles: ["admin"],
              createdAt: "2026-01-01T00:00:00Z",
              updatedAt: "2026-01-01T00:00:00Z",
              createdBy: "",
              updatedBy: "",
            },
          ])
        )
      );
      render(<UsersPage />, { preloadedState: SUPER_ADMIN_STATE });
      await waitFor(() => screen.getByText("alice"));
      expect(screen.getByRole("button", { name: "Impersonate" })).toBeInTheDocument();
    });

    it("hides the Impersonate button for a row holding admin when the viewer is a regular admin", async () => {
      routerMock();
      server.use(
        http.get("http://localhost:8000/api/v1/users", () =>
          envelope([{ ...USER_WITH_TENANT("tenant-1"), roles: ["admin"] }])
        )
      );
      render(<UsersPage />, { preloadedState: ADMIN_TENANT_1_STATE });
      await waitFor(() => screen.getByText("alice"));
      expect(screen.queryByRole("button", { name: "Impersonate" })).not.toBeInTheDocument();
    });

    it("hides the Impersonate button for the viewer's own row", async () => {
      routerMock();
      render(<UsersPage />, {
        preloadedState: {
          auth: {
            user: { id: "user-1", roles: ["super_admin"] } as User,
            status: "authenticated",
          },
        },
      });
      await waitFor(() => screen.getByText("alice"));
      expect(screen.queryByRole("button", { name: "Impersonate" })).not.toBeInTheDocument();
    });

    it("shows the Impersonate button for an admin viewer targeting their own tenant", async () => {
      routerMock();
      server.use(
        http.get("http://localhost:8000/api/v1/users", () =>
          envelope([USER_WITH_TENANT("tenant-1")])
        )
      );
      render(<UsersPage />, { preloadedState: ADMIN_TENANT_1_STATE });
      await waitFor(() => screen.getByText("alice"));
      expect(screen.getByRole("button", { name: "Impersonate" })).toBeInTheDocument();
    });

    it("hides the Impersonate button for an admin viewer targeting a different tenant", async () => {
      routerMock();
      server.use(
        http.get("http://localhost:8000/api/v1/users", () =>
          envelope([USER_WITH_TENANT("tenant-2")])
        )
      );
      render(<UsersPage />, { preloadedState: ADMIN_TENANT_1_STATE });
      await waitFor(() => screen.getByText("alice"));
      expect(screen.queryByRole("button", { name: "Impersonate" })).not.toBeInTheDocument();
    });

    it("calls the impersonate api after confirm and navigates to /admin", async () => {
      const push = routerMock();
      const user = userEvent.setup();
      const impersonateSpy = vi.fn(() =>
        envelope({
          user: {
            id: "user-1",
            username: "alice",
            firstName: "Alice",
            lastName: "Smith",
            email: "alice@example.com",
            enabled: true,
            emailVerified: false,
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "",
            updatedBy: "",
          },
          impersonatedBy: {
            id: "viewer-1",
            username: "super",
            firstName: "Super",
            lastName: "Admin",
            email: "super@example.com",
            enabled: true,
            emailVerified: false,
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "",
            updatedBy: "",
          },
        })
      );
      server.use(http.post("http://localhost:8000/api/v1/auth/impersonate", impersonateSpy));

      render(<UsersPage />, { preloadedState: SUPER_ADMIN_STATE });
      await waitFor(() => screen.getByText("alice"));
      await user.click(screen.getByRole("button", { name: "Impersonate" }));
      const dialog = screen.getByRole("dialog");
      await user.click(within(dialog).getByRole("button", { name: /impersonate/i }));

      await waitFor(() => expect(impersonateSpy).toHaveBeenCalled());
      expect(push).toHaveBeenCalledWith("/admin");
    });
  });
});

/** A user row with a `tenantId`, for the admin-viewer eligibility tests. */
function USER_WITH_TENANT(tenantId: string) {
  return {
    id: "user-1",
    username: "alice",
    firstName: "Alice",
    lastName: "Smith",
    email: "alice@example.com",
    enabled: true,
    emailVerified: false,
    tenantId,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
  };
}
