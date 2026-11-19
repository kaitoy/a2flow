/**
 * @module CredentialSourceField — A credential that is either entered here or
 * referenced from one of the tenant's secrets.
 *
 * The secret can be local or HashiCorp Vault-backed; either way it is read each
 * time the credential is used, which is what lets a value rotated in Vault take
 * effect without saving the form again. Used for the OIDC client secret and the
 * tenant admin's LLM API key on Admin Settings.
 */
"use client";

import type React from "react";
import { z } from "zod";
import { FormField } from "@/components/admin/form-field";
import { SecretRefField } from "@/components/admin/secret-ref-field";
import { SegmentedControl, type SegmentedOption } from "@/components/ui/segmented-control";
import { useT } from "@/i18n/provider";

/** Zod schema of a credential's source, for a page's form schema. */
export const credentialSourceSchema = z.enum(["value", "secret"]);

/** Where a credential comes from: typed into the form, or a secret entry. */
export type CredentialSource = z.infer<typeof credentialSourceSchema>;

/**
 * The source a stored credential starts the form in: a stored reference means
 * the credential is read from a secret.
 *
 * @param ref - The stored `name/key` reference, if any.
 * @returns `"secret"` when a reference is stored, otherwise `"value"`.
 */
export function initialCredentialSource(ref: string | null | undefined): CredentialSource {
  return ref ? "secret" : "value";
}

/**
 * Require a complete reference once "Use a secret" is selected: choosing the
 * source and then no secret would otherwise save as "nothing changed".
 *
 * @param source - The selected source.
 * @param ref - The reference in the form, `""` while incomplete.
 * @param path - Form field the issue is reported on.
 * @param ctx - The refinement context.
 */
export function refineCredentialSource(
  source: CredentialSource,
  ref: string,
  path: string,
  ctx: z.RefinementCtx
): void {
  if (source === "secret" && ref === "") {
    ctx.addIssue({ code: "custom", path: [path], message: "credentialSource.secretRequired" });
  }
}

/** The state a page binds to one {@link CredentialSourceField}. */
export interface CredentialSourceBinding {
  /** The source currently selected. */
  source: CredentialSource;
  /** Called when the other source is picked. */
  onSourceChange: (source: CredentialSource) => void;
  /** The `name/key` reference, or `""` when none is chosen. */
  secretRef: string;
  /** Called with the new reference, `""` while it is incomplete. */
  onSecretRefChange: (ref: string) => void;
  /** Validation message for the reference, if any. */
  secretRefError?: string;
}

/** The two sources, in the order they are offered. */
const SOURCE_OPTIONS: ReadonlyArray<SegmentedOption<CredentialSource>> = [
  { value: "value", label: "credentialSource.enterValue" },
  { value: "secret", label: "credentialSource.useSecret" },
];

/** Props for {@link CredentialSourceField}. */
export interface CredentialSourceFieldProps {
  /** Id of the value input; the label points at it. */
  htmlFor: string;
  /** Label of the credential, e.g. "Client secret". */
  label: string;
  /** The selected source and the reference, owned by the page. */
  binding: CredentialSourceBinding;
  /** The value input, shown while "Enter value" is selected. */
  children: React.ReactNode;
  /** Hint under the value input. */
  hint?: string;
  /** Validation message for the value input, if any. */
  error?: string;
}

/**
 * A switch between entering a credential and referencing a secret entry, with
 * the control for whichever is selected below it.
 */
export function CredentialSourceField({
  htmlFor,
  label,
  binding,
  children,
  hint,
  error,
}: CredentialSourceFieldProps) {
  const t = useT();
  const bySecret = binding.source === "secret";
  return (
    <FormField htmlFor={htmlFor} label={label} error={bySecret ? undefined : error}>
      <SegmentedControl
        options={SOURCE_OPTIONS}
        value={binding.source}
        onChange={binding.onSourceChange}
        aria-label={t("credentialSource.choose", { field: label })}
      />
      {bySecret ? (
        <SecretRefField
          value={binding.secretRef}
          onChange={binding.onSecretRefChange}
          label={t("credentialSource.secret")}
          idPrefix={`${htmlFor}Ref`}
          hint={t("credentialSource.secretHint")}
          error={binding.secretRefError && t.maybe(binding.secretRefError)}
        />
      ) : (
        <>
          {children}
          {hint && <p className="text-xs text-on-surface-variant">{hint}</p>}
        </>
      )}
    </FormField>
  );
}
