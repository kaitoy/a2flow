/**
 * @module AuthProvider — Loads the current user into the auth slice on mount and
 * gates protected routes. While the `getMe` check is pending it shows a spinner;
 * if the session is invalid it redirects to `/login`.
 */
"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Spinner } from "@/components/ui/spinner";
import { getMe } from "@/lib/api";
import { clearUser, setUser } from "@/store/authSlice";
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
  const status = useAppSelector((s) => s.auth.status);

  useEffect(() => {
    let cancelled = false;
    getMe()
      .then((user) => {
        if (!cancelled) dispatch(setUser(user));
      })
      .catch(() => {
        if (cancelled) return;
        dispatch(clearUser());
        router.replace("/login");
      });
    return () => {
      cancelled = true;
    };
  }, [dispatch, router]);

  if (status !== "authenticated") {
    return (
      <div className="flex h-dvh items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  return <>{children}</>;
}
