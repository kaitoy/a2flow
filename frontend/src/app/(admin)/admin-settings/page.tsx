/**
 * @module AdminSettingsPage — Admin page for the settings a tenant's own
 * `admin` manages: how failed sign-ins lock the tenant's accounts, the
 * tenant's own HashiCorp Vault, its OpenID Connect single sign-on and — only
 * while a super admin has handed it over — the tenant's LLM.
 */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Settings } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import {
  LlmSettingsFields,
  llmShape,
  refineTenantAdminLlm,
  toLlmBody,
  toLlmFormValues,
} from "@/components/admin/llm-settings-fields";
import {
  OidcSettingsFields,
  oidcShape,
  toOidcBody,
  toOidcFormValues,
} from "@/components/admin/oidc-settings-fields";
import {
  SignInLockoutFields,
  signInLockoutShape,
  toSignInLockoutBody,
  toSignInLockoutFormValues,
} from "@/components/admin/sign-in-lockout-fields";
import {
  refineVaultConnection,
  savedVaultMethod,
  toVaultConnectionBody,
  toVaultConnectionFormValues,
  VaultConnectionFields,
  vaultConnectionShape,
} from "@/components/admin/vault-connection-fields";
import { Button } from "@/components/ui/button";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useT } from "@/i18n/provider";
import {
  type AdminSettings,
  getAdminSettings,
  type LlmMode,
  SUPPRESS_FORBIDDEN_TOAST,
  updateAdminSettings,
  type VaultAuthMethod,
} from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/**
 * Build the validation schema. `savedMethod` is the auth method whose Vault
 * credential is stored, if any (see {@link refineVaultConnection}). `llm` is
 * whether the LLM fields are this admin's to set and whether a key is stored;
 * only then are they checked (see {@link refineTenantAdminLlm}).
 */
function buildSchema(
  savedMethod: VaultAuthMethod | null,
  llm: { editable: boolean; keySaved: boolean }
) {
  return z
    .object({ ...signInLockoutShape, ...vaultConnectionShape, ...oidcShape, ...llmShape })
    .superRefine((values, ctx) => {
      refineVaultConnection(values, ctx, savedMethod);
      if (llm.editable) refineTenantAdminLlm(values, ctx, llm.keySaved);
    });
}

type FormValues = z.infer<ReturnType<typeof buildSchema>>;

/** Convert the stored settings into form values. */
function toFormValues(settings: Partial<AdminSettings>): FormValues {
  return {
    ...toSignInLockoutFormValues(settings),
    ...toVaultConnectionFormValues(settings),
    ...toOidcFormValues(settings),
    ...toLlmFormValues(settings),
  };
}

/**
 * Settings of the acting tenant: how many failed sign-ins lock one of its
 * accounts and for how many minutes, and the HashiCorp Vault its Vault-type
 * secrets are read from (without one, the global Vault a super admin set up
 * is used). Reachable only by `admin` (and `super_admin`) — `layout.tsx`
 * blocks every other viewer before this page mounts.
 */
