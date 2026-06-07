/** @module LogoutButton — Logs the current user out and returns to the login page. */
"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { Button } from "@/components/ui/button";
import { logout } from "@/lib/api";
import { clearUser } from "@/store/authSlice";
import { useAppDispatch } from "@/store/hooks";

/**
 * Button that revokes the session via the API, clears the auth slice, and
 * navigates to `/login`.
 *
 * @param props.className - Optional extra classes for layout.
 */
export function LogoutButton({ className }: { className?: string }) {
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [pending, setPending] = useState(false);

  const onLogout = useCallback(async () => {
    setPending(true);
    try {
      await logout();
    } catch {
      // Even if the request fails, drop local auth state and leave.
    }
    dispatch(clearUser());
    router.replace("/login");
  }, [dispatch, router]);

  return (
    <Button variant="ghost" onClick={onLogout} disabled={pending} className={className}>
      Log out
    </Button>
  );
}
