/** @module SignupPage — The self-service sign-up form, which mails a confirmation link. */
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
import { getLoginOptions, signup } from "@/lib/api";

/** The form's fields, named as the sign-up request names them. */
const EMPTY_FORM = { email: "", username: "", firstName: "", lastName: "", password: "" };

/**
 * Public sign-up page. A visitor enters an email, a username, their name and a
 * password; the backend mails a confirmation link to that address, and the
 * page says so. Nothing is created until the link's page
 * at `/signup/verify` completes the sign-up.
 *
 * Only offered where the login options say so (`signup`: the deployment
 * offers sign-up and this is the main host, not a tenant subdomain);
 * anywhere else the page sends the visitor to `/login`.
 */
export default function SignupPage() {
  const t = useT();
  const router = useRouter();
  const [allowed, setAllowed] = useState(false);
  const [privacyPolicyUrl, setPrivacyPolicyUrl] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const submit = useAsyncAction({ showDone: false });

  useEffect(() => {
    let cancelled = false;
    getLoginOptions(window.location.hostname)
      .catch(() => ({ signup: false, privacyPolicyUrl: null }))
      .then(({ signup: offered = false, privacyPolicyUrl: policy = null }) => {
        if (cancelled) return;
        setPrivacyPolicyUrl(policy);
        if (offered) setAllowed(true);
        else router.replace("/login");
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  const onSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      try {
        await submit.run(async () => {
          await signup(form);
          setSentTo(form.email);
        });
      } catch {
        // Failure toast is shown globally by api.ts; nothing else to do here.
      }
    },
    [form, submit.run]
  );

  /** Bind one form field to its `<input>`. */
  const field = (name: keyof typeof EMPTY_FORM) => ({
    id: name,
    name,
    value: form[name],
    required: true,
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [name]: e.target.value })),
    "data-testid": `signup-${name}`,
  });

  if (sentTo !== null) {
    return (
      <AuthCard title={t("signup.checkEmailTitle")} privacyPolicyUrl={privacyPolicyUrl}>
        <p className="text-center text-sm text-on-surface-variant" data-testid="signup-sent">
          {t("signup.checkEmailMessage", { email: sentTo })}
        </p>
        <Button href="/login" variant="ghost" className="w-full">
          {t("signup.backToSignIn")}
        </Button>
      </AuthCard>
    );
  }

  return (
    <AuthCard title={t("signup.title")} onSubmit={onSubmit} privacyPolicyUrl={privacyPolicyUrl}>
      {allowed && (
        <>
          <FormField htmlFor="email" label={t("common.email")} required>
            <Input {...field("email")} type="email" autoComplete="email" autoFocus />
          </FormField>
          <FormField htmlFor="username" label={t("common.username")} required>
            <Input
              {...field("username")}
              autoComplete="username"
              minLength={3}
              maxLength={64}
              pattern="[a-zA-Z0-9._\-]+"
            />
            <p className="mt-1 text-xs text-on-surface-variant">{t("signup.usernameHint")}</p>
          </FormField>
          <FormField htmlFor="firstName" label={t("common.firstName")} required>
            <Input {...field("firstName")} autoComplete="given-name" maxLength={100} />
          </FormField>
          <FormField htmlFor="lastName" label={t("common.lastName")} required>
            <Input {...field("lastName")} autoComplete="family-name" maxLength={100} />
          </FormField>
          <FormField htmlFor="password" label={t("common.password")} required>
            <PasswordInput
              {...field("password")}
              autoComplete="new-password"
              minLength={12}
              maxLength={72}
            />
            <p className="mt-1 text-xs text-on-surface-variant">{t("signup.passwordHint")}</p>
          </FormField>
          <Button
            type="submit"
            variant="primary"
            disabled={submit.inFlight}
            status={submit.status}
            pendingLabel={t("signup.creatingAccount")}
            className="w-full"
            data-testid="signup-submit"
          >
            {t("signup.createAccount")}
          </Button>
          <Button href="/login" variant="ghost" className="w-full" data-testid="signup-sign-in">
            {t("signup.haveAccount")}
          </Button>
        </>
      )}
    </AuthCard>
  );
}
