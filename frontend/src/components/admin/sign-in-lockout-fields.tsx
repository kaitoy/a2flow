/**
 * @module SignInLockoutFields — Shared schema and field set for a tenant's
 * sign-in lockout, edited on both the Tenant Settings page (the tenant's own
 * admin) and the tenant detail page (super admins).
 */
"use client";

import type { UseFormRegisterReturn } from "react-hook-form";
import { z } from "zod";
import { FormField } from "@/components/admin/form-field";
import { Input } from "@/components/ui/input";
import { zTenantSettingsUpdate } from "@/generated/api/zod.gen";
import { useT } from "@/i18n/provider";

/**
 * A whole number typed into a text input, checked against a generated field
 * schema so the bounds stay the backend's.
 */
function wholeNumber(schema: z.ZodType, message: string) {
  return z
    .string()
    .refine((v) => /^\d+$/.test(v) && schema.safeParse(Number(v)).success, { message });
}

/**
 * Zod shape for the two lockout fields, held as strings in the form. Spread
 * into a page's schema with `.extend(signInLockoutShape)`.
 */
export const signInLockoutShape = {
  loginMaxFailures: wholeNumber(
    zTenantSettingsUpdate.shape.loginMaxFailures,
    "Enter a whole number from 1 to 100"
  ),
  loginLockoutMinutes: wholeNumber(
    zTenantSettingsUpdate.shape.loginLockoutMinutes,
    "Enter a whole number of minutes from 1 to 1440"
  ),
};

/** Form values for the lockout fields. */
export type SignInLockoutFormValues = {
  loginMaxFailures: string;
  loginLockoutMinutes: string;
};

/**
 * Convert stored settings into form values.
 *
 * @param settings - The tenant's stored limit and lockout minutes.
 * @returns The same values as strings for the inputs.
 */
export function toSignInLockoutFormValues(settings: {
  loginMaxFailures?: number;
  loginLockoutMinutes?: number;
}): SignInLockoutFormValues {
  return {
    loginMaxFailures: String(settings.loginMaxFailures ?? 5),
    loginLockoutMinutes: String(settings.loginLockoutMinutes ?? 15),
  };
}

/**
 * Convert form values into the request body fields.
 *
 * @param values - Validated form values.
 * @returns The limit and lockout minutes as numbers.
 */
export function toSignInLockoutBody(values: SignInLockoutFormValues): {
  loginMaxFailures: number;
  loginLockoutMinutes: number;
} {
  return {
    loginMaxFailures: Number(values.loginMaxFailures),
    loginLockoutMinutes: Number(values.loginLockoutMinutes),
  };
}

/** Props for {@link SignInLockoutFields}. */
export interface SignInLockoutFieldsProps {
  /** `register("loginMaxFailures")` from the page's `useForm`. */
  maxFailures: UseFormRegisterReturn;
  /** `register("loginLockoutMinutes")` from the page's `useForm`. */
  lockoutMinutes: UseFormRegisterReturn;
  /** Validation errors for the two fields, if any. */
  errors: { loginMaxFailures?: string; loginLockoutMinutes?: string };
}

/**
 * How many failed sign-ins lock one of the tenant's accounts, and for how long.
 * Failures are counted over the same number of minutes the lock lasts.
 */
export function SignInLockoutFields({
  maxFailures,
  lockoutMinutes,
  errors,
}: SignInLockoutFieldsProps) {
  const t = useT();
  return (
    <>
      <FormField
        htmlFor="loginMaxFailures"
        label={t("admin.failedSignInsBeforeLockout")}
        required
        error={errors.loginMaxFailures}
      >
        <Input id="loginMaxFailures" inputMode="numeric" {...maxFailures} />
      </FormField>
      <FormField
        htmlFor="loginLockoutMinutes"
        label={t("admin.lockoutMinutes")}
        required
        error={errors.loginLockoutMinutes}
      >
        <Input id="loginLockoutMinutes" inputMode="numeric" {...lockoutMinutes} />
        <p className="text-xs text-on-surface-variant">
          {t("admin.failuresAreCountedOverThisManyMinutes")}
        </p>
      </FormField>
    </>
  );
}
