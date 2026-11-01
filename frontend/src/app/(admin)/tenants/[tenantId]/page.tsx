/** @module TenantDetailPage — Admin detail page for an existing tenant. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Building2 } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormField } from "@/components/admin/form-field";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import {
  SignInLockoutFields,
  signInLockoutShape,
  toSignInLockoutBody,
  toSignInLockoutFormValues,
} from "@/components/admin/sign-in-lockout-fields";
import {
  refineVaultCredential,
  savedVaultMethod,
  VaultConnectionFields,
  vaultCredentialShape,
} from "@/components/admin/vault-connection-fields";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { zTenantCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import {
  deleteTenant,
  getTenant,
  type Tenant,
  type TenantUpdate,
  updateTenant,
  type VaultAuthMethod,
} from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";
import { useAppDispatch } from "@/store/hooks";
import { tenantsChanged } from "@/store/tenantsSlice";
import { showToast } from "@/store/toastSlice";

/**
 * Build the validation schema. `name` is immutable after creation, so it is
 * kept out of the form and rendered as a read-only field instead. The tenant's
 * own Vault connection is a tenant setting, edited on the Tenant Settings page;
 * its credential for the global Vault is edited here.
 *
 * @param savedMethod - The auth method whose global Vault credential is
 *   stored, if any (the credential itself never reaches the client).
 */
function buildSchema(savedMethod: VaultAuthMethod | null) {
  return zTenantCreate
    .pick({ displayName: true, enabled: true })
    .extend(signInLockoutShape)
    .extend({ globalVaultEnabled: z.boolean(), ...vaultCredentialShape })
    .superRefine((values, ctx) => {
      if (values.globalVaultEnabled) refineVaultCredential(values, ctx, savedMethod);
    });
}

type FormValues = z.infer<ReturnType<typeof buildSchema>>;

/** The stored global Vault credential, in the shape the shared helpers take. */
function storedGlobalVault(tenant: Partial<Tenant>) {
  return {
    vaultAuthMethod: tenant.globalVaultAuthMethod,
    vaultCredentialSet: tenant.globalVaultCredentialSet,
  };
}

/** Convert a tenant into form values. The credential field always starts blank. */
function toFormValues(tenant: Partial<Tenant>): FormValues {
  return {
    displayName: tenant.displayName ?? "",
    enabled: tenant.enabled ?? true,
    ...toSignInLockoutFormValues(tenant),
    globalVaultEnabled: Boolean(tenant.globalVaultCredentialSet || tenant.globalVaultAuthMethod),
    vaultAuthMethod: tenant.globalVaultAuthMethod ?? "token",
    vaultRoleId: tenant.globalVaultRoleId ?? "",
    vaultApproleMount: tenant.globalVaultApproleMount ?? "",
    vaultCredential: "",
  };
}

/**
 * Build the PATCH body. Unticking the global Vault clears the whole
 * credential; otherwise an untouched credential field is omitted so the
 * backend keeps the ciphertext it holds.
 */
function toBody(values: FormValues): TenantUpdate {
  const approle = values.vaultAuthMethod === "approle";
  const body: TenantUpdate = {
    displayName: values.displayName,
    enabled: values.enabled,
    ...toSignInLockoutBody(values),
    globalVaultAuthMethod: values.globalVaultEnabled ? values.vaultAuthMethod : null,
    globalVaultRoleId: values.globalVaultEnabled && approle ? values.vaultRoleId : null,
    globalVaultApproleMount:
      values.globalVaultEnabled && approle && values.vaultApproleMount
        ? values.vaultApproleMount
        : null,
  };
  if (!values.globalVaultEnabled) body.globalVaultCredential = null;
  else if (values.vaultCredential !== "") body.globalVaultCredential = values.vaultCredential;
  return body;
}

/**
 * Detail page of a tenant: its display name, its immutable URL-safe name,
 * whether it is enabled, how failed sign-ins lock its accounts, and the
 * credential it logs in to the global Vault with. The page
 * is titled with the tenant's display name —
 * the same label its row carries in the list. Reachable only by `super_admin`
 * — `layout.tsx` blocks every other viewer before this page mounts. Name is
 * read-only for everyone, super admins included: it is immutable once the
 * tenant exists.
 */
