/** @module LoginPage — Username/password sign-in that establishes the session cookie. */
"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import logo from "@/../assets/logo.png";
import { FormField } from "@/components/admin/form-field";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useT } from "@/i18n/provider";
import { API_BASE, login } from "@/lib/api";
import { persistImpersonatedUserId } from "@/lib/impersonation";
import { clearImpersonation, setUser } from "@/store/authSlice";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/** The failure codes the backend puts in `/login?sso_error=`. */
const SSO_ERRORS = ["unavailable", "failed", "account_disabled", "not_permitted"] as const;

/**
 * Public sign-in page. On success the backend sets the session and CSRF cookies,
 * the current user is stored in the auth slice, and the user is sent to the
 * welcome page at `/`. The SSO button hands the typed tenant to the backend's
 * OpenID Connect sign-in; when that fails the backend returns here with an
 * `sso_error` code, shown as a toast.
 */
export default function LoginPage() {
  const t = useT();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [username, setUsername] = useState("");
  const [tenantName, setTenantName] = useState("");
  const [password, setPassword] = useState("");
  // No `done` stage: a successful sign-in navigates away immediately, so the
  // success color/checkmark/wiggle would only flash before the page unmounts.
  const signIn = useAsyncAction({ showDone: false });

  // Read from `window` rather than `useSearchParams`, which would force a
  // Suspense boundary around the whole form.
  useEffect(() => {
    const raw = new URLSearchParams(window.location.search).get("sso_error");
    if (raw === null) return;
    const code = SSO_ERRORS.find((c) => c === raw) ?? "failed";
    dispatch(showToast({ message: t(`login.ssoError.${code}`), variant: "error" }));
    router.replace("/login");
  }, [dispatch, router, t]);

  const onSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      try {
        await signIn.run(async () => {
          const user = await login(username, password, tenantName.trim() || undefined);
          dispatch(setUser(user));
          // A fresh login must never inherit a previous session's impersonation
          // selection lingering in localStorage.
          dispatch(clearImpersonation());
          persistImpersonatedUserId(null);
          router.replace("/");
        });
      } catch {
        // Failure toast is shown globally by api.ts; nothing else to do here.
      }
    },
    [username, tenantName, password, dispatch, router, signIn.run]
  );

  return (
    <main className="relative flex min-h-dvh items-center justify-center px-4">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>
      <form
        onSubmit={onSubmit}
        className="glass-panel flex w-full max-w-sm flex-col gap-5 rounded-2xl p-8"
      >
        <div className="flex flex-col items-center gap-3">
          <Image
            src={logo}
            alt={t("common.a2flowLogo")}
            width={logo.width}
            height={logo.height}
            className="h-12 w-auto"
            priority
          />
          <h1 className="font-display text-2xl font-semibold tracking-tight text-on-surface">
            {t("login.signInToA2flow")}
          </h1>
        </div>

        <FormField htmlFor="username" label={t("common.username")} required>
          <Input
            id="username"
            data-testid="login-username"
            name="username"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoFocus
          />
        </FormField>

        <FormField htmlFor="tenantName" label={t("common.tenant")}>
          <Input
            id="tenantName"
            data-testid="login-tenant"
            name="tenantName"
            autoComplete="organization"
            value={tenantName}
            onChange={(e) => setTenantName(e.target.value)}
            placeholder={t("login.eGAcmeCorp")}
          />
          <p className="mt-1 text-xs text-on-surface-variant">
            {t("login.leaveBlankIfYouSignInAs")}
          </p>
        </FormField>

        <FormField htmlFor="password" label={t("common.password")} required>
          <PasswordInput
            id="password"
            data-testid="login-password"
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </FormField>

        <Button
          type="submit"
          variant="primary"
          disabled={signIn.inFlight}
          status={signIn.status}
          pendingLabel={t("login.signingIn")}
          className="w-full"
          data-testid="login-submit"
        >
          {t("login.signIn")}
        </Button>

        <Button
          type="button"
          variant="secondary"
          disabled={tenantName.trim() === ""}
          className="w-full"
          data-testid="login-sso"
          onClick={() =>
            window.location.assign(
              `${API_BASE}/api/v1/auth/oidc/start?tenant=${encodeURIComponent(tenantName.trim())}`
            )
          }
        >
          {t("login.signInWithSso")}
        </Button>
      </form>
    </main>
  );
}
