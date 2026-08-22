import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import { Role } from "@/lib/roles";
import { render, screen } from "@/test/test-utils";
import { ProfileHero } from "./profile-hero";

const USER: User = {
  id: "user-1",
  username: "alice",
  firstName: "Alice",
  lastName: "Smith",
  email: "alice@example.com",
  enabled: true,
  emailVerified: true,
  roles: [Role.ADMIN, Role.APPROVER],
  groupRoles: [Role.DEVELOPER],
  tenantId: "tenant-1",
  avatarUpdatedAt: null,
  avatarConfig: null,
  deletedAt: null,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "user-1",
  updatedBy: "user-1",
};

describe("ProfileHero", () => {
  it("titles the page with the user's display name", () => {
    render(<ProfileHero user={USER} onEditAvatar={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 1, name: "Alice Smith" })).toBeInTheDocument();
  });

  it("falls back to the username when the user has no full name", () => {
    render(<ProfileHero user={{ ...USER, firstName: "", lastName: "" }} onEditAvatar={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 1, name: "alice" })).toBeInTheDocument();
  });

  it("keeps 'Profile' as an eyebrow above the name, and shows the handle below it", () => {
    render(<ProfileHero user={USER} onEditAvatar={vi.fn()} />);
    expect(screen.getByText("Profile")).toBeInTheDocument();
    expect(screen.getByText("@alice")).toBeInTheDocument();
  });

  it("renders each direct role as a labelled badge", () => {
    render(<ProfileHero user={USER} onEditAvatar={vi.fn()} />);
    expect(screen.getByText("Admin")).toBeInTheDocument();
    expect(screen.getByText("Approver")).toBeInTheDocument();
  });

  it("renders the healthy account flags as status pills", () => {
    render(<ProfileHero user={USER} onEditAvatar={vi.fn()} />);
    expect(screen.getByText("Enabled")).toBeInTheDocument();
    expect(screen.getByText("Email verified")).toBeInTheDocument();
  });

  it("names the unhealthy state instead of negating the healthy one", () => {
    render(
      <ProfileHero
        user={{ ...USER, enabled: false, emailVerified: false }}
        onEditAvatar={vi.fn()}
      />
    );
    expect(screen.getByText("Disabled")).toBeInTheDocument();
    expect(screen.getByText("Email not verified")).toBeInTheDocument();
  });

  it("opens the avatar editor when the avatar is activated", async () => {
    const onEditAvatar = vi.fn();
    render(<ProfileHero user={USER} onEditAvatar={onEditAvatar} />);
    await userEvent.click(screen.getByRole("button", { name: "Edit avatar" }));
    expect(onEditAvatar).toHaveBeenCalledOnce();
  });
});
