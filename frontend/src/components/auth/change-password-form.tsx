/** @module ChangePasswordForm — The current/new/confirm password form shared by the profile page and the forced-change page. */
"use client";

import { useState } from "react";
import { FormField } from "@/components/admin/form-field";
import { Button } from "@/components/ui/button";
import { PasswordInput } from "@/components/ui/password-input";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useT } from "@/i18n/provider";
import { changePassword } from "@/lib/api";
import { setUser } from "@/store/authSlice";
import { useAppDispatch } from "@/store/hooks";

const EMPTY_FORM = { current: "", next: "", confirm: "" };

/**
 * Lets the signed-in user replace their own password. On success the updated
 * user (with `mustChangePassword` cleared) goes into the auth slice, the fields
 * are emptied, and `onDone` runs. A backend refusal — a wrong current password,
 * the same password again — is toasted by api.ts like every other form's.
 *
 * @param props.onDone - Called after the password has been changed.
 * @param props.disabled - Disables every field and the button, e.g. while impersonating.
 * @param props.fullWidthButton - Stretches the button across the form, as in an
 *   {@link import("./auth-card").AuthCard}, whose other buttons are full width.
 */
export function ChangePasswordForm({
  onDone,
  disabled = false,
  fullWidthButton = false,
}: {
  onDone?: () => void;
  disabled?: boolean;
  fullWidthButton?: boolean;
}) {
  const t = useT();
  const dispatch = useAppDispatch();
  const [form, setForm] = useState(EMPTY_FORM);
  const [mismatch, setMismatch] = useState(false);
  const submit = useAsyncAction({ showDone: false });

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (form.next !== form.confirm) {
      setMismatch(true);
      return;
    }
    try {
      await submit.run(async () => {
        dispatch(setUser(await changePassword(form.current, form.next)));
      });
    } catch {
      return; // Toasted by api.ts.
    }
    setForm(EMPTY_FORM);
    onDone?.();
  }

  /** Bind one field to its `<input>`. */
  const field = (name: keyof typeof EMPTY_FORM) => ({
    id: `password-${name}`,
    value: form[name],
    required: true,
    disabled,
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => {
      setForm((f) => ({ ...f, [name]: e.target.value }));
      setMismatch(false);
    },
    "data-testid": `password-${name}`,
  });

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <FormField htmlFor="password-current" label={t("changePassword.current")} required>
        <PasswordInput {...field("current")} autoComplete="current-password" />
      </FormField>
      <FormField htmlFor="password-next" label={t("changePassword.new")} required>
        <PasswordInput
          {...field("next")}
          autoComplete="new-password"
          minLength={12}
          maxLength={72}
        />
        <p className="mt-1 text-xs text-on-surface-variant">{t("signup.passwordHint")}</p>
      </FormField>
      <FormField
        htmlFor="password-confirm"
        label={t("changePassword.confirm")}
        required
        error={mismatch ? "changePassword.mismatch" : undefined}
      >
        <PasswordInput {...field("confirm")} autoComplete="new-password" maxLength={72} />
      </FormField>
      <Button
        type="submit"
        variant="primary"
        disabled={disabled || submit.inFlight}
        status={submit.status}
        pendingLabel={t("changePassword.changing")}
        className={fullWidthButton ? "w-full" : "self-start"}
        data-testid="password-submit"
      >
        {t("changePassword.submit")}
      </Button>
    </form>
  );
}
