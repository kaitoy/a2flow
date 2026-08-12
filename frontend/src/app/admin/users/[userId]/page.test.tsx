import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { RootState } from "@/store";
import { store } from "@/store";
import { ADMIN, DEVELOPER } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import UserDetailPage from "./page";

/** Render the page as an admin — the role updating or deleting a user requires. */
function renderPage() {
  return render(<UserDetailPage />, { preloadedState: ADMIN });
}

/** Render the page as a developer, who may read a user but never write one. */
function renderPageReadOnly() {
  return render(<UserDetailPage />, { preloadedState: DEVELOPER });
}

/** Build a preloaded auth slice for a signed-in super admin acting as a given tenant. */
function superAdminState(selectedTenantId: string | null): Partial<RootState> {
  return {
    auth: {
      user: { id: "u1", roles: ["super_admin"] } as User,
      status: "authenticated",
      selectedTenantId,
      impersonatedUserId: null,
      impersonatedBy: null,
    },
  };
}

// Replace the real Avatar with a stub that surfaces the avatarConfig and tenantId
// it receives, so the test can assert the page threads the loaded customization
// and seed through to the preview without depending on the renderer's internals.
vi.mock("@/components/ui/avatar", () => ({
  Avatar: ({ user }: { user: { avatarConfig?: unknown; tenantId?: unknown } | null }) => (
    <div
      data-testid="avatar"
      data-config={JSON.stringify(user?.avatarConfig ?? null)}
      data-tenant={JSON.stringify(user?.tenantId ?? null)}
    />
  ),
}));

const FULL_USER = {
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
};

function setup() {
  vi.mocked(useParams).mockReturnValue({ userId: "user-1" });
}

