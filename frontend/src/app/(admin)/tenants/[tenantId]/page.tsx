/** @module TenantDetailPage — Admin detail page for an existing tenant. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Building2 } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormField } from "@/components/admin/form-field";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { SegmentedControl, type SegmentedOption } from "@/components/ui/segmented-control";
import { zTenantCreate, zTenantUpdate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import {
  deleteTenant,
  getTenant,
  type TenantUpdate,
  updateTenant,
  type VaultAuthMethod,
} from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";
import { useAppDispatch } from "@/store/hooks";
import { tenantsChanged } from "@/store/tenantsSlice";
import { showToast } from "@/store/toastSlice";

/** How A2Flow logs in to the tenant's Vault. */
const AUTH_OPTIONS: ReadonlyArray<SegmentedOption<VaultAuthMethod>> = [
  { value: "token", label: "Token" },
  { value: "approle", label: "AppRole" },
];

/**
 * Build the validation schema, mirroring the merged-result rules the backend
 * applies in `TenantService`.
 *
 * `name` is immutable after creation, so it is kept out of the form and
 * rendered as a read-only field instead. The Vault fields are plain strings
 * (empty meaning "none"); `savedMethod` is the auth method whose credential is
 * stored, if any -- the credential itself never reaches the client, so leaving
 * the field blank is acceptable only while the method stays the same.
 */
function buildSchema(savedMethod: VaultAuthMethod | null) {
  return zTenantCreate
    .pick({ displayName: true, enabled: true })
    .extend({
      vaultAddr: z.string(),
      vaultAuthMethod: z.enum(["token", "approle"]),
      vaultRoleId: z.string(),
      vaultApproleMount: z.string(),
      vaultCredential: z.string(),
    })
    .superRefine((values, ctx) => {
      if (values.vaultAddr === "") return;
      if (!zTenantUpdate.shape.vaultAddr.safeParse(values.vaultAddr).success) {
        ctx.addIssue({
          code: "custom",
          path: ["vaultAddr"],
          message: "Enter an http:// or https:// address",
        });
      }
      if (values.vaultCredential === "" && savedMethod !== values.vaultAuthMethod) {
        ctx.addIssue({
          code: "custom",
          path: ["vaultCredential"],
          message:
            values.vaultAuthMethod === "approle" ? "Secret ID is required" : "Token is required",
        });
      }
      if (values.vaultAuthMethod === "approle" && values.vaultRoleId === "") {
        ctx.addIssue({ code: "custom", path: ["vaultRoleId"], message: "Role ID is required" });
      }
    });
}

type FormValues = z.infer<ReturnType<typeof buildSchema>>;

/**
 * Build the PATCH body. An empty Vault address clears the whole connection,
 * credential included; otherwise an untouched credential field is omitted so
 * the backend keeps the ciphertext it already holds.
 */
function toBody(values: FormValues): TenantUpdate {
  const body: TenantUpdate = { displayName: values.displayName, enabled: values.enabled };
  if (values.vaultAddr === "") {
    return {
      ...body,
      vaultAddr: null,
      vaultAuthMethod: null,
      vaultRoleId: null,
      vaultApproleMount: null,
      vaultCredential: null,
    };
  }
  const approle = values.vaultAuthMethod === "approle";
  body.vaultAddr = values.vaultAddr;
  body.vaultAuthMethod = values.vaultAuthMethod;
  body.vaultRoleId = approle ? values.vaultRoleId : null;
  body.vaultApproleMount = approle && values.vaultApproleMount ? values.vaultApproleMount : null;
  if (values.vaultCredential !== "") body.vaultCredential = values.vaultCredential;
  return body;
}

/**
 * Detail page of a tenant: its display name, its immutable URL-safe name,
 * whether it is enabled, and the connection to its own HashiCorp Vault (address,
 * auth method, and a write-only token or AppRole secret id). The page is titled with the tenant's display name —
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
  // The auth method whose credential is stored, or null when none is. Drives
  // the credential placeholder and whether leaving it blank is acceptable.
  const [savedMethod, setSavedMethod] = useState<VaultAuthMethod | null>(null);
  const schema = useMemo(() => buildSchema(savedMethod), [savedMethod]);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    reset,
    control,
    watch,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: {
      displayName: "",
      enabled: true,
      vaultAddr: "",
      vaultAuthMethod: "token",
      vaultRoleId: "",
      vaultApproleMount: "",
      vaultCredential: "",
    },
  });
  const authMethod = watch("vaultAuthMethod");
  const credentialSaved = savedMethod !== null && savedMethod === authMethod;

  useEffect(() => {
    getTenant(tenantId)
      .then((tenant) => {
        setDisplayName(tenant.displayName);
        setName(tenant.name);
        setSavedMethod(tenant.vaultCredentialSet ? (tenant.vaultAuthMethod ?? "token") : null);
        reset({
          displayName: tenant.displayName,
          enabled: tenant.enabled,
          vaultAddr: tenant.vaultAddr ?? "",
          vaultAuthMethod: tenant.vaultAuthMethod ?? "token",
          vaultRoleId: tenant.vaultRoleId ?? "",
          vaultApproleMount: tenant.vaultApproleMount ?? "",
          vaultCredential: "",
        });
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

          <FormField htmlFor="vaultAddr" label="Vault Address" error={errors.vaultAddr?.message}>
            <Input
              id="vaultAddr"
              placeholder="https://vault.example.com:8200"
              {...register("vaultAddr")}
            />
            <p className="text-xs text-on-surface-variant">
              The HashiCorp Vault this tenant&apos;s Vault-type secrets are read from. Leave empty
              to disconnect it.
            </p>
          </FormField>

          <FormField htmlFor="vaultAuthMethod" label="Vault Auth Method">
            <Controller
              name="vaultAuthMethod"
              control={control}
              render={({ field }) => (
                <SegmentedControl
                  options={AUTH_OPTIONS}
                  value={field.value}
                  onChange={field.onChange}
                  aria-label="Vault auth method"
                />
              )}
            />
          </FormField>

          {authMethod === "approle" && (
            <>
              <FormField
                htmlFor="vaultRoleId"
                label="Vault Role ID"
                error={errors.vaultRoleId?.message}
              >
                <Input id="vaultRoleId" {...register("vaultRoleId")} />
              </FormField>
              <FormField
                htmlFor="vaultApproleMount"
                label="AppRole Mount"
                error={errors.vaultApproleMount?.message}
              >
                <Input
                  id="vaultApproleMount"
                  placeholder="approle"
                  {...register("vaultApproleMount")}
                />
              </FormField>
            </>
          )}

          <FormField
            htmlFor="vaultCredential"
            label={authMethod === "approle" ? "Vault Secret ID" : "Vault Token"}
            error={errors.vaultCredential?.message}
          >
            <PasswordInput
              id="vaultCredential"
              autoComplete="new-password"
              placeholder={credentialSaved ? "Saved — leave empty to keep it" : ""}
              {...register("vaultCredential")}
            />
          </FormField>

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
