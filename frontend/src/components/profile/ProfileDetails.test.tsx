import { describe, expect, it } from "vitest";
import type { User, UserGroup } from "@/lib/api";
import { Role } from "@/lib/roles";
import { render, screen } from "@/test/test-utils";
import { ProfileDetails } from "./ProfileDetails";

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

const GROUP: UserGroup = {
  id: "group-1",
  tenantId: "tenant-1",
  name: "Developers",
  description: "People who build workflows",
  roles: [Role.DEVELOPER],
  memberIds: ["user-1"],
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "user-1",
  updatedBy: "user-1",
};

describe("ProfileDetails", () => {
  it("shows the display name and username header", () => {
    render(<ProfileDetails user={USER} groups={[GROUP]} />);
    expect(screen.getByText("Alice Smith")).toBeInTheDocument();
    expect(screen.getByText("@alice")).toBeInTheDocument();
  });

  it("falls back to the username when the user has no full name", () => {
    render(<ProfileDetails user={{ ...USER, firstName: "", lastName: "" }} groups={[GROUP]} />);
    // Once as the heading fallback, once as the Username value.
    expect(screen.getAllByText("alice")).toHaveLength(2);
  });

  it("lists every basic attribute", () => {
    render(<ProfileDetails user={USER} groups={[GROUP]} />);
    for (const label of [
      "Username",
      "Email",
      "First Name",
      "Last Name",
      "Roles",
      "Roles from Groups",
      "Groups",
      "Enabled",
      "Email Verified",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Smith")).toBeInTheDocument();
  });

  it("renders each role as a labelled badge", () => {
    render(<ProfileDetails user={USER} groups={[GROUP]} />);
    expect(screen.getByText("Admin")).toBeInTheDocument();
    expect(screen.getByText("Approver")).toBeInTheDocument();
  });

  it("shows a placeholder when the user holds no roles", () => {
    render(<ProfileDetails user={{ ...USER, roles: [] }} groups={[GROUP]} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders the boolean flags as Yes / No", () => {
    render(
      <ProfileDetails user={{ ...USER, enabled: false, emailVerified: true }} groups={[GROUP]} />
    );
    expect(screen.getByText("No")).toBeInTheDocument();
    expect(screen.getByText("Yes")).toBeInTheDocument();
  });

  it("renders each group the user belongs to as a chip", () => {
    render(<ProfileDetails user={USER} groups={[GROUP]} />);
    expect(screen.getByText("Developers")).toBeInTheDocument();
  });

  it("shows a placeholder when the user belongs to no group", () => {
    render(<ProfileDetails user={{ ...USER, groupRoles: [] }} groups={[]} />);
    // "Groups" and "Roles from Groups" both fall back to the same em-dash.
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
  });

  it("shows a spinner while groups are still loading", () => {
    render(<ProfileDetails user={USER} groups={null} />);
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
  });

  it("renders group-inherited roles as muted chips, distinct from direct roles", () => {
    render(<ProfileDetails user={USER} groups={[GROUP]} />);
    expect(screen.getByText("Developer")).toBeInTheDocument();
  });

  it("is entirely read-only — no form controls are rendered", () => {
    const { container } = render(<ProfileDetails user={USER} groups={[GROUP]} />);
    expect(container.querySelectorAll("input, textarea, select, button")).toHaveLength(0);
  });
});
