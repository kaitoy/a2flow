/**
 * @module VaultConnectionFields — Shared schema helpers and field set for a
 * HashiCorp Vault connection, edited on the Tenant Settings page (a tenant's
 * own Vault, address included) and on a tenant's detail page (its credential
 * for the global Vault, whose address is a system setting).
 */
"use client";

import type { ReactNode } from "react";
import type { UseFormRegisterReturn } from "react-hook-form";
import { z } from "zod";
import { FormField } from "@/components/admin/form-field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { SegmentedControl, type SegmentedOption } from "@/components/ui/segmented-control";
import { zTenantSettingsUpdate } from "@/generated/api/zod.gen";
import { useT } from "@/i18n/provider";
import type { VaultAuthMethod } from "@/lib/api";

/** How A2Flow logs in to the Vault. */
const AUTH_OPTIONS: ReadonlyArray<SegmentedOption<VaultAuthMethod>> = [
  { value: "token", label: "admin.token" },
  { value: "approle", label: "AppRole" },
];

/**
 * Zod shape for the credential fields alone, held as plain strings in the form
 * (empty meaning "none"). Check them with {@link refineVaultCredential}.
 */
export const vaultCredentialShape = {
  vaultAuthMethod: z.enum(["token", "approle"]),
  vaultRoleId: z.string(),
  vaultApproleMount: z.string(),
  vaultCredential: z.string(),
};

/**
 * Zod shape for the connection fields, address included. Spread into a page's
 * schema, then check the cross-field rules with {@link refineVaultConnection}.
 */
export const vaultConnectionShape = {
  vaultAddr: z.string(),
  ...vaultCredentialShape,
};

/** Form values for the credential fields. */
export type VaultCredentialFormValues = {
  vaultAuthMethod: VaultAuthMethod;
  vaultRoleId: string;
  vaultApproleMount: string;
  vaultCredential: string;
};

/** Form values for the connection fields. */
export type VaultConnectionFormValues = VaultCredentialFormValues & {
  vaultAddr: string;
};

/** The stored connection, as either settings read view reports it. */
export type StoredVaultConnection = {
  vaultAddr?: string | null;
  vaultAuthMethod?: VaultAuthMethod | null;
  vaultRoleId?: string | null;
  vaultApproleMount?: string | null;
  vaultCredentialSet?: boolean;
};

/** The connection fields of a request body; `null` clears a field. */
export type VaultConnectionBody = {
  vaultAddr: string | null;
  vaultAuthMethod: VaultAuthMethod | null;
  vaultRoleId: string | null;
  vaultApproleMount: string | null;
  vaultCredential?: string | null;
};

/**
 * Check the cross-field rules the backend applies to a merged connection, for
 * use inside a page schema's `superRefine`.
 *
 * @param values - The connection fields of the form.
 * @param ctx - The refinement context to report issues on.
 * @param savedMethod - The auth method whose credential is stored, if any. The
 *   credential itself never reaches the client, so leaving the field blank is
 *   acceptable only while the method stays the same.
 */
export function refineVaultConnection(
  values: VaultConnectionFormValues,
  ctx: z.RefinementCtx,
  savedMethod: VaultAuthMethod | null
): void {
  if (values.vaultAddr === "") return;
  if (!zTenantSettingsUpdate.shape.vaultAddr.safeParse(values.vaultAddr).success) {
    ctx.addIssue({
      code: "custom",
      path: ["vaultAddr"],
      message: "admin.enterHttpAddress",
    });
  }
  refineVaultCredential(values, ctx, savedMethod);
}

/**
 * Check the credential rules the backend applies to a connection in use, for
 * use inside a page schema's `superRefine` — on its own where the address is
 * stored elsewhere (the global Vault), or through {@link refineVaultConnection}.
 *
 * @param values - The credential fields of the form.
 * @param ctx - The refinement context to report issues on.
 * @param savedMethod - The auth method whose credential is stored, if any.
 */
export function refineVaultCredential(
  values: VaultCredentialFormValues,
  ctx: z.RefinementCtx,
  savedMethod: VaultAuthMethod | null
): void {
  if (values.vaultCredential === "" && savedMethod !== values.vaultAuthMethod) {
    ctx.addIssue({
      code: "custom",
      path: ["vaultCredential"],
      message:
        values.vaultAuthMethod === "approle" ? "admin.secretIdIsRequired" : "admin.tokenIsRequired",
    });
  }
  if (values.vaultAuthMethod === "approle" && values.vaultRoleId === "") {
    ctx.addIssue({ code: "custom", path: ["vaultRoleId"], message: "admin.roleIdIsRequired" });
  }
}

/**
 * The auth method whose credential is stored, or `null` when none is.
 *
 * @param stored - The stored connection.
 * @returns The method a blank credential field keeps the credential for.
 */
export function savedVaultMethod(stored: StoredVaultConnection): VaultAuthMethod | null {
  return stored.vaultCredentialSet ? (stored.vaultAuthMethod ?? "token") : null;
}

