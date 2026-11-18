/** @module SignupVerifyPage — Finishes a sign-up from the link in its confirmation email. */
"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthCard } from "@/components/auth/auth-card";
import { Button } from "@/components/ui/button";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useT } from "@/i18n/provider";
import { completeSignup, type SignupResult } from "@/lib/api";
import { persistImpersonatedUserId } from "@/lib/impersonation";
import { clearImpersonation, setUser } from "@/store/authSlice";
import { useAppDispatch } from "@/store/hooks";

/**
 * Where the sign-up confirmation email's link lands: `/signup/verify#<token>`.
 * The token rides in the fragment, which the browser never sends to a server.
 *
 * Opening the page creates nothing. The visitor chooses **Complete sign-up**,
 * so a mail scanner that opens links on its own cannot complete it for them.
 * The backend then creates the tenant, makes the visitor its admin and signs
 * them in, and the page shows the tenant name and username they sign in with
 * from now on, then continues to the welcome page at `/`. A link with no token
 * says so and offers the sign-up form again; an expired or used one gets the
 * backend's error as a toast.
 */
export default function SignupVerifyPage() {
  const t = useT();
  const router = useRouter();
  const dispatch = useAppDispatch();
  // `undefined` until read from the URL after mount; "" when the link has none.
  const [token, setToken] = useState<string>();
  const [result, setResult] = useState<SignupResult | null>(null);
  const complete = useAsyncAction({ showDone: false });

  useEffect(() => {
    setToken(window.location.hash.slice(1));
  }, []);

  const onComplete = async () => {
    try {
      await complete.run(async () => {
        const created = await completeSignup(token ?? "");
        dispatch(setUser(created.user));
        // A fresh session must never inherit a previous one's impersonation
        // selection lingering in localStorage.
        dispatch(clearImpersonation());
        persistImpersonatedUserId(null);
        setResult(created);
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  };

  if (result !== null) {
    return (
      <AuthCard title={t("signup.doneTitle")}>
        <p className="text-center text-sm text-on-surface-variant">{t("signup.doneMessage")}</p>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="text-on-surface-variant">{t("common.tenant")}</dt>
          <dd className="font-mono text-on-surface" data-testid="signup-tenant-name">
            {result.tenantName}
          </dd>
          <dt className="text-on-surface-variant">{t("common.username")}</dt>
          <dd className="font-mono text-on-surface">{result.user.username}</dd>
          {result.tenantUrl && (
            <>
              <dt className="text-on-surface-variant">{t("signup.tenantAddress")}</dt>
              <dd className="break-all font-mono text-on-surface">{result.tenantUrl}</dd>
            </>
          )}
        </dl>
        <Button
          type="button"
          variant="primary"
          className="w-full"
          data-testid="signup-continue"
          onClick={() => router.replace("/")}
        >
          {t("signup.continue")}
        </Button>
      </AuthCard>
    );
  }

  return (
    <AuthCard title={t("signup.verifyTitle")}>
      {token === "" ? (
        <>
          <p className="text-center text-sm text-on-surface-variant" data-testid="signup-no-token">
            {t("signup.linkIncomplete")}
          </p>
          <Button href="/signup" variant="primary" className="w-full">
            {t("signup.signUpAgain")}
          </Button>
        </>
      ) : (
        token !== undefined && (
          <>
            <p className="text-center text-sm text-on-surface-variant">
              {t("signup.verifyMessage")}
            </p>
            <Button
              type="button"
              variant="primary"
              disabled={complete.inFlight}
              status={complete.status}
              pendingLabel={t("signup.completingSignup")}
              className="w-full"
              data-testid="signup-complete"
              onClick={onComplete}
            >
              {t("signup.completeSignup")}
            </Button>
          </>
        )
      )}
    </AuthCard>
  );
}
