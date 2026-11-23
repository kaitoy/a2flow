/**
 * @module LlmSettingsFields — Shared schema helpers and field sets for the LLM
 * model and API key, edited in three places: System Settings (the platform's
 * own LLM), a tenant's detail page (a super admin setting it for the tenant, and
 * choosing who sets it) and Admin Settings (the tenant's admin, only while a
 * super admin has handed the tenant's LLM over).
 */
"use client";

import type { UseFormRegisterReturn } from "react-hook-form";
import { z } from "zod";
import {
  type CredentialSourceBinding,
  CredentialSourceField,
  credentialSourceSchema,
  initialCredentialSource,
  refineCredentialSource,
} from "@/components/admin/credential-source-field";
import { FormField } from "@/components/admin/form-field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { SegmentedControl, type SegmentedOption } from "@/components/ui/segmented-control";
import type { MessageKey } from "@/i18n/messages/en";
import { useT } from "@/i18n/provider";
import type { LlmMode } from "@/lib/api";

/** Longest model name the backend accepts. */
const MODEL_MAX_LENGTH = 200;

/**
 * Zod shape for the two LLM fields, held as plain strings in the form (empty
 * meaning "none"). Spread into a page's schema.
 */
export const llmShape = {
  llmModel: z.string().max(MODEL_MAX_LENGTH, "llm.modelTooLong"),
  llmApiKey: z.string(),
};

/** Form values for the LLM fields. */
export type LlmFormValues = z.infer<z.ZodObject<typeof llmShape>>;

/** The stored LLM, as any of the settings read views reports it. */
export type StoredLlm = {
  llmModel?: string | null;
};

/** The LLM fields of a request body; `null` clears the model. */
export type LlmBody = {
  llmModel: string | null;
  llmApiKey?: string;
};

/**
 * Convert a stored LLM into form values. The key field always starts blank,
 * since the key is write-only.
 *
 * @param stored - The stored model.
 * @returns The form values.
 */
export function toLlmFormValues(stored: StoredLlm): LlmFormValues {
  return { llmModel: stored.llmModel ?? "", llmApiKey: "" };
}

/**
 * Convert form values into the request body fields. A blank model clears the
 * stored one; a blank key is omitted so the backend keeps the ciphertext it
 * holds.
 *
 * @param values - Validated form values.
 * @returns The LLM fields of the body.
 */
export function toLlmBody(values: LlmFormValues): LlmBody {
  const body: LlmBody = { llmModel: values.llmModel.trim() || null };
  if (values.llmApiKey !== "") body.llmApiKey = values.llmApiKey;
  return body;
}

/** Who sets a tenant's LLM, in the order a super admin reaches for them. */
const MODE_OPTIONS: ReadonlyArray<SegmentedOption<LlmMode>> = [
  { value: "system_default", label: "llm.modeSystemDefault" },
  { value: "super_admin", label: "llm.modeSuperAdmin" },
  { value: "tenant_admin", label: "llm.modeTenantAdmin" },
];

/** Props for {@link LlmModeField}. */
export interface LlmModeFieldProps {
  /** The mode currently selected in the form. */
  mode: LlmMode;
  /** Called when another mode is picked. */
  onModeChange: (mode: LlmMode) => void;
  /** Whether to print the "LLM" heading; off where another field already did. */
  withTitle?: boolean;
  /** The field's label; defaults to "Who sets the LLM". */
  label?: MessageKey;
  /**
   * One hint for every mode, in place of the per-mode ones that speak of "this
   * tenant" — for the default new tenants start with, which has no tenant yet.
   */
  hint?: MessageKey;
}

/**
 * The "LLM" section heading and the choice of who sets the tenant's LLM: the
 * system's setting as it is, a super admin, or the tenant's own admin.
 */
export function LlmModeField({
  mode,
  onModeChange,
  withTitle = true,
  label = "llm.mode",
  hint,
}: LlmModeFieldProps) {
  const t = useT();
  const modeHint: Record<LlmMode, MessageKey> = {
    system_default: "llm.modeSystemDefaultHint",
    super_admin: "llm.modeSuperAdminHint",
    tenant_admin: "llm.modeTenantAdminHint",
  };
  return (
    <>
      {withTitle && (
        <h2 className="font-display text-lg font-semibold tracking-tight text-on-surface">
          {t("llm.title")}
        </h2>
      )}
      <FormField htmlFor="llmMode" label={t(label)}>
        <SegmentedControl
          options={MODE_OPTIONS}
          value={mode}
          onChange={onModeChange}
          aria-label={t(label)}
        />
        <p className="text-xs text-on-surface-variant">{t(hint ?? modeHint[mode])}</p>
      </FormField>
    </>
  );
}

/**
 * Zod shape for the LLM a tenant's admin sets: {@link llmShape} plus whether
 * the key is entered or read from one of the tenant's secrets. A super admin's
 * key is always entered, so only Admin Settings uses this.
 */
export const tenantAdminLlmShape = {
  ...llmShape,
  llmApiKeySource: credentialSourceSchema,
  llmApiKeyRef: z.string(),
};

/** Form values for {@link tenantAdminLlmShape}. */
export type TenantAdminLlmFormValues = z.infer<z.ZodObject<typeof tenantAdminLlmShape>>;

