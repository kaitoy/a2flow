/**
 * @module SecretFields — Shared schema and field set for the secret create and
 * edit forms.
 *
 * Both forms edit the same record through the same type-discriminated shape, so
 * the schema, the empty/reset values, the request-body builder, and the fields
 * themselves live here rather than being duplicated per page.
 *
 * A secret holds a map of entries the way a Vault KV path does, so `local`
 * secrets are edited as a key/value list. Values are write-only: the API never
 * returns them, so on the edit form every row starts blank and a blank value
 * means "keep the stored one" — the sentinel the backend's PATCH understands.
 */
"use client";

import type { Control, FieldErrors, UseFormRegister } from "react-hook-form";
import { Controller } from "react-hook-form";
import { z } from "zod";
import { FormField } from "@/components/admin/form-field";
import {
  KeyValueEditor,
  type KeyValuePair,
  pairsToRecord,
} from "@/components/admin/key-value-editor";
import { Input } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { zSecretCreate } from "@/generated/api/zod.gen";
import type { SecretCreate } from "@/lib/api";

/** Charset a secret entry key must use, mirroring the backend's slug rule. */
const ENTRY_KEY_PATTERN = /^[a-zA-Z0-9._-]+$/;

/**
 * Build the validation schema shared by both forms.
 *
 * The generated schema marks the per-type fields nullish with a minimum length,
 * so a hidden empty input would fail validation. The form instead keeps them as
 * plain strings and enforces the per-type requiredness itself, mirroring the
 * backend's shape validation against a merged PATCH.
 *
 * @param requireEntryValues - Whether every entry must carry a value. The
 *   create form requires them; the edit form does not, because a blank value
 *   there keeps the stored one.
 * @returns The zod schema for the form values.
 */
export function buildSecretFormSchema(requireEntryValues: boolean) {
  return z
    .object({
      name: zSecretCreate.shape.name,
      type: zSecretCreate.shape.type,
      entries: z.array(z.object({ key: z.string(), value: z.string().max(8192) })),
      vaultMount: z.string().max(256),
      vaultPath: z.string().max(1024),
    })
    .superRefine((values, ctx) => {
      if (values.type === "local") {
        validateEntries(values.entries, ctx, requireEntryValues);
        return;
      }
      for (const field of ["vaultMount", "vaultPath"] as const) {
        if (values[field] === "") {
          ctx.addIssue({
            code: "custom",
            path: [field],
            message: "Required for a Vault secret",
          });
        }
      }
    });
}

/**
 * Report the first problem with the entry rows of a `local` secret.
 *
 * @param entries - Current entry rows.
 * @param ctx - Refinement context the issue is reported on.
 * @param requireValues - Whether a blank value is an error.
 */
function validateEntries(
  entries: KeyValuePair[],
  ctx: z.RefinementCtx,
  requireValues: boolean
): void {
  const named = entries.filter((entry) => entry.key.trim() !== "");
  if (named.length === 0) {
    ctx.addIssue({
      code: "custom",
      path: ["entries"],
      message: "At least one entry is required",
    });
    return;
  }
  const keys = named.map((entry) => entry.key.trim());
  if (new Set(keys).size !== keys.length) {
    ctx.addIssue({ code: "custom", path: ["entries"], message: "Keys must be unique" });
    return;
  }
  if (keys.some((key) => !ENTRY_KEY_PATTERN.test(key))) {
    ctx.addIssue({
      code: "custom",
      path: ["entries"],
      message: "Keys may use letters, digits, '.', '_' and '-' only",
    });
    return;
  }
  if (requireValues && named.some((entry) => entry.value === "")) {
    ctx.addIssue({
      code: "custom",
      path: ["entries"],
      message: "Every entry requires a value",
    });
  }
}

/** Form values for the secret create and edit forms. */
export type SecretFormValues = z.infer<ReturnType<typeof buildSecretFormSchema>>;

/** Blank form values, used as the create form's fallback and the edit form's reset base. */
export function emptySecretFormValues(): SecretFormValues {
  return {
    name: "",
    type: "local",
    entries: [{ key: "", value: "" }],
    vaultMount: "",
    vaultPath: "",
  };
}

