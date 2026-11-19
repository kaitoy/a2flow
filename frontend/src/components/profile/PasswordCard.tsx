/** @module PasswordCard — The profile card where a user changes their own password. */
"use client";

import { KeyRound } from "lucide-react";
import { ChangePasswordForm } from "@/components/auth/change-password-form";
import { SectionCard } from "@/components/ui/section-card";
import { useT } from "@/i18n/provider";
import type { User } from "@/lib/api";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/**
 * Lets the signed-in user change their password. Renders nothing for an
 * SSO-only account, which has no password, and is disabled while
 * impersonating: the backend refuses it, since the password is not the
 * impersonator's to change.
 *
 * @param props.user - The user shown on the profile page.
 */
export function PasswordCard({ user }: { user: User }) {
  const t = useT();
  const dispatch = useAppDispatch();
  const impersonating = useAppSelector((s) => s.auth.impersonatedBy !== null);

  if (!user.hasPassword) return null;

  return (
    <SectionCard icon={KeyRound} title={t("common.password")}>
      <ChangePasswordForm
        disabled={impersonating}
        onDone={() => dispatch(showToast({ message: t("profile.password.changed") }))}
      />
      {impersonating && (
        <p className="mt-1.5 text-xs text-on-surface-variant">
          {t("profile.password.impersonating")}
        </p>
      )}
    </SectionCard>
  );
}
