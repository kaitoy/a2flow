/** @module SignedOutPage — Confirms a sign-out and links back to the sign-in page. */
"use client";

import { AuthCard } from "@/components/auth/auth-card";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n/provider";

/**
 * Where the user menu lands after signing out. It exists so that signing out
 * never opens the sign-in page directly: on a tenant subdomain with SSO that
 * page goes straight to the identity provider, whose own session would sign
 * the browser back in. Here, going back is the visitor's choice.
 */
export default function SignedOutPage() {
  const t = useT();
  return (
    <AuthCard title={t("signedOut.title")}>
      <p className="text-center text-sm text-on-surface-variant">{t("signedOut.message")}</p>
      <Button href="/login" variant="primary" className="w-full" data-testid="signed-out-sign-in">
        {t("signedOut.signInAgain")}
      </Button>
    </AuthCard>
  );
}
