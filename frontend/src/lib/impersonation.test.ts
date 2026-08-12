import { describe, expect, it } from "vitest";
import type { User } from "@/lib/api";
import { canImpersonate } from "@/lib/impersonation";
import { Role } from "@/lib/roles";

/** A signed-in viewer in the given tenant. */
const VIEWER = { id: "viewer", tenantId: "tenant-1" } as User;

/** Build the target shape `canImpersonate` inspects. */
function target(roles: Role[], groupRoles: Role[] = [], tenantId: string | null = "tenant-1") {
  return { id: "target", roles, groupRoles, tenantId };
}

describe("canImpersonate", () => {
  it("lets an admin impersonate an ordinary user in their tenant", () => {
    expect(canImpersonate(VIEWER, false, true, target([Role.DEVELOPER]))).toBe(true);
  });

  it("refuses a super_admin target, for anyone", () => {
    expect(canImpersonate(VIEWER, true, true, target([Role.SUPER_ADMIN], [], null))).toBe(false);
  });

  it("refuses an admin target for a plain admin viewer", () => {
    expect(canImpersonate(VIEWER, false, true, target([Role.ADMIN]))).toBe(false);
  });

  it("refuses a target whose admin comes from a group", () => {
    // Judging the target on direct roles alone would hand a plain admin exactly
    // the escalation this rule exists to block.
    expect(canImpersonate(VIEWER, false, true, target([], [Role.ADMIN]))).toBe(false);
  });

  it("still allows a super admin viewer to impersonate a group-inherited admin", () => {
    expect(canImpersonate(VIEWER, true, true, target([], [Role.ADMIN]))).toBe(true);
  });

  it("allows a target whose group grants something other than admin", () => {
    expect(canImpersonate(VIEWER, false, true, target([], [Role.DEVELOPER]))).toBe(true);
  });

  it("refuses the viewer themself", () => {
    expect(canImpersonate(VIEWER, true, true, { ...target([]), id: VIEWER.id })).toBe(false);
  });

  it("refuses a cross-tenant target for a plain admin", () => {
    expect(canImpersonate(VIEWER, false, true, target([], [], "tenant-2"))).toBe(false);
  });
});
