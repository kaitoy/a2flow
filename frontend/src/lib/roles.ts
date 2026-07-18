/**
 * @module roles — Client-side role helpers mirroring the backend's authorization rules.
 *
 * The backend gates writes behind roles (see `dependencies/authz.py`); these
 * helpers let the UI hide actions the API would reject with HTTP 403. They are
 * a usability layer only — the backend remains the enforcement point.
 */
import { Role } from "@/generated/api/types.gen";
import type { User } from "@/lib/api";
import { useAppSelector } from "@/store/hooks";

export { Role };

/** Human-readable labels for each role, used by the admin user forms. */
export const ROLE_LABELS: Record<Role, string> = {
  [Role.SUPER_ADMIN]: "Super Admin",
  [Role.ADMIN]: "Admin",
  [Role.DEVELOPER]: "Developer",
  [Role.REQUESTER]: "Requester",
  [Role.APPROVER]: "Approver",
  [Role.TENANT_ADMIN]: "Tenant Admin",
};

/** Every role, in descending order of privilege — the order shown in the UI. */
export const ALL_ROLES: Role[] = [
  Role.SUPER_ADMIN,
  Role.ADMIN,
  Role.DEVELOPER,
  Role.REQUESTER,
  Role.APPROVER,
  Role.TENANT_ADMIN,
];

/**
 * Return whether `user` holds any of the given roles.
 *
 * A `super_admin` always passes, mirroring the backend's `has_role` bypass. A
 * `null` user (not yet loaded, or signed out) never passes.
 */
export function hasRole(user: User | null | undefined, ...roles: Role[]): boolean {
  const held = user?.roles ?? [];
  if (held.includes(Role.SUPER_ADMIN)) return true;
  return roles.some((role) => held.includes(role));
}

/**
 * React hook returning whether the signed-in user holds any of the given roles.
 *
 * Reads the authenticated user from the Redux auth slice, so it re-renders when
 * the session (and therefore the roles) changes.
 */
export function useHasRole(...roles: Role[]): boolean {
  const user = useAppSelector((s) => s.auth.user);
  return hasRole(user, ...roles);
}
