import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import { Role } from "@/lib/roles";
import { render, screen } from "@/test/test-utils";
import ProfilePage from "./page";

beforeAll(() => {
  // The avatar dialog's AvatarField turns the picked file into an object URL for
  // the selected-file preview; pin it to a fixed value so the src is assertable.
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
});

const USER: User = {
  id: "user-1",
  username: "alice",
  firstName: "Alice",
  lastName: "Smith",
  email: "alice@example.com",
  enabled: true,
  emailVerified: true,
  roles: [Role.DEVELOPER],
  groupRoles: [Role.APPROVER],
  tenantId: "tenant-1",
  avatarUpdatedAt: null,
  avatarConfig: null,
  deletedAt: null,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "user-1",
  updatedBy: "user-1",
};

const AUTHENTICATED = {
  auth: {
    user: USER,
    status: "authenticated" as const,
    selectedTenantId: null,
    impersonatedUserId: null,
    impersonatedBy: null,
  },
};

describe("ProfilePage", () => {
  it("titles the page with the user's name and shows the read-only detail cards", () => {
    render(<ProfilePage />, { preloadedState: AUTHENTICATED });

    expect(screen.getByRole("heading", { level: 1, name: "Alice Smith" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Account" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Access" })).toBeInTheDocument();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
  });

  it("keeps the avatar editor closed until the avatar is clicked", async () => {
    render(<ProfilePage />, { preloadedState: AUTHENTICATED });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Edit avatar" }));
    expect(screen.getByRole("dialog", { name: "Edit avatar" })).toBeInTheDocument();
  });

  it("loads and shows the user's groups and their group-inherited roles", async () => {
    render(<ProfilePage />, { preloadedState: AUTHENTICATED });

    // The default MSW handler for GET /api/v1/users/:userId/groups returns
    // USER_GROUP_1 ("Developers"); the chip only appears once that resolves.
    expect(await screen.findByText("Developers")).toBeInTheDocument();
    expect(screen.getByText("Approver")).toBeInTheDocument();
  });

  it("shows a spinner until the auth slice is populated", () => {
    render(<ProfilePage />);
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
  });
});