/**
 * Convert a stored connection into form values. The credential field always
 * starts blank, since the credential is write-only.
 *
 * @param stored - The stored connection.
 * @returns The form values.
 */
export function toVaultConnectionFormValues(
  stored: StoredVaultConnection
): VaultConnectionFormValues {
  return {
    vaultAddr: stored.vaultAddr ?? "",
    vaultAuthMethod: stored.vaultAuthMethod ?? "token",
    vaultRoleId: stored.vaultRoleId ?? "",
    vaultApproleMount: stored.vaultApproleMount ?? "",
    vaultCredential: "",
  };
}

/**
 * Convert form values into the request body fields. An empty address clears
 * the whole connection, credential included; otherwise an untouched
 * credential field is omitted so the backend keeps the ciphertext it holds.
 *
 * @param values - Validated form values.
 * @returns The connection fields of the body.
 */
export function toVaultConnectionBody(values: VaultConnectionFormValues): VaultConnectionBody {
  if (values.vaultAddr === "") {
    return {
      vaultAddr: null,
      vaultAuthMethod: null,
      vaultRoleId: null,
      vaultApproleMount: null,
      vaultCredential: null,
    };
  }
  const approle = values.vaultAuthMethod === "approle";
  const body: VaultConnectionBody = {
    vaultAddr: values.vaultAddr,
    vaultAuthMethod: values.vaultAuthMethod,
    vaultRoleId: approle ? values.vaultRoleId : null,
    vaultApproleMount: approle && values.vaultApproleMount ? values.vaultApproleMount : null,
  };
  if (values.vaultCredential !== "") body.vaultCredential = values.vaultCredential;
  return body;
}

/** Props for {@link VaultConnectionFields}. */
export interface VaultConnectionFieldsProps {
  /**
   * `register("vaultAddr")` from the page's `useForm`. Omitted where the
   * address is stored elsewhere, which leaves the address field out.
   */
  addr?: UseFormRegisterReturn;
  /** `register("vaultRoleId")` from the page's `useForm`. */
  roleId: UseFormRegisterReturn;
  /** `register("vaultApproleMount")` from the page's `useForm`. */
  approleMount: UseFormRegisterReturn;
  /** `register("vaultCredential")` from the page's `useForm`. */
  credential: UseFormRegisterReturn;
  /** The auth method currently selected in the form. */
  authMethod: VaultAuthMethod;
  /** Called when another auth method is picked. */
  onAuthMethodChange: (method: VaultAuthMethod) => void;
  /** The auth method whose credential is stored, if any. */
  savedMethod: VaultAuthMethod | null;
  /** Help text under the address field. */
  addrHint?: ReactNode;
  /** Validation errors for the fields, if any. */
  errors: {
    vaultAddr?: string;
    vaultRoleId?: string;
    vaultApproleMount?: string;
    vaultCredential?: string;
  };
}

/**
 * The Vault address (when `addr` is given), auth method, AppRole role id and
 * mount, and a write-only token or AppRole secret id.
 */
export function VaultConnectionFields({
  addr,
  roleId,
  approleMount,
  credential,
  authMethod,
  onAuthMethodChange,
  savedMethod,
  addrHint,
  errors,
}: VaultConnectionFieldsProps) {
  const t = useT();
  const credentialSaved = savedMethod !== null && savedMethod === authMethod;
  return (
    <>
      {addr && (
        <FormField htmlFor="vaultAddr" label={t("admin.vaultAddress")} error={errors.vaultAddr}>
          <Input id="vaultAddr" placeholder="https://vault.example.com:8200" {...addr} />
          <p className="text-xs text-on-surface-variant">{addrHint}</p>
        </FormField>
      )}

      <FormField htmlFor="vaultAuthMethod" label={t("admin.vaultAuthMethod")}>
        <SegmentedControl
          options={AUTH_OPTIONS}
          value={authMethod}
          onChange={onAuthMethodChange}
          aria-label={t("admin.vaultAuthMethod2")}
        />
      </FormField>

      {authMethod === "approle" && (
        <>
          <FormField
            htmlFor="vaultRoleId"
            label={t("admin.vaultRoleId")}
            error={errors.vaultRoleId}
          >
            <Input id="vaultRoleId" {...roleId} />
          </FormField>
          <FormField
            htmlFor="vaultApproleMount"
            label={t("admin.approleMount")}
            error={errors.vaultApproleMount}
          >
            <Input id="vaultApproleMount" placeholder="approle" {...approleMount} />
          </FormField>
        </>
      )}

      <FormField
        htmlFor="vaultCredential"
        label={authMethod === "approle" ? t("admin.vaultSecretId") : t("admin.vaultToken")}
        error={errors.vaultCredential}
      >
        <PasswordInput
          id="vaultCredential"
          autoComplete="new-password"
          placeholder={credentialSaved ? t("common.savedLeaveEmptyToKeepIt") : ""}
          {...credential}
        />
      </FormField>
    </>
  );
}