/**
 * Build the request body for the active type, dropping the other type's fields
 * entirely so a PATCH that switches type lets the backend clear the stale ones.
 *
 * @param values - Current form values.
 * @returns The `POST`/`PATCH` body for the secret.
 */
export function toSecretBody(values: SecretFormValues): SecretCreate {
  if (values.type === "local") {
    return {
      name: values.name,
      type: "local",
      entries: pairsToRecord(values.entries),
    };
  }
  return {
    name: values.name,
    type: "vault",
    vaultMount: values.vaultMount,
    vaultPath: values.vaultPath,
  };
}

/** Props for {@link SecretFields}. */
export interface SecretFieldsProps {
  /** `register` from the page's `useForm`. */
  register: UseFormRegister<SecretFormValues>;
  /** `control` from the page's `useForm`, for the entry editor. */
  control: Control<SecretFormValues>;
  /** `formState.errors` from the page's `useForm`. */
  errors: FieldErrors<SecretFormValues>;
  /** Currently selected type, watched by the page so the fields re-render. */
  type: SecretFormValues["type"];
  /** Whether to show input placeholders (the create form does, the edit form does not). */
  showPlaceholders?: boolean;
}

/**
 * Name, type switch, and the type-specific fields of a secret: the key/value
 * entries of a locally encrypted secret, or the mount and path of a Vault KV
 * reference whose keys are read live from Vault.
 */
export function SecretFields({
  register,
  control,
  errors,
  type,
  showPlaceholders = false,
}: SecretFieldsProps) {
  return (
    <>
      <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
        <Input
          id="name"
          placeholder={showPlaceholders ? "e.g. aws-credentials" : undefined}
          {...register("name")}
        />
        <p className="mt-1 text-xs text-on-surface-variant">
          One entry is referenced as{" "}
          {/* biome-ignore lint/suspicious/noTemplateCurlyInString: literal placeholder syntax shown to the user */}
          {"${secret:name/key}"} in MCP server headers and environment variables, and as{" "}
          <code>name/key</code> in Agent Skill repo auth. The key is always required.
        </p>
      </FormField>

      <FormField htmlFor="type" label="Type" required>
        <Controller
          control={control}
          name="type"
          render={({ field }) => (
            <SegmentedControl
              aria-label="Secret type"
              options={[
                { value: "local", label: "Local (encrypted)" },
                { value: "vault", label: "HashiCorp Vault" },
              ]}
              value={field.value}
              onChange={field.onChange}
            />
          )}
        />
      </FormField>

      {type === "local" ? (
        <FormField htmlFor="entries" label="Entries" required error={errors.entries?.message}>
          <Controller
            control={control}
            name="entries"
            render={({ field }) => (
              <KeyValueEditor
                name="entries"
                pairs={field.value}
                onChange={field.onChange}
                valueType="password"
                keyPlaceholder="AWS_ACCESS_KEY_ID"
                valuePlaceholder={
                  showPlaceholders ? "Value (stored encrypted)" : "Leave blank to keep"
                }
              />
            )}
          />
          <p className="mt-1 text-xs text-on-surface-variant">
            {showPlaceholders
              ? "Each value is encrypted before it is stored and is never returned by the API."
              : "Values are never returned by the API. Leave one blank to keep the stored value; remove a row to delete that entry."}
          </p>
        </FormField>
      ) : (
        <>
          <FormField
            htmlFor="vaultMount"
            label="Vault Mount"
            required
            error={errors.vaultMount?.message}
          >
            <Input
              id="vaultMount"
              placeholder={showPlaceholders ? "secret" : undefined}
              {...register("vaultMount")}
            />
          </FormField>
          <FormField
            htmlFor="vaultPath"
            label="Vault Path"
            required
            error={errors.vaultPath?.message}
          >
            <Input
              id="vaultPath"
              placeholder={showPlaceholders ? "myapp/aws" : undefined}
              {...register("vaultPath")}
            />
            <p className="mt-1 text-xs text-on-surface-variant">
              Every key stored at this KV v2 path is available; pick one per reference.
            </p>
          </FormField>
        </>
      )}
    </>
  );
}