export default function TenantDetailPage() {
  const { tenantId } = useParams<{ tenantId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);
  // The persisted display name, which titles the page. Kept out of the form so
  // the heading names the saved record rather than following every keystroke.
  const [displayName, setDisplayName] = useState("");
  // name is immutable after creation, so it lives outside the form state and
  // is rendered read-only.
  const [name, setName] = useState("");
  // The auth method whose global Vault credential is stored, or null.
  const [vaultMethod, setVaultMethod] = useState<VaultAuthMethod | null>(null);

  const save = useAsyncAction({ showDone: false });
  const schema = useMemo(() => buildSchema(vaultMethod), [vaultMethod]);
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
    getTenant(tenantId)
      .then((tenant) => {
        setDisplayName(tenant.displayName);
        setName(tenant.name);
        setVaultMethod(savedVaultMethod(storedGlobalVault(tenant)));
        reset(toFormValues(tenant));
        setAudit({
          createdBy: tenant.createdBy,
          updatedBy: tenant.updatedBy,
          createdAt: tenant.createdAt,
          updatedAt: tenant.updatedAt,
        });
      })
      .catch(() => {
        // Failure toast is shown globally by api.ts; nothing else to do here.
      })
      .finally(() => setLoading(false));
  }, [tenantId, reset]);

  async function onSubmit(values: FormValues) {
    try {
      await save.run(async () => {
        await updateTenant(tenantId, toBody(values));
        dispatch(showToast({ message: "Tenant updated" }));
        dispatch(tenantsChanged());
        router.push("/tenants");
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  function handleDelete() {
    setConfirmOpen(true);
  }

  async function executeDelete() {
    setConfirmOpen(false);
    try {
      await deleteTenant(tenantId);
      dispatch(tenantsChanged());
      router.push("/tenants");
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: "Home", href: "/" },
    { label: "Tenants", href: "/tenants" },
    // The tenant itself is the current page; an ellipsis stands in until its
    // display name has loaded.
    { label: displayName || "…" },
  ];

  if (loading) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={<AdminPageHeader icon={Building2} />}>
          <FormSkeleton fields={6} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout
        header={<AdminPageHeader title={displayName} icon={Building2} />}
        aside={audit && <AuditMeta {...audit} />}
      >
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField
            htmlFor="displayName"
            label="Display Name"
            required
            error={errors.displayName?.message}
          >
            <Input id="displayName" {...register("displayName")} />
          </FormField>

          <FormField htmlFor="name" label="Name">
            <ReadOnlyField>{name || EMPTY_VALUE}</ReadOnlyField>
          </FormField>

          <Checkbox label="Enabled" {...register("enabled")} />

          <hr className="border-outline-variant" />

          <SignInLockoutFields
            maxFailures={register("loginMaxFailures")}
            lockoutMinutes={register("loginLockoutMinutes")}
            errors={{
              loginMaxFailures: errors.loginMaxFailures?.message,
              loginLockoutMinutes: errors.loginLockoutMinutes?.message,
            }}
          />

          <hr className="border-outline-variant" />

          <div className="flex flex-col gap-1">
            <Checkbox label="Log in to the global Vault" {...register("globalVaultEnabled")} />
            <p className="text-xs text-on-surface-variant">
              Used only while the tenant has no Vault of its own. Register a credential issued for
              this tenant: the Vault policies attached to it decide which secrets the tenant can
              read.
            </p>
          </div>

          {watch("globalVaultEnabled") && (
            <VaultConnectionFields
              roleId={register("vaultRoleId")}
              approleMount={register("vaultApproleMount")}
              credential={register("vaultCredential")}
              authMethod={watch("vaultAuthMethod")}
              onAuthMethodChange={(method) => setValue("vaultAuthMethod", method)}
              savedMethod={vaultMethod}
              errors={{
                vaultRoleId: errors.vaultRoleId?.message,
                vaultApproleMount: errors.vaultApproleMount?.message,
                vaultCredential: errors.vaultCredential?.message,
              }}
            />
          )}

          <div className="flex gap-2">
            <Button
              type="submit"
              variant="primary"
              disabled={save.inFlight}
              status={save.status}
              pendingLabel="Saving…"
            >
              Save
            </Button>
            <Button type="button" variant="ghost" onClick={() => router.push("/tenants")}>
              Cancel
            </Button>
            <Button type="button" variant="danger" onClick={handleDelete} className="ml-auto">
              Delete
            </Button>
          </div>
        </form>
      </FormLayout>
      <ConfirmDialog
        open={confirmOpen}
        title="Delete Tenant"
        description={`Delete "${displayName}"?`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </AdminPageContainer>
  );
}
