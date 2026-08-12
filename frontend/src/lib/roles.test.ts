import { describe, expect, it } from "vitest";
import type { User } from "@/lib/api";
import { ALL_ROLES, effectiveRoles, hasRole, ROLE_LABELS, Role } from "@/lib/roles";

/** Build a minimal signed-in user holding the given roles. */
function user(roles: Role[], groupRoles: Role[] = []): User {
  return { id: "u1", roles, groupRoles } as User;
}

describe("hasRole", () => {
  it("returns true when the user holds one of the requested roles", () => {
    expect(hasRole(user([Role.DEVELOPER, Role.APPROVER]), Role.DEVELOPER)).toBe(true);
  });

  it("returns false when the user holds none of them", () => {
    expect(hasRole(user([Role.APPROVER]), Role.ADMIN, Role.DEVELOPER)).toBe(false);
  });

  it("lets a super admin pass any role check", () => {
    expect(hasRole(user([Role.SUPER_ADMIN]), Role.ADMIN)).toBe(true);
    expect(hasRole(user([Role.SUPER_ADMIN]), Role.REQUESTER)).toBe(true);
  });

  it("returns false for a role-less user", () => {
    expect(hasRole(user([]), Role.REQUESTER)).toBe(false);
  });

  it("returns false when no user is signed in", () => {
    expect(hasRole(null, Role.ADMIN)).toBe(false);
    expect(hasRole(undefined, Role.ADMIN)).toBe(false);
  });
});

describe("role metadata", () => {
  it("labels every role", () => {
    for (const role of ALL_ROLES) {
      expect(ROLE_LABELS[role]).toBeTruthy();
    }
  });
});

describe("roles inherited from user groups", () => {
  it("unions the direct grants with the inherited ones", () => {
    expect(effectiveRoles(user([Role.ADMIN], [Role.DEVELOPER]))).toEqual([
      Role.ADMIN,
      Role.DEVELOPER,
    ]);
  });

  it("passes a role held only through a group", () => {
    expect(hasRole(user([], [Role.DEVELOPER]), Role.DEVELOPER)).toBe(true);
  });

  it("still refuses a role held neither way", () => {
    expect(hasRole(user([Role.REQUESTER], [Role.DEVELOPER]), Role.ADMIN)).toBe(false);
  });

  it("keeps the super_admin bypass on the direct grants", () => {
    // A user group can never grant super_admin, matching the backend.
    expect(hasRole(user([Role.SUPER_ADMIN], []), Role.REQUESTER)).toBe(true);
  });

  it("tolerates a user with no groupRoles field", () => {
    expect(effectiveRoles({ id: "u1", roles: [Role.ADMIN] } as User)).toEqual([Role.ADMIN]);
  });
});
