/** @module impersonation — Shared impersonation eligibility check and localStorage persistence of the active selection. */
import type { User } from "@/lib/api";
import { effectiveRoles, Role } from "@/lib/roles";
import { IMPERSONATED_USER_ID_STORAGE_KEY } from "@/store/authSlice";

/** Persist the impersonated user id to localStorage, ignoring privacy-mode write failures. */
export function persistImpersonatedUserId(userId: string | null): void {
  try {
    if (userId) {
      window.localStorage.setItem(IMPERSONATED_USER_ID_STORAGE_KEY, userId);
    } else {
      window.localStorage.removeItem(IMPERSONATED_USER_ID_STORAGE_KEY);
    }
  } catch {
    // Ignore -- privacy-mode browsers may throw on localStorage writes.
  }
}

/**
 * Whether `viewer` may impersonate `target`, mirroring the backend's
 * eligibility rules: a `super_admin` target can never be impersonated, an
 * `admin` target only by a `super_admin` viewer (a regular admin still can't
 * impersonate a fellow admin).
 *
 * The target is judged on its *effective* roles, so an `admin` inherited from a
 * user group protects them exactly as a directly granted one does — matching
 * `services/impersonation.py`, where treating the two differently would let a
 * plain admin escalate.
 */
export function canImpersonate(
  viewer: User | null,
  isSuperAdmin: boolean,
  isAdmin: boolean,
  target: Pick<User, "id" | "roles" | "tenantId" | "groupRoles">
): boolean {
  if (!viewer || target.id === viewer.id) return false;
  const held = effectiveRoles(target as User);
  if (held.includes(Role.SUPER_ADMIN)) return false;
  if (held.includes(Role.ADMIN) && !isSuperAdmin) return false;
  if (isSuperAdmin) return true;
  return isAdmin && target.tenantId === viewer.tenantId;
}
