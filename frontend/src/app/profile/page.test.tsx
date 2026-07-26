import { beforeAll, describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import { Role } from "@/lib/roles";
import { render, screen } from "@/test/test-utils";
import ProfilePage from "./page";

beforeAll(() => {
  // jsdom doesn't implement object URLs; the embedded AvatarField uses them for
  // the selected-file preview.
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
      preloadedState: { auth: { user: USER, status: "authenticated" } },
    });

    expect(screen.getByRole("heading", { level: 1, name: "Profile" })).toBeInTheDocument();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Avatar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });

  it("shows a spinner until the auth slice is populated", () => {
    render(<ProfilePage />);
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
  });
});
