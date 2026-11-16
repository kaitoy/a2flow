/**
 * @module OidcSettingsFields — Shared schema helpers and field set for a
 * tenant's OpenID Connect single sign-on, edited on the Admin Settings page.
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
import type { AdminSettings, AdminSettingsUpdate } from "@/lib/api";
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
export function toOidcFormValues(settings: Partial<AdminSettings>): OidcFormValues {
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
export function toOidcBody(values: OidcFormValues): AdminSettingsUpdate {
  const body: AdminSettingsUpdate = {
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
  /**
   * The callback URL for sign-ins started at the tenant's own address, or
   * `null` when the deployment has no such address (no base URL, or one on an
   * IP address).
   */
  subdomainRedirectUri?: string | null;
}

/**
 * The SSO enable switch, issuer, client id, write-only client secret, groups
 * claim, the trust-e-mail switch, and the read-only redirect URIs -- the
 * deployment's and the tenant's own address's -- each with a copy button (or a
 * warning while the deployment's base URL is not set).
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
  subdomainRedirectUri = null,
}: OidcSettingsFieldsProps) {
  const t = useT();

  return (
    <>
      <h2 className="font-display text-lg font-semibold tracking-tight text-on-surface">
        {t("adminSettings.oidc.title")}
      </h2>

      <Checkbox label={t("adminSettings.oidc.enable")} {...enabled} />

      <FormField htmlFor="oidcIssuer" label={t("adminSettings.oidc.issuerUrl")}>
        <Input
          id="oidcIssuer"
          placeholder={t("common.exampleValue", { value: "https://idp.example.com" })}
          {...issuer}
        />
        <p className="text-xs text-on-surface-variant">{t("adminSettings.oidc.issuerUrlHint")}</p>
      </FormField>

      <FormField htmlFor="oidcClientId" label={t("adminSettings.oidc.clientId")}>
        <Input id="oidcClientId" autoComplete="off" {...clientId} />
      </FormField>

      <FormField htmlFor="oidcClientSecret" label={t("adminSettings.oidc.clientSecret")}>
        <PasswordInput
          id="oidcClientSecret"
          autoComplete="new-password"
          placeholder={secretSaved ? t("common.savedLeaveEmptyToKeepIt") : ""}
          {...clientSecret}
        />
      </FormField>

      <FormField htmlFor="oidcGroupsClaim" label={t("adminSettings.oidc.groupsClaim")}>
        <Input id="oidcGroupsClaim" {...groupsClaim} />
        <p className="text-xs text-on-surface-variant">{t("adminSettings.oidc.groupsClaimHint")}</p>
      </FormField>

      <div className="flex flex-col gap-1">
        <Checkbox label={t("adminSettings.oidc.trustEmail")} {...trustEmail} />
        <p className="px-3 text-xs text-on-surface-variant">
          {t("adminSettings.oidc.trustEmailHint")}
        </p>
      </div>

      {redirectUri === null ? (
        <FormField htmlFor="oidcRedirectUri" label={t("adminSettings.oidc.redirectUri")}>
          <p className="text-sm text-error">{t("adminSettings.oidc.baseUrlMissing")}</p>
        </FormField>
      ) : (
        <RedirectUriField
          id="oidcRedirectUri"
          label={t("adminSettings.oidc.redirectUri")}
          hint={t("adminSettings.oidc.redirectUriHint")}
          uri={redirectUri}
        />
      )}
      {redirectUri !== null && subdomainRedirectUri !== null && (
        <RedirectUriField
          id="oidcSubdomainRedirectUri"
          label={t("adminSettings.oidc.subdomainRedirectUri")}
          hint={t("adminSettings.oidc.subdomainRedirectUriHint")}
          uri={subdomainRedirectUri}
        />
      )}
    </>
  );
}

/** One read-only callback URL with a button copying it to the clipboard. */
function RedirectUriField({
  id,
  label,
  hint,
  uri,
}: {
  id: string;
  label: string;
  hint: string;
  uri: string;
}) {
  const t = useT();
  const dispatch = useAppDispatch();

  async function copy() {
    try {
      await navigator.clipboard.writeText(uri);
      dispatch(showToast({ message: t("adminSettings.oidc.copied") }));
    } catch {
      // Clipboard access can be refused; the URI is on screen to select by hand.
    }
  }

  return (
    <FormField htmlFor={id} label={label}>
      <div className="flex items-start gap-2">
        <ReadOnlyField className="min-w-0 flex-1">{uri}</ReadOnlyField>
        <Button type="button" variant="secondary" onClick={copy}>
          {t("adminSettings.oidc.copy")}
        </Button>
      </div>
      <p className="text-xs text-on-surface-variant">{hint}</p>
    </FormField>
  );
}
