/** @module impersonation — localStorage persistence for the active impersonation selection. */
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
