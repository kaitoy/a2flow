/** Redux slice holding the authenticated user resolved from the session cookie. */
import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { User } from "@/lib/api";

/** Lifecycle of the auth check performed on app load. */
export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

/** localStorage key persisting the tenant a super_admin has selected to act as. */
export const SELECTED_TENANT_STORAGE_KEY = "a2flow.selectedTenantId";

/** Redux state shape for authentication. */
interface AuthState {
  /** The current user, or null when not authenticated. */
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
}

/** Read the tenant selection persisted by a previous session, if any. */
function readInitialSelectedTenantId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(SELECTED_TENANT_STORAGE_KEY);
  } catch {
    return null;
  }
}

const initialState: AuthState = {
  user: null,
  status: "loading",
  selectedTenantId: readInitialSelectedTenantId(),
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
    /** Clear the user and mark the session as unauthenticated. */
    clearUser(state) {
      state.user = null;
      state.status = "unauthenticated";
      state.selectedTenantId = null;
    },
    /** Record the tenant a super_admin has selected to act as. */
    setSelectedTenantId(state, action: PayloadAction<string | null>) {
      state.selectedTenantId = action.payload;
    },
  },
});

export const { setUser, clearUser, setSelectedTenantId } = authSlice.actions;

export default authSlice.reducer;
