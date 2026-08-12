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
};

/** Every role, in descending order of privilege — the order shown in the UI. */
export const ALL_ROLES: Role[] = [
  Role.SUPER_ADMIN,
  Role.ADMIN,
  Role.DEVELOPER,
  Role.REQUESTER,
  Role.APPROVER,
];

/**
 * Return a user's effective roles: their direct grants plus everything
 * inherited from the user groups they belong to.
 *
 * The backend applies the same union at every authorization check (see
 * `dependencies/auth.py`'s `get_effective_roles`), so the UI has to as well —
 * otherwise a user whose only `developer` grant comes from a group would see
 * an empty admin nav and read-only forms for actions the API would allow.
 */
export function effectiveRoles(user: User | null | undefined): Role[] {
  return [...(user?.roles ?? []), ...(user?.groupRoles ?? [])];
}

/**
 * Return whether `user` holds any of the given roles, directly or through a group.
 *
 * A `super_admin` always passes, mirroring the backend's `has_any_role` bypass.
 * That check reads the direct grants only, again mirroring the backend: a user
 * group can never grant `super_admin`. A `null` user (not yet loaded, or signed
 * out) never passes.
 */
export function hasRole(user: User | null | undefined, ...roles: Role[]): boolean {
  if ((user?.roles ?? []).includes(Role.SUPER_ADMIN)) return true;
  const held = effectiveRoles(user);
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
