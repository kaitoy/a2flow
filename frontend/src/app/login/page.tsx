/** @module LoginPage — Password and SSO sign-in that establishes the session cookie. */
"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { FormField } from "@/components/admin/form-field";
import { AuthCard } from "@/components/auth/auth-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useT } from "@/i18n/provider";
import { API_BASE, getLoginOptions, login } from "@/lib/api";
import { persistImpersonatedUserId } from "@/lib/impersonation";
import { loginPath, safeNextPath } from "@/lib/next-path";
import { clearImpersonation, setUser } from "@/store/authSlice";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/** The failure codes the backend puts in `/login?sso_error=`. */
const SSO_ERRORS = ["unavailable", "failed", "account_disabled", "not_permitted"] as const;

/** What the page shows at this host, from `getLoginOptions`. */
interface HostOptions {
  /** The tenant a tenant subdomain signs in to; `null` on the main host. */
  tenantName: string | null;
  /** Whether that tenant signs in through its identity provider. */
  sso: boolean;
  /** Set while the browser is on its way to the identity provider. */
  redirecting: boolean;
}

/**
 * Send the browser to the backend's OpenID Connect sign-in for `tenant`. On a
 * tenant's own subdomain the sign-in is asked to end there too, so the session
 * lands on the host the visitor is on; either way it returns to `next`.
 */
function startSso(tenant: string, onSubdomain: boolean, next: string) {
  const query = new URLSearchParams({ tenant });
  if (onSubdomain) query.set("subdomain", "true");
  if (next !== "/") query.set("next", next);
  window.location.assign(`${API_BASE}/api/v1/auth/oidc/start?${query}`);
}

/**
 * Public sign-in page. On success the backend sets the session and CSRF cookies,
 * the current user is stored in the auth slice, and the user is sent back to
 * the page that sent them here (`?next`, see {@link loginPath}) or to the
 * welcome page at `/`. The SSO button hands the tenant to the backend's OpenID
 * Connect sign-in; when that fails the backend returns here with an `sso_error`
 * code, shown as a toast.
 *
 * On a tenant subdomain the tenant is fixed and its field is hidden. A tenant
 * with SSO goes straight to its identity provider, unless SSO just failed
 * (`?sso_error`): then the page offers the SSO button, with the password fields
 * behind a link. `?local` stays too, with the password fields already open,
 * for an account that has only a password. A tenant without SSO shows only the
 * password fields. Signing out lands on `/signed-out`, not here, so it never
 * bounces off the identity provider's own session straight back in.
 */
export default function LoginPage() {
  const t = useT();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [username, setUsername] = useState("");
  const [tenantName, setTenantName] = useState("");
  const [password, setPassword] = useState("");
  const [options, setOptions] = useState<HostOptions | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [nextPath, setNextPath] = useState("/");
  // No `done` stage: a successful sign-in navigates away immediately, so the
  // success color/checkmark/wiggle would only flash before the page unmounts.
  const signIn = useAsyncAction({ showDone: false });

  // Runs once, and before the effect below strips `sso_error` from the URL: a
  // re-run without it would send a visitor whose SSO just failed straight back.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const passwordAsked = params.has("local");
    const stay = params.has("sso_error") || passwordAsked;
    const next = safeNextPath(params.get("next"));
    setShowPassword(passwordAsked);
    setNextPath(next);
    let cancelled = false;
    getLoginOptions(window.location.hostname)
      .catch(() => ({ tenantName: null, sso: false }))
      .then(({ tenantName = null, sso = false }) => {
        if (cancelled) return;
        const redirecting = tenantName !== null && sso && !stay;
        setOptions({ tenantName, sso, redirecting });
        if (redirecting) startSso(tenantName, true, next);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Read from `window` rather than `useSearchParams`, which would force a
  // Suspense boundary around the whole form.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const raw = params.get("sso_error");
    if (raw === null) return;
    const code = SSO_ERRORS.find((c) => c === raw) ?? "failed";
    dispatch(showToast({ message: t(`login.ssoError.${code}`), variant: "error" }));
    router.replace(loginPath(params.get("next") ?? "/"));
  }, [dispatch, router, t]);

  const fixedTenant = options?.tenantName ?? null;
  const tenant = fixedTenant ?? tenantName.trim();
  const passwordVisible = fixedTenant === null || !options?.sso || showPassword;

  const onSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      try {
        await signIn.run(async () => {
          const user = await login(username, password, tenant || undefined);
          dispatch(setUser(user));
          // A fresh login must never inherit a previous session's impersonation
          // selection lingering in localStorage.
          dispatch(clearImpersonation());
          persistImpersonatedUserId(null);
          router.replace(nextPath);
        });
      } catch {
        // Failure toast is shown globally by api.ts; nothing else to do here.
      }
    },
    [username, tenant, password, nextPath, dispatch, router, signIn.run]
  );

  return (
    <AuthCard title={t("login.signInToA2flow")} onSubmit={onSubmit}>
      {options === null ? null : options.redirecting ? (
        <p className="text-center text-sm text-on-surface-variant" role="status">
          {t("login.redirectingToSso")}
        </p>
      ) : (
        <>
          {passwordVisible && (
            <>
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

              {fixedTenant === null && (
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
              )}

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
            </>
          )}

          {(fixedTenant === null || options.sso) && (
            <Button
              type="button"
              variant={passwordVisible ? "secondary" : "primary"}
              disabled={tenant === ""}
              className="w-full"
              data-testid="login-sso"
              onClick={() => startSso(tenant, fixedTenant !== null, nextPath)}
            >
              {t("login.signInWithSso")}
            </Button>
          )}

          {!passwordVisible && (
            <Button
              type="button"
              variant="ghost"
              className="w-full"
              data-testid="login-show-password"
              onClick={() => setShowPassword(true)}
            >
              {t("login.signInWithPassword")}
            </Button>
          )}
        </>
      )}
    </AuthCard>
  );
}
