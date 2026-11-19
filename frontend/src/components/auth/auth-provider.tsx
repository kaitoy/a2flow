/**
 * @module AuthProvider — Loads the current user into the auth slice on mount and
 * gates protected routes. While the `getMe` check is pending it shows a spinner;
 * if the session is invalid it redirects to `/login`, asking it to come back here.
 * A user who must change an admin-chosen password is sent to `/change-password`
 * the same way, and nothing else renders until they have.
 */
"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Spinner } from "@/components/ui/spinner";
import { getMe } from "@/lib/api";
import { changePasswordPath, loginPath } from "@/lib/next-path";
import { clearUser, setMe } from "@/store/authSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

/**
 * Wrap protected route trees so children only render once an authenticated user
 * has been resolved from the session cookie.
 *
 * @param props.children - The protected content to render once authenticated.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const dispatch = useAppDispatch();
  const router = useRouter();
  const pathname = usePathname();
  const status = useAppSelector((s) => s.auth.status);
  // The real user's flag, not an impersonation target's: the backend gates on
  // the session's own user, and so does this.
  const mustChangePassword = useAppSelector(
    (s) => (s.auth.impersonatedBy ?? s.auth.user)?.mustChangePassword === true
  );
  const heldForPassword =
    status === "authenticated" && mustChangePassword && pathname !== "/change-password";

  useEffect(() => {
    if (heldForPassword) {
      router.replace(changePasswordPath(window.location.pathname + window.location.search));
    }
  }, [heldForPassword, router]);

  useEffect(() => {
    let cancelled = false;
    getMe()
      .then((me) => {
        if (!cancelled) dispatch(setMe(me));
      })
      .catch(() => {
        if (cancelled) return;
        dispatch(clearUser());
        router.replace(loginPath(window.location.pathname + window.location.search));
      });
    return () => {
      cancelled = true;
    };
  }, [dispatch, router]);

  // While held, nothing renders: every resource API would answer 403 anyway.
  if (status !== "authenticated" || heldForPassword) {
    return (
      <div className="flex h-dvh items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  return <>{children}</>;
}
