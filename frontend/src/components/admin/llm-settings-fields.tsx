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
}

/**
 * The "LLM" section heading and the choice of who sets the tenant's LLM: the
 * system's setting as it is, a super admin, or the tenant's own admin.
 */
export function LlmModeField({ mode, onModeChange }: LlmModeFieldProps) {
  const t = useT();
  const hint: Record<LlmMode, MessageKey> = {
    system_default: "llm.modeSystemDefaultHint",
    super_admin: "llm.modeSuperAdminHint",
    tenant_admin: "llm.modeTenantAdminHint",
  };
  return (
    <>
      <h2 className="font-display text-lg font-semibold tracking-tight text-on-surface">
        {t("llm.title")}
      </h2>
      <FormField htmlFor="llmMode" label={t("llm.mode")}>
        <SegmentedControl
          options={MODE_OPTIONS}
          value={mode}
          onChange={onModeChange}
          aria-label={t("llm.mode")}
        />
        <p className="text-xs text-on-surface-variant">{t(hint[mode])}</p>
      </FormField>
    </>
  );
}

/**
 * Require an API key with a model, for the LLM a tenant's admin sets: the
 * platform's key never pays for a model the admin picked (the backend refuses
 * the save too). A key already stored counts, since it never reaches the form.
 *
 * @param values - The LLM fields of the form.
 * @param ctx - The refinement context to report issues on.
 * @param keySaved - Whether an API key is already stored.
 */
export function refineTenantAdminLlm(
  values: LlmFormValues,
  ctx: z.RefinementCtx,
  keySaved: boolean
): void {
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
}: LlmSettingsFieldsProps) {
  const t = useT();
  const keyHint = keyRequired
    ? "llm.apiKeyHintTenantAdmin"
    : inherits
      ? "llm.apiKeyHintTenant"
      : "llm.apiKeyHint";
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

      <FormField htmlFor="llmApiKey" label={t("llm.apiKey")} error={errors.llmApiKey}>
        <PasswordInput
          id="llmApiKey"
          autoComplete="new-password"
          placeholder={apiKeySaved ? t("common.savedLeaveEmptyToKeepIt") : ""}
          {...apiKey}
        />
        <p className="text-xs text-on-surface-variant">{t(keyHint)}</p>
      </FormField>
    </>
  );
}
