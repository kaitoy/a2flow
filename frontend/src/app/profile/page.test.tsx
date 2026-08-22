import { beforeAll, describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import { Role } from "@/lib/roles";
import { render, screen } from "@/test/test-utils";
import ProfilePage from "./page";

beforeAll(() => {
  // The embedded AvatarField turns the picked file into an object URL for the
  // selected-file preview; pin it to a fixed value so the src is assertable.
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

describe("ProfilePage", () => {
  it("renders the read-only details above the editable avatar section", () => {
    render(<ProfilePage />, {
      preloadedState: {
        auth: {
          user: USER,
          status: "authenticated",
          selectedTenantId: null,
          impersonatedUserId: null,
          impersonatedBy: null,
        },
      },
    });

    expect(screen.getByRole("heading", { level: 1, name: "Profile" })).toBeInTheDocument();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Avatar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });

  it("loads and shows the user's groups and their group-inherited roles", async () => {
    render(<ProfilePage />, {
      preloadedState: {
        auth: {
          user: USER,
          status: "authenticated",
          selectedTenantId: null,
          impersonatedUserId: null,
          impersonatedBy: null,
        },
      },
    });

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