export default function AdminSettingsPage() {
  const t = useT();
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  // The auth method whose credential is stored, or null when none is. Drives
  // the credential placeholder and whether leaving it blank is acceptable.
  const [savedMethod, setSavedMethod] = useState<VaultAuthMethod | null>(null);
  // Whether an OIDC client secret is stored, and the callback URL the IdP must
  // allow (null while the deployment's base URL is unset). Both are read-only.
  const [secretSaved, setSecretSaved] = useState(false);
  const [redirectUri, setRedirectUri] = useState<string | null>(null);
  const [subdomainRedirectUri, setSubdomainRedirectUri] = useState<string | null>(null);
  // Whether a super admin has handed the tenant's LLM to its admin, and whether
  // a key is stored. Only in that mode are the LLM fields shown or sent.
  const [llmMode, setLlmMode] = useState<LlmMode>("system_default");
  const [llmKeySet, setLlmKeySet] = useState(false);
  const schema = useMemo(
    () => buildSchema(savedMethod, { editable: llmMode === "tenant_admin", keySaved: llmKeySet }),
    [savedMethod, llmMode, llmKeySet]
  );
  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    reset,
    watch,
    setValue,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: toFormValues({}),
  });

  useEffect(() => {
    getAdminSettings(SUPPRESS_FORBIDDEN_TOAST)
      .then((settings) => {
        setSavedMethod(savedVaultMethod(settings));
        setSecretSaved(settings.oidcClientSecretSet ?? false);
        setRedirectUri(settings.oidcRedirectUri ?? null);
        setSubdomainRedirectUri(settings.oidcSubdomainRedirectUri ?? null);
        setLlmMode(settings.llmMode ?? "system_default");
        setLlmKeySet(settings.llmApiKeySet ?? false);
        reset(toFormValues(settings));
      })
      .catch(() => setDenied(true))
      .finally(() => setLoading(false));
  }, [reset]);

  async function onSubmit(values: FormValues) {
    try {
      await save.run(async () => {
        const saved = await updateAdminSettings({
          ...toSignInLockoutBody(values),
          ...toVaultConnectionBody(values),
          ...toOidcBody(values),
          ...(llmMode === "tenant_admin" ? toLlmBody(values) : {}),
        });
        setSavedMethod(savedVaultMethod(saved));
        setSecretSaved(saved.oidcClientSecretSet ?? false);
        setRedirectUri(saved.oidcRedirectUri ?? null);
        setSubdomainRedirectUri(saved.oidcSubdomainRedirectUri ?? null);
        setLlmMode(saved.llmMode ?? "system_default");
        setLlmKeySet(saved.llmApiKeySet ?? false);
        reset(toFormValues(saved));
        dispatch(showToast({ message: t("adminSettings.adminSettingsUpdated") }));
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: t("common.home"), href: "/" },
    { label: t("common.adminSettings") },
  ];
  const header = <AdminPageHeader title={t("common.adminSettings")} icon={Settings} />;

  if (loading) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={header}>
          <FormSkeleton fields={8} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  if (denied) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={header}>
          <p className="rounded-2xl glass-panel-strong p-6 text-on-surface-variant">
            {t("adminSettings.theAdminSettingsCouldNotBeLoaded")}
          </p>
        </FormLayout>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout header={header}>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <SignInLockoutFields
            maxFailures={register("loginMaxFailures")}
            lockoutMinutes={register("loginLockoutMinutes")}
            errors={{
              loginMaxFailures: errors.loginMaxFailures?.message,
              loginLockoutMinutes: errors.loginLockoutMinutes?.message,
            }}
          />

          <hr className="border-outline-variant" />

          <VaultConnectionFields
            addr={register("vaultAddr")}
            roleId={register("vaultRoleId")}
            approleMount={register("vaultApproleMount")}
            credential={register("vaultCredential")}
            authMethod={watch("vaultAuthMethod")}
            onAuthMethodChange={(method) => setValue("vaultAuthMethod", method)}
            savedMethod={savedMethod}
            addrHint={t("adminSettings.theHashicorpVaultThisTenantsVaultType")}
            errors={{
              vaultAddr: errors.vaultAddr?.message,
              vaultRoleId: errors.vaultRoleId?.message,
              vaultApproleMount: errors.vaultApproleMount?.message,
              vaultCredential: errors.vaultCredential?.message,
            }}
          />

          <hr className="border-outline-variant" />

          <OidcSettingsFields
            enabled={register("oidcEnabled")}
            issuer={register("oidcIssuer")}
            clientId={register("oidcClientId")}
            clientSecret={register("oidcClientSecret")}
            groupsClaim={register("oidcGroupsClaim")}
            trustEmail={register("oidcTrustEmail")}
            secretSaved={secretSaved}
            redirectUri={redirectUri}
            subdomainRedirectUri={subdomainRedirectUri}
          />

          {llmMode === "tenant_admin" && (
            <>
              <hr className="border-outline-variant" />

              <LlmSettingsFields
                model={register("llmModel")}
                apiKey={register("llmApiKey")}
                apiKeySaved={llmKeySet}
                inherits
                keyRequired
                errors={{
                  llmModel: errors.llmModel?.message,
                  llmApiKey: errors.llmApiKey?.message,
                }}
              />
            </>
          )}

          <div className="flex gap-2">
            <Button
              type="submit"
              variant="primary"
              disabled={save.inFlight}
              status={save.status}
              pendingLabel={t("common.saving")}
            >
              {t("common.save")}
            </Button>
          </div>
        </form>
      </FormLayout>
    </AdminPageContainer>
  );
}
