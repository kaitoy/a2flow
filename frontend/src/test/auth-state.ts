/** @module auth-state — Preloaded Redux auth state for role-gated component tests. */
import type { User } from "@/lib/api";
import type { RootState } from "@/store";

/** Build a preloaded auth slice for a signed-in user holding the given roles. */
export function authState(roles: string[]): Partial<RootState> {
  return {
    auth: {
      user: { id: "u1", roles } as User,
      status: "authenticated",
      selectedTenantId: null,
      impersonatedUserId: null,
      impersonatedBy: null,
    },
  };
}

/** Preloaded state for a signed-in `super_admin`. */
export const SUPER_ADMIN = authState(["super_admin"]);
/** Preloaded state for a signed-in `admin`. */
export const ADMIN = authState(["admin"]);
/** Preloaded state for a signed-in `requester`. */
export const REQUESTER = authState(["requester"]);
/** Preloaded state for a signed-in `developer`. */
export const DEVELOPER = authState(["developer"]);