/**
 * Convert a tenant admin's stored LLM into form values, starting on "Use a
 * secret" when the key is referenced from one.
 *
 * @param stored - The stored model and key reference.
 * @returns The form values.
 */
export function toTenantAdminLlmFormValues(
  stored: StoredLlm & { llmApiKeyRef?: string | null }
): TenantAdminLlmFormValues {
  return {
    ...toLlmFormValues(stored),
    llmApiKeySource: initialCredentialSource(stored.llmApiKeyRef),
    llmApiKeyRef: stored.llmApiKeyRef ?? "",
  };
}

/**
 * Convert a tenant admin's LLM into request body fields: the reference alone
 * with "Use a secret" (the backend then drops a stored key), otherwise
 * {@link toLlmBody} with the reference cleared.
 *
 * @param values - Validated form values.
 * @returns The LLM fields of the body.
 */
export function toTenantAdminLlmBody(
  values: TenantAdminLlmFormValues
): LlmBody & { llmApiKeyRef: string | null } {
  if (values.llmApiKeySource === "secret") {
    return { llmModel: values.llmModel.trim() || null, llmApiKeyRef: values.llmApiKeyRef };
  }
  return { ...toLlmBody(values), llmApiKeyRef: null };
}

/**
 * Require an API key with a model, for the LLM a tenant's admin sets: the
 * platform's key never pays for a model the admin picked (the backend refuses
 * the save too). A key already stored counts, since it never reaches the form.
 * With "Use a secret" a complete reference is required instead.
 *
 * @param values - The LLM fields of the form.
 * @param ctx - The refinement context to report issues on.
 * @param keySaved - Whether an API key (not a reference) is already stored.
 */
export function refineTenantAdminLlm(
  values: TenantAdminLlmFormValues,
  ctx: z.RefinementCtx,
  keySaved: boolean
): void {
  if (values.llmApiKeySource === "secret") {
    refineCredentialSource("secret", values.llmApiKeyRef, "llmApiKeyRef", ctx);
    return;
  }
  if (values.llmModel.trim() !== "" && values.llmApiKey === "" && !keySaved) {
    ctx.addIssue({ code: "custom", path: ["llmApiKey"], message: "llm.apiKeyRequired" });
  }
}

/** Props for {@link LlmSettingsFields}. */
export interface LlmSettingsFieldsProps {
  /** `register("llmModel")` from the page's `useForm`. */
  model: UseFormRegisterReturn;
  /** `register("llmApiKey")` from the page's `useForm`. */
  apiKey: UseFormRegisterReturn;
  /** Whether an API key is already stored. */
  apiKeySaved: boolean;
  /** Validation errors for the two fields, if any. */
  errors: { llmModel?: string; llmApiKey?: string };
  /**
   * Whether a field left empty falls back to the platform's LLM — true for a
   * tenant's, false for the platform's own.
   */
  inherits?: boolean;
  /**
   * Whether a model needs a key of its own — true for the LLM a tenant's admin
   * sets, which may not run on the system's key (see {@link refineTenantAdminLlm}).
   */
  keyRequired?: boolean;
  /** Whether to print the "LLM" heading; off where {@link LlmModeField} already did. */
  withTitle?: boolean;
  /**
   * Lets the key be read from one of the tenant's secrets instead — only for
   * the LLM a tenant's admin sets. Without it the key can only be entered.
   */
  apiKeySource?: CredentialSourceBinding;
}

/** The model name and the write-only API key. */
export function LlmSettingsFields({
  model,
  apiKey,
  apiKeySaved,
  errors,
  inherits = false,
  keyRequired = false,
  withTitle = true,
  apiKeySource,
}: LlmSettingsFieldsProps) {
  const t = useT();
  const keyHint = keyRequired
    ? "llm.apiKeyHintTenantAdmin"
    : inherits
      ? "llm.apiKeyHintTenant"
      : "llm.apiKeyHint";
  const keyInput = (
    <PasswordInput
      id="llmApiKey"
      autoComplete="new-password"
      placeholder={apiKeySaved ? t("common.savedLeaveEmptyToKeepIt") : ""}
      {...apiKey}
    />
  );
  return (
    <>
      {withTitle && (
        <h2 className="font-display text-lg font-semibold tracking-tight text-on-surface">
          {t("llm.title")}
        </h2>
      )}

      <FormField htmlFor="llmModel" label={t("llm.model")} error={errors.llmModel}>
        <Input
          id="llmModel"
          autoComplete="off"
          placeholder={t("common.exampleValue", { value: "litellm:openai/gpt-6.1-sol" })}
          {...model}
        />
        <p className="text-xs text-on-surface-variant">
          {t("llm.modelHint")} {inherits ? t("llm.modelEmptyTenant") : t("llm.modelEmpty")}
        </p>
      </FormField>

      {apiKeySource ? (
        <CredentialSourceField
          htmlFor="llmApiKey"
          label={t("llm.apiKey")}
          binding={apiKeySource}
          hint={t(keyHint)}
          error={errors.llmApiKey}
        >
          {keyInput}
        </CredentialSourceField>
      ) : (
        <FormField htmlFor="llmApiKey" label={t("llm.apiKey")} error={errors.llmApiKey}>
          {keyInput}
          <p className="text-xs text-on-surface-variant">{t(keyHint)}</p>
        </FormField>
      )}
    </>
  );
}
