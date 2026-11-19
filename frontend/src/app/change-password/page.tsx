/** @module ChangePasswordPage — Where a user whose password an admin chose must replace it before anything else. */
"use client";

import { useRouter } from "next/navigation";
import { AuthCard } from "@/components/auth/auth-card";
import { ChangePasswordForm } from "@/components/auth/change-password-form";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n/provider";
import { logout } from "@/lib/api";
import { safeNextPath } from "@/lib/next-path";
import { clearUser } from "@/store/authSlice";
import { useAppDispatch } from "@/store/hooks";

/**
 * The page {@link import("@/components/auth/auth-provider").AuthProvider} holds a
 * user on while `mustChangePassword` is set. Once the password is changed it
 * goes on to the `?next=` page the user was headed for. Signing out instead
 * lands on `/signed-out`, as the user menu's does.
 */
export default function ChangePasswordPage() {
  const t = useT();
  const router = useRouter();
  const dispatch = useAppDispatch();

  async function onSignOut() {
    try {
      await logout();
    } catch {
      // Even if the request fails, drop local auth state and leave.
    }
    dispatch(clearUser());
    router.replace("/signed-out");
  }

  return (
    <AuthCard title={t("changePassword.title")}>
      <p className="text-sm text-on-surface-variant">{t("changePassword.required")}</p>
      <ChangePasswordForm
        fullWidthButton
        onDone={() =>
          router.replace(safeNextPath(new URLSearchParams(window.location.search).get("next")))
        }
      />
      <Button
        variant="ghost"
        className="w-full"
        onClick={onSignOut}
        data-testid="password-sign-out"
      >
        {t("app.logOut")}
      </Button>
    </AuthCard>
  );
}
