/**
 * @module TenantSettingsPage — Admin page for the settings a tenant's own
 * `admin` manages: how failed sign-ins lock the tenant's accounts, and the
 * tenant's own HashiCorp Vault.
 */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
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
  getTenantSettings,
  SUPPRESS_FORBIDDEN_TOAST,
  type TenantSettings,
  updateTenantSettings,
  type VaultAuthMethod,
} from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/**
 * Build the validation schema. `savedMethod` is the auth method whose Vault
 * credential is stored, if any (see {@link refineVaultConnection}).
 */
function buildSchema(savedMethod: VaultAuthMethod | null) {
  return z
    .object({ ...signInLockoutShape, ...vaultConnectionShape })
    .superRefine((values, ctx) => refineVaultConnection(values, ctx, savedMethod));
}

type FormValues = z.infer<ReturnType<typeof buildSchema>>;

/** Convert the stored settings into form values. */
function toFormValues(settings: Partial<TenantSettings>): FormValues {
  return { ...toSignInLockoutFormValues(settings), ...toVaultConnectionFormValues(settings) };
}

/**
 * Settings of the acting tenant: how many failed sign-ins lock one of its
 * accounts and for how many minutes, and the HashiCorp Vault its Vault-type
 * secrets are read from (without one, the global Vault a super admin set up
 * is used). Reachable only by `admin` (and `super_admin`) — `layout.tsx`
 * blocks every other viewer before this page mounts.
 */
export default function TenantSettingsPage() {
  const t = useT();
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  // The auth method whose credential is stored, or null when none is. Drives
  // the credential placeholder and whether leaving it blank is acceptable.
  const [savedMethod, setSavedMethod] = useState<VaultAuthMethod | null>(null);
  const schema = useMemo(() => buildSchema(savedMethod), [savedMethod]);
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
    getTenantSettings(SUPPRESS_FORBIDDEN_TOAST)
      .then((settings) => {
        setSavedMethod(savedVaultMethod(settings));
        reset(toFormValues(settings));
      })
      .catch(() => setDenied(true))
      .finally(() => setLoading(false));
  }, [reset]);

  async function onSubmit(values: FormValues) {
    try {
      await save.run(async () => {
        const saved = await updateTenantSettings({
          ...toSignInLockoutBody(values),
          ...toVaultConnectionBody(values),
        });
        setSavedMethod(savedVaultMethod(saved));
        reset(toFormValues(saved));
        dispatch(showToast({ message: t("tenantSettings.tenantSettingsUpdated") }));
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: t("common.home"), href: "/" },
    { label: t("common.tenantSettings") },
  ];
  const header = <AdminPageHeader title={t("common.tenantSettings")} icon={ShieldCheck} />;

  if (loading) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={header}>
          <FormSkeleton fields={5} />
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
            {t("tenantSettings.theTenantSettingsCouldNotBeLoaded")}
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
            addrHint={t("tenantSettings.theHashicorpVaultThisTenantsVaultType")}
            errors={{
              vaultAddr: errors.vaultAddr?.message,
              vaultRoleId: errors.vaultRoleId?.message,
              vaultApproleMount: errors.vaultApproleMount?.message,
              vaultCredential: errors.vaultCredential?.message,
            }}
          />

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