describe("UserDetailPage", () => {
  it("titles the page and ends the breadcrumb trail with the username", async () => {
    setup();
    renderPage();
    expect(await screen.findByRole("heading", { name: "alice" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByText("alice")).toHaveAttribute("aria-current", "page");
  });

  it("prefills form with user data", async () => {
    setup();
    renderPage();
    await waitFor(() => expect(screen.getByDisplayValue("Alice")).toBeInTheDocument());
    expect(screen.getByDisplayValue("Smith")).toBeInTheDocument();
    expect(screen.getByDisplayValue("alice@example.com")).toBeInTheDocument();
  });

  it("submits update api on form submit", async () => {
    setup();
    const patchSpy = vi.fn(() => envelope(FULL_USER));
    server.use(http.patch("http://localhost:8000/api/v1/users/:userId", patchSpy));

    renderPage();
    await waitFor(() => screen.getByDisplayValue("Alice"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalled());
  });

  it("omits password from the request body when left blank", async () => {
    setup();
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("http://localhost:8000/api/v1/users/:userId", async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return envelope(FULL_USER);
      })
    );

    renderPage();
    await waitFor(() => screen.getByDisplayValue("Alice"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    expect(capturedBody).not.toHaveProperty("password");
  });

  it("includes password in the request body when provided", async () => {
    setup();
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("http://localhost:8000/api/v1/users/:userId", async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return envelope(FULL_USER);
      })
    );

    renderPage();
    await waitFor(() => screen.getByDisplayValue("Alice"));
    await userEvent.type(screen.getByLabelText(/password/i), "newsecret456");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    expect(capturedBody).toMatchObject({ password: "newsecret456" });
  });

  it("navigates to list after save", async () => {
    setup();
    const pushMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({
      push: pushMock,
      replace: vi.fn(),
      back: vi.fn(),
      prefetch: vi.fn(),
      refresh: vi.fn(),
      forward: vi.fn(),
    });

    renderPage();
    await waitFor(() => screen.getByDisplayValue("Alice"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/users"));
  });

  it("calls delete api and navigates after confirm", async () => {
    setup();
    const pushMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({
      push: pushMock,
      replace: vi.fn(),
      back: vi.fn(),
      prefetch: vi.fn(),
      refresh: vi.fn(),
      forward: vi.fn(),
    });
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/users/:userId", deleteSpy));

    renderPage();
    await waitFor(() => screen.getByDisplayValue("Alice"));
    await userEvent.click(screen.getByRole("button", { name: /delete/i }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalled());
    expect(pushMock).toHaveBeenCalledWith("/admin/users");
  });

  it("renders the immutable username as a value, not an input", async () => {
    setup();
    renderPage();
    await waitFor(() => screen.getByDisplayValue("Alice"));
    expect(screen.queryByRole("textbox", { name: /username/i })).not.toBeInTheDocument();
    // The heading and the breadcrumb carry the username too; the field value is
    // the only one rendered on a ReadOnlyField's <p>.
    expect(screen.getByText("alice", { selector: "p" })).toHaveClass("bg-surface-dim/40");
  });

  it("omits username from the request body", async () => {
    setup();
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("http://localhost:8000/api/v1/users/:userId", async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return envelope(FULL_USER);
      })
    );

    renderPage();
    await waitFor(() => screen.getByDisplayValue("Alice"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    expect(capturedBody).not.toHaveProperty("username");
  });

  it("shows validation error on blur when required field is cleared", async () => {
    setup();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByDisplayValue("Alice"));
    const firstNameInput = screen.getByRole("textbox", { name: /first name/i });
    await user.clear(firstNameInput);
    await user.tab();
    await waitFor(() => expect(screen.getByText(/at least 1 character/i)).toBeInTheDocument());
  });

  it("passes the loaded avatar customization to the preview", async () => {
    setup();
    const avatarConfig = { colors: ["#4A3728", "#EFEFEF"] };
    server.use(
      http.get("http://localhost:8000/api/v1/users/:userId", () =>
        envelope({ ...FULL_USER, avatarConfig })
      )
    );

    renderPage();
    await waitFor(() => screen.getByDisplayValue("Alice"));

    expect(screen.getByTestId("avatar")).toHaveAttribute(
      "data-config",
      JSON.stringify(avatarConfig)
    );
  });

  it("seeds the preview from the tenant the user is stored with", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/users/:userId", () =>
        envelope({ ...FULL_USER, tenantId: "tenant-7" })
      )
    );

    renderPage();
    await waitFor(() => screen.getByDisplayValue("Alice"));

    expect(screen.getByTestId("avatar")).toHaveAttribute("data-tenant", JSON.stringify("tenant-7"));
  });

  it("does not render a tenant field for a non-super-admin viewer", async () => {
    setup();
    renderPage();
    await waitFor(() => screen.getByDisplayValue("Alice"));
    expect(screen.queryByLabelText("Tenant")).not.toBeInTheDocument();
  });

  it("does not render a tenant field for a super-admin viewer either", async () => {
    setup();
    render(<UserDetailPage />, { preloadedState: superAdminState("tenant-1") });
    await waitFor(() => screen.getByDisplayValue("Alice"));
    expect(screen.queryByLabelText("Tenant")).not.toBeInTheDocument();
  });

  it("submits the app-bar selected tenant when demoting a still-tenant-less super admin", async () => {
    setup();
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.get("http://localhost:8000/api/v1/users/:userId", () =>
        envelope({ ...FULL_USER, roles: ["super_admin"] })
      ),
      http.patch("http://localhost:8000/api/v1/users/:userId", async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return envelope(FULL_USER);
      })
    );

    render(<UserDetailPage />, { preloadedState: superAdminState("tenant-1") });
    await waitFor(() => screen.getByDisplayValue("Alice"));
    await userEvent.click(screen.getByRole("checkbox", { name: "Super Admin" }));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(capturedBody?.tenantId).toBe("tenant-1"));
    expect(capturedBody).toMatchObject({ roles: [] });
  });

  it("keeps a super admin's tenantId null on save regardless of the app-bar selection", async () => {
    setup();
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.get("http://localhost:8000/api/v1/users/:userId", () =>
        envelope({ ...FULL_USER, roles: ["super_admin"] })
      ),
      http.patch("http://localhost:8000/api/v1/users/:userId", async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return envelope(FULL_USER);
      })
    );

    render(<UserDetailPage />, { preloadedState: superAdminState("tenant-1") });
    await waitFor(() => screen.getByDisplayValue("Alice"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(capturedBody?.tenantId).toBeNull());
  });

  it("keeps an already-assigned tenant unchanged on save, regardless of the app-bar selection", async () => {
    setup();
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.get("http://localhost:8000/api/v1/users/:userId", () =>
        envelope({ ...FULL_USER, tenantId: "tenant-1" })
      ),
      http.patch("http://localhost:8000/api/v1/users/:userId", async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return envelope(FULL_USER);
      })
    );

    render(<UserDetailPage />, { preloadedState: superAdminState("tenant-2") });
    await waitFor(() => screen.getByDisplayValue("Alice"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(capturedBody?.tenantId).toBe("tenant-1"));
  });

  it("shows a validation error when granting super_admin to a user who already has a tenant assigned", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/users/:userId", () =>
        envelope({ ...FULL_USER, tenantId: "tenant-1" })
      ),
      http.patch("http://localhost:8000/api/v1/users/:userId", () =>
        envelopeErr("INVALID_USER", "A super admin cannot be assigned a tenant", 422)
      )
    );

    render(<UserDetailPage />, { preloadedState: superAdminState("tenant-1") });
    await waitFor(() => screen.getByDisplayValue("Alice"));
    await userEvent.click(screen.getByRole("checkbox", { name: "Super Admin" }));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "A super admin cannot be assigned a tenant",
        variant: "error",
      })
    );
  });

  it("disables save and shows a hint when demoting a super admin with no tenant selected in the app bar", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/users/:userId", () =>
        envelope({ ...FULL_USER, roles: ["super_admin"] })
      )
    );

    render(<UserDetailPage />, { preloadedState: superAdminState(null) });
    await waitFor(() => screen.getByDisplayValue("Alice"));

    await userEvent.click(screen.getByRole("checkbox", { name: "Super Admin" }));

    expect(screen.getByRole("button", { name: /save/i })).toBeDisabled();
    expect(
      screen.getByText(
        /select a tenant in the header before removing this user's super admin role/i
      )
    ).toBeInTheDocument();
  });

  it("shows a Super Admin badge for a super_admin target", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/users/:userId", () =>
        envelope({ ...FULL_USER, roles: ["super_admin"] })
      )
    );

    renderPage();
    await waitFor(() => screen.getByDisplayValue("Alice"));

    expect(screen.getByText("Super Admin")).toBeInTheDocument();
  });

  it("does not show a Super Admin badge for a non-super-admin target", async () => {
    setup();
    renderPage();
    await waitFor(() => screen.getByDisplayValue("Alice"));

    expect(screen.queryByText("Super Admin")).not.toBeInTheDocument();
  });

  it("shows error on load failure", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/users/:userId", () =>
        envelopeErr("NOT_FOUND", "User not found", 404)
      )
    );

    renderPage();
    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "User not found",
        variant: "error",
      })
    );
  });

  it("shows the access-denied state and no toast on a FORBIDDEN load failure", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/users/:userId", () =>
        envelopeErr("FORBIDDEN", "Requires developer", 403)
      )
    );
    const beforeCount = store.getState().toast.items.length;

    renderPage();

    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(store.getState().toast.items.length).toBe(beforeCount);
  });

  describe("without the admin role", () => {
    it("renders the profile fields, roles, and flags as values", async () => {
      setup();
      server.use(
        http.get("http://localhost:8000/api/v1/users/:userId", () =>
          envelope({ ...FULL_USER, roles: ["developer", "approver"] })
        )
      );
      renderPageReadOnly();

      expect(await screen.findByRole("heading", { name: "alice" })).toBeInTheDocument();
      expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
      expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
      expect(screen.getByText("Alice")).toBeInTheDocument();
      expect(screen.getByText("alice@example.com")).toBeInTheDocument();
      expect(screen.getByText("Developer, Approver")).toBeInTheDocument();
      expect(screen.getByText("Yes")).toBeInTheDocument();
      expect(screen.getByText("No")).toBeInTheDocument();
    });

    it("omits the password field entirely", async () => {
      setup();
      renderPageReadOnly();

      expect(await screen.findByRole("heading", { name: "alice" })).toBeInTheDocument();
      expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
      expect(screen.queryByText("Password")).not.toBeInTheDocument();
    });

    it("hides Save and Delete and offers Back instead of Cancel", async () => {
      setup();
      renderPageReadOnly();

      expect(await screen.findByRole("heading", { name: "alice" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /back/i })).toBeInTheDocument();
    });
  });

  describe("impersonate action", () => {
    it("shows the Impersonate button for an eligible target", async () => {
      setup();
      render(<UserDetailPage />, { preloadedState: superAdminState(null) });
      await waitFor(() => screen.getByDisplayValue("Alice"));
      expect(screen.getByRole("button", { name: "Impersonate" })).toBeInTheDocument();
    });

    it("hides the Impersonate button when the target holds super_admin", async () => {
      setup();
      server.use(
        http.get("http://localhost:8000/api/v1/users/:userId", () =>
          envelope({ ...FULL_USER, roles: ["super_admin"] })
        )
      );
      render(<UserDetailPage />, { preloadedState: superAdminState(null) });
      await waitFor(() => screen.getByDisplayValue("Alice"));
      expect(screen.queryByRole("button", { name: "Impersonate" })).not.toBeInTheDocument();
    });

    it("hides the Impersonate button when viewing your own account", async () => {
      setup();
      render(<UserDetailPage />, {
        preloadedState: {
          auth: {
            user: { id: "user-1", roles: ["super_admin"] } as User,
            status: "authenticated",
            selectedTenantId: null,
            impersonatedUserId: null,
            impersonatedBy: null,
          },
        },
      });
      await waitFor(() => screen.getByDisplayValue("Alice"));
      expect(screen.queryByRole("button", { name: "Impersonate" })).not.toBeInTheDocument();
    });

    it("calls the impersonate api after confirm and navigates to /admin", async () => {
      setup();
      const pushMock = vi.fn();
      vi.mocked(useRouter).mockReturnValue({
        push: pushMock,
        replace: vi.fn(),
        back: vi.fn(),
        prefetch: vi.fn(),
        refresh: vi.fn(),
        forward: vi.fn(),
      });
      const impersonateSpy = vi.fn(() =>
        envelope({
          user: FULL_USER,
          impersonatedBy: {
            id: "u1",
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

      render(<UserDetailPage />, { preloadedState: superAdminState(null) });
      await waitFor(() => screen.getByDisplayValue("Alice"));
      await userEvent.click(screen.getByRole("button", { name: "Impersonate" }));
      const dialog = screen.getByRole("dialog");
      await userEvent.click(within(dialog).getByRole("button", { name: /impersonate/i }));

      await waitFor(() => expect(impersonateSpy).toHaveBeenCalled());
      expect(pushMock).toHaveBeenCalledWith("/admin");
    });
  });
});

describe("UserDetailPage group membership", () => {
  it("shows the roles inherited from the user's groups, apart from the direct ones", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/users/:userId", () =>
        envelope({
          id: "user-1",
          username: "alice",
          firstName: "Alice",
          lastName: "Smith",
          email: "alice@example.com",
          enabled: true,
          emailVerified: false,
          tenantId: "tenant-1",
          roles: ["approver"],
          groupRoles: ["developer"],
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        })
      )
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("Roles from groups")).toBeInTheDocument());
    // Direct grants stay editable; inherited ones render as read-only chips.
    expect(screen.getByRole("checkbox", { name: "Approver" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Developer" })).not.toBeChecked();
    // The explanatory line only renders when something is actually inherited.
    expect(screen.getByText(/Granted by group membership/)).toBeInTheDocument();
  });

  it("shows a chip for each group the user already belongs to", async () => {
    renderPage();
    expect(await screen.findByText("Developers")).toBeInTheDocument();
  });

  it("writes membership only when the selection changed", async () => {
    let membershipWrites = 0;
    server.use(
      http.put("http://localhost:8000/api/v1/users/:userId/groups", () => {
        membershipWrites += 1;
        return envelope({ id: "user-1" });
      })
    );
    renderPage();
    await screen.findByText("Developers");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(membershipWrites).toBe(0));
  });

  it("writes the new membership when a group is removed", async () => {
    let body: unknown;
    server.use(
      http.put("http://localhost:8000/api/v1/users/:userId/groups", async ({ request }) => {
        body = await request.json();
        return envelope({ id: "user-1" });
      })
    );
    renderPage();
    await screen.findByText("Developers");
    await userEvent.click(screen.getByRole("button", { name: "Remove Developers" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(body).toEqual({ groupIds: [] }));
  });

  it("hides the group picker for a platform-scoped user", async () => {
    // A super admin carries no tenantId and can never be a group member.
    server.use(
      http.get("http://localhost:8000/api/v1/users/:userId", () =>
        envelope({
          id: "user-1",
          username: "root",
          firstName: "Root",
          lastName: "User",
          email: "root@example.com",
          enabled: true,
          emailVerified: false,
          tenantId: null,
          roles: ["super_admin"],
          groupRoles: [],
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        })
      )
    );
    renderPage();
    await waitFor(() => screen.getByDisplayValue("Root"));
    expect(screen.queryByText("Groups")).not.toBeInTheDocument();
  });
});
