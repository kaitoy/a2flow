/** Redux slice holding the authenticated user resolved from the session cookie. */
import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { User } from "@/lib/api";

/** Lifecycle of the auth check performed on app load. */
export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

/** Redux state shape for authentication. */
interface AuthState {
  /** The current user, or null when not authenticated. */
  user: User | null;
  /** Whether the initial `getMe` check is pending, resolved, or failed. */
  status: AuthStatus;
}

const initialState: AuthState = {
  user: null,
  status: "loading",
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
    },
  },
});

export const { setUser, clearUser } = authSlice.actions;

export default authSlice.reducer;
