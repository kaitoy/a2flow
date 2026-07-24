/** Redux slice holding the authenticated user resolved from the session cookie. */
import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { Me, User } from "@/lib/api";

/** Lifecycle of the auth check performed on app load. */
export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

/** localStorage key persisting the tenant a super_admin has selected to act as. */
export const SELECTED_TENANT_STORAGE_KEY = "a2flow.selectedTenantId";

/** localStorage key persisting the user id an admin/super_admin is impersonating. */
export const IMPERSONATED_USER_ID_STORAGE_KEY = "a2flow.impersonatedUserId";

/** Redux state shape for authentication. */
interface AuthState {
  /**
   * The effective current user: the impersonation target while one is
   * active, otherwise the real logged-in user.
   */
  user: User | null;
  /** Whether the initial `getMe` check is pending, resolved, or failed. */
  status: AuthStatus;
  /**
   * The tenant a platform-scoped (super_admin) user has selected to act as,
   * sent as the `X-Tenant-Id` header on every API request. `null` for a
   * tenant-scoped user, whose own tenant applies server-side regardless of
   * this value.
   */
  selectedTenantId: string | null;
  /**
   * The user id an admin/super_admin has chosen to impersonate, sent as the
   * `X-Impersonate-User-Id` header on every API request. Persisted to
   * `localStorage` so it survives a reload and can be attached to the very
   * first `getMe` call on boot. May be stale (e.g. stopped in another tab,
   * or the target became ineligible) -- `setMe` reconciles it against the
   * server's `impersonatedBy` on every `getMe`/login/impersonate response.
   */
  impersonatedUserId: string | null;
  /**
   * The real actor behind an active impersonation, or `null` when not
   * impersonating. Drives the "Acting as" header indicator.
   */
  impersonatedBy: User | null;
}

/** Read a value persisted by a previous session from `localStorage`, if any. */
function readInitialStorageValue(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

const initialState: AuthState = {
  user: null,
  status: "loading",
  selectedTenantId: readInitialStorageValue(SELECTED_TENANT_STORAGE_KEY),
  impersonatedUserId: readInitialStorageValue(IMPERSONATED_USER_ID_STORAGE_KEY),
  impersonatedBy: null,
};

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    /** Record the authenticated user and mark the session as authenticated. */
    setUser(state, action: PayloadAction<User>) {
      state.user = action.payload;
      state.status = "authenticated";
    },
    /**
     * Record the result of `getMe`/login/impersonate: the effective user and
     * the real actor (if impersonating). If the server reports no active
     * impersonation, clears `impersonatedUserId` too -- this is how a stale
     * local selection (stopped elsewhere, target since ineligible) self-heals.
     */
    setMe(state, action: PayloadAction<Me>) {
      state.user = action.payload.user;
      state.status = "authenticated";
      state.impersonatedBy = action.payload.impersonatedBy;
      if (action.payload.impersonatedBy === null) {
        state.impersonatedUserId = null;
      }
    },
    /** Clear the user and mark the session as unauthenticated. */
    clearUser(state) {
      state.user = null;
      state.status = "unauthenticated";
      state.selectedTenantId = null;
      state.impersonatedUserId = null;
      state.impersonatedBy = null;
    },
    /** Record the tenant a super_admin has selected to act as. */
    setSelectedTenantId(state, action: PayloadAction<string | null>) {
      state.selectedTenantId = action.payload;
    },
    /** Clear any impersonation state without otherwise touching the session. */
    clearImpersonation(state) {
      state.impersonatedUserId = null;
      state.impersonatedBy = null;
    },
  },
});

export const { setUser, setMe, clearUser, setSelectedTenantId, clearImpersonation } =
  authSlice.actions;

export default authSlice.reducer;
