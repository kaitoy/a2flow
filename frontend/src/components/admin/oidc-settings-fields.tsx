/**
 * @module OidcSettingsFields — Shared schema helpers and field set for a
 * tenant's OpenID Connect single sign-on, edited on the Tenant Settings page.
 */
"use client";

import type { UseFormRegisterReturn } from "react-hook-form";
import { z } from "zod";
import { FormField } from "@/components/admin/form-field";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { useT } from "@/i18n/provider";
import type { TenantSettings, TenantSettingsUpdate } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/**
 * Zod shape for the SSO fields, held as plain strings and booleans in the
 * form. Spread into a page's schema; the backend checks the cross-field
 * enable rule when the settings are saved.
 */
export const oidcShape = {
  oidcEnabled: z.boolean(),
  oidcIssuer: z.string(),
  oidcClientId: z.string(),
  oidcClientSecret: z.string(),
  oidcGroupsClaim: z.string(),
  oidcTrustEmail: z.boolean(),
};

/** Form values for the SSO fields. */
export type OidcFormValues = z.infer<z.ZodObject<typeof oidcShape>>;

/**
 * Convert stored settings into form values. The client secret field always
 * starts blank, since the secret is write-only.
 *
 * @param settings - The stored settings.
 * @returns The form values.
 */
export function toOidcFormValues(settings: Partial<TenantSettings>): OidcFormValues {
  return {
    oidcEnabled: settings.oidcEnabled ?? false,
    oidcIssuer: settings.oidcIssuer ?? "",
    oidcClientId: settings.oidcClientId ?? "",
    oidcClientSecret: "",
    oidcGroupsClaim: settings.oidcGroupsClaim ?? "groups",
    oidcTrustEmail: settings.oidcTrustEmail ?? false,
  };
}

/**
 * Convert form values into the request body fields. A blank client secret and
 * a blank groups claim are omitted so the backend keeps what it holds; a blank
 * issuer or client id clears the stored one.
 *
 * @param values - The form values.
 * @returns The SSO fields of the body.
 */
export function toOidcBody(values: OidcFormValues): TenantSettingsUpdate {
  const body: TenantSettingsUpdate = {
    oidcEnabled: values.oidcEnabled,
    oidcIssuer: values.oidcIssuer.trim() || null,
    oidcClientId: values.oidcClientId.trim() || null,
    oidcTrustEmail: values.oidcTrustEmail,
  };
  if (values.oidcClientSecret !== "") body.oidcClientSecret = values.oidcClientSecret;
  if (values.oidcGroupsClaim.trim() !== "") body.oidcGroupsClaim = values.oidcGroupsClaim.trim();
  return body;
}

/** Props for {@link OidcSettingsFields}. */
export interface OidcSettingsFieldsProps {
  /** `register("oidcEnabled")` from the page's `useForm`. */
  enabled: UseFormRegisterReturn;
  /** `register("oidcIssuer")` from the page's `useForm`. */
  issuer: UseFormRegisterReturn;
  /** `register("oidcClientId")` from the page's `useForm`. */
  clientId: UseFormRegisterReturn;
  /** `register("oidcClientSecret")` from the page's `useForm`. */
  clientSecret: UseFormRegisterReturn;
  /** `register("oidcGroupsClaim")` from the page's `useForm`. */
  groupsClaim: UseFormRegisterReturn;
  /** `register("oidcTrustEmail")` from the page's `useForm`. */
  trustEmail: UseFormRegisterReturn;
  /** Whether a client secret is already stored. */
  secretSaved: boolean;
  /** The callback URL to register at the IdP, or `null` while the deployment's base URL is unset. */
  redirectUri: string | null;
}

/**
 * The SSO enable switch, issuer, client id, write-only client secret, groups
 * claim, the trust-e-mail switch, and the read-only redirect URI with a copy
 * button (or a warning while the deployment's base URL is not set).
 */
export function OidcSettingsFields({
  enabled,
  issuer,
  clientId,
  clientSecret,
  groupsClaim,
  trustEmail,
  secretSaved,
  redirectUri,
}: OidcSettingsFieldsProps) {
  const t = useT();
  const dispatch = useAppDispatch();

  async function copyRedirectUri() {
    if (redirectUri === null) return;
    try {
      await navigator.clipboard.writeText(redirectUri);
      dispatch(showToast({ message: t("tenantSettings.oidc.copied") }));
    } catch {
      // Clipboard access can be refused; the URI is on screen to select by hand.
    }
  }

  return (
    <>
      <h2 className="font-display text-lg font-semibold tracking-tight text-on-surface">
        {t("tenantSettings.oidc.title")}
      </h2>

      <Checkbox label={t("tenantSettings.oidc.enable")} {...enabled} />

      <FormField htmlFor="oidcIssuer" label={t("tenantSettings.oidc.issuerUrl")}>
        <Input id="oidcIssuer" placeholder="https://idp.example.com" {...issuer} />
        <p className="text-xs text-on-surface-variant">{t("tenantSettings.oidc.issuerUrlHint")}</p>
      </FormField>

      <FormField htmlFor="oidcClientId" label={t("tenantSettings.oidc.clientId")}>
        <Input id="oidcClientId" autoComplete="off" {...clientId} />
      </FormField>

      <FormField htmlFor="oidcClientSecret" label={t("tenantSettings.oidc.clientSecret")}>
        <PasswordInput
          id="oidcClientSecret"
          autoComplete="new-password"
          placeholder={secretSaved ? t("common.savedLeaveEmptyToKeepIt") : ""}
          {...clientSecret}
        />
      </FormField>

      <FormField htmlFor="oidcGroupsClaim" label={t("tenantSettings.oidc.groupsClaim")}>
        <Input id="oidcGroupsClaim" {...groupsClaim} />
        <p className="text-xs text-on-surface-variant">
          {t("tenantSettings.oidc.groupsClaimHint")}
        </p>
      </FormField>

      <div className="flex flex-col gap-1">
        <Checkbox label={t("tenantSettings.oidc.trustEmail")} {...trustEmail} />
        <p className="px-3 text-xs text-on-surface-variant">
          {t("tenantSettings.oidc.trustEmailHint")}
        </p>
      </div>

      <FormField htmlFor="oidcRedirectUri" label={t("tenantSettings.oidc.redirectUri")}>
        {redirectUri === null ? (
          <p className="text-sm text-error">{t("tenantSettings.oidc.baseUrlMissing")}</p>
        ) : (
          <>
            <div className="flex items-start gap-2">
              <ReadOnlyField className="min-w-0 flex-1">{redirectUri}</ReadOnlyField>
              <Button type="button" variant="secondary" onClick={copyRedirectUri}>
                {t("tenantSettings.oidc.copy")}
              </Button>
            </div>
            <p className="text-xs text-on-surface-variant">
              {t("tenantSettings.oidc.redirectUriHint")}
            </p>
          </>
        )}
      </FormField>
    </>
  );
}
