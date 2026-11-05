/**
 * @module AgentSkillFields — Shared schema and field set for the agent skill
 * create and edit forms.
 *
 * Both forms edit the same record through the same shape, so the schema, the
 * empty/reset values, the request-body builders, and the fields themselves live
 * here rather than being duplicated per page.
 *
 * The two body builders are deliberately separate rather than one call with a
 * flag: the wire contracts genuinely differ. On create an absent optional field
 * means "take the default", so blanks are omitted; on update it means "leave
 * the stored value alone", so blanks must be sent as `null` to clear it.
 */
"use client";

import type { Control, FieldErrors, UseFormRegister } from "react-hook-form";
import { Controller } from "react-hook-form";
import { z } from "zod";
import { FormField } from "@/components/admin/form-field";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import { SecretRefField } from "@/components/admin/secret-ref-field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zAgentSkillCreate } from "@/generated/api/zod.gen";
import { useT } from "@/i18n/provider";
import type { AgentSkillCreate, AgentSkillUpdate } from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/**
 * Validation schema shared by the create and edit forms.
 *
 * The generated auth fields are nullish with a minimum length, so a blank one
 * would fail validation; the form allows the empty string ("no auth") and each
 * body builder maps it to that endpoint's own "unset" representation.
 */
export const agentSkillFormSchema = zAgentSkillCreate
  .omit({ repoAuthPassword: true, repoAuthUsername: true })
  .extend({
    repoAuthPassword: z.literal("").or(zAgentSkillCreate.shape.repoAuthPassword.unwrap().unwrap()),
    repoAuthUsername: z.literal("").or(zAgentSkillCreate.shape.repoAuthUsername.unwrap().unwrap()),
  });

/**
 * Form values for the agent skill create and edit forms.
 *
 * The schema's *input* type, not `z.infer`'s output: the generated `repoPath`
 * carries `.default('')`, so the two differ there, and `useForm` types its
 * fields — and therefore the `register`/`control` handed to
 * {@link AgentSkillFields} — from the input side.
 */
export type AgentSkillFormValues = z.input<typeof agentSkillFormSchema>;

/** Blank form values, used as the create form's defaults and the edit form's reset base. */
export function emptyAgentSkillFormValues(): AgentSkillFormValues {
  return {
    name: "",
    repoUrl: "",
    repoPath: "",
    repoRef: "",
    description: "",
    repoAuthPassword: "",
    repoAuthUsername: "",
  };
}

/**
 * Build the `POST` body, omitting every optional field left blank so the
 * backend applies its own default.
 *
 * @param values - Current form values.
 * @returns The body for creating the skill.
 */
export function toAgentSkillCreateBody(values: AgentSkillFormValues): AgentSkillCreate {
  return {
    name: values.name,
    repoUrl: values.repoUrl,
    repoPath: values.repoPath || undefined,
    repoRef: values.repoRef || null,
    description: values.description || null,
    repoAuthPassword: values.repoAuthPassword || undefined,
    repoAuthUsername: values.repoAuthUsername || undefined,
  };
}

/**
 * Build the `PATCH` body, sending every optional field left blank as `null` so
 * a value the user cleared is actually cleared server-side.
 *
 * @param values - Current form values.
 * @returns The body for updating the skill.
 */
export function toAgentSkillUpdateBody(values: AgentSkillFormValues): AgentSkillUpdate {
  return {
    name: values.name,
    repoUrl: values.repoUrl,
    repoPath: values.repoPath,
    repoRef: values.repoRef || null,
    description: values.description || null,
    repoAuthPassword: values.repoAuthPassword || null,
    repoAuthUsername: values.repoAuthUsername || null,
  };
}

/** Props for the editable rendering of {@link AgentSkillFields}. */
export interface AgentSkillEditableFieldsProps {
  /** `register` from the page's `useForm`. */
  register: UseFormRegister<AgentSkillFormValues>;
  /** `control` from the page's `useForm`, for the secret reference picker. */
  control: Control<AgentSkillFormValues>;
  /** `formState.errors` from the page's `useForm`. */
  errors: FieldErrors<AgentSkillFormValues>;
  /** Whether to show input placeholders (the create form does, the edit form does not). */
  showPlaceholders?: boolean;
}

/** Props for the read-only rendering of {@link AgentSkillFields}. */
export interface AgentSkillReadOnlyFieldsProps {
  /** Renders every field as a value instead of a control. */
  readOnly: true;
  /** The values to display, e.g. the edit form's `getValues()`. */
  values: AgentSkillFormValues;
}

/**
 * Props for {@link AgentSkillFields}: either the form handles to edit with, or
 * the values to display. A read-only rendering has no control to register
 * against and no errors to report, so the two shapes are kept apart rather than
 * left as optional props that only make sense in one mode.
 */
export type AgentSkillFieldsProps =
  | ({ readOnly?: false } & AgentSkillEditableFieldsProps)
  | AgentSkillReadOnlyFieldsProps;

/**
 * The same fields as values on a recessed surface, for a viewer who may see the
 * skill but not edit it.
 *
 * The auth password is shown as its stored `name/key` reference rather than
 * through {@link SecretRefField}: the picker exists to *choose* a reference, and
 * mounting it would list every registered secret to a viewer who has no business
 * editing this record.
 */
function AgentSkillFieldValues({ values }: { values: AgentSkillFormValues }) {
  const t = useT();
  return (
    <>
      <FormField htmlFor="name" label={t("common.name")} required>
        <ReadOnlyField>{values.name || EMPTY_VALUE}</ReadOnlyField>
      </FormField>

      <FormField htmlFor="repoUrl" label={t("common.repoUrl")} required>
        <ReadOnlyField>{values.repoUrl || EMPTY_VALUE}</ReadOnlyField>
      </FormField>

      <FormField htmlFor="repoPath" label={t("common.repoPath")}>
        <ReadOnlyField>{values.repoPath || EMPTY_VALUE}</ReadOnlyField>
      </FormField>

      <FormField htmlFor="repoRef" label={t("common.ref")}>
        <ReadOnlyField>{values.repoRef || EMPTY_VALUE}</ReadOnlyField>
      </FormField>

      <FormField htmlFor="description" label={t("common.description")}>
        <ReadOnlyField className="whitespace-pre-wrap">
          {values.description || EMPTY_VALUE}
        </ReadOnlyField>
      </FormField>

      <FormField htmlFor="repoAuthUsername" label={t("common.authUsername")}>
        <ReadOnlyField>{values.repoAuthUsername || EMPTY_VALUE}</ReadOnlyField>
      </FormField>

      <FormField htmlFor="repoAuthPassword" label={t("common.authPassword")}>
        <ReadOnlyField>{values.repoAuthPassword || EMPTY_VALUE}</ReadOnlyField>
      </FormField>
    </>
  );
}

/**
 * Name, repository location, description, and repository credentials of an
 * agent skill. The clone token is not typed in — it is picked as one entry of a
 * registered secret, which is the only form the backend accepts.
 *
 * Pass `readOnly` with the current `values` to render the same fields as plain
 * values instead, for a viewer whose role cannot write agent skills.
 */
export function AgentSkillFields(props: AgentSkillFieldsProps) {
  const t = useT();
  if (props.readOnly) {
    return <AgentSkillFieldValues values={props.values} />;
  }
  const { register, control, errors, showPlaceholders = false } = props;

  return (
    <>
      <FormField htmlFor="name" label={t("common.name")} required error={errors.name?.message}>
        <Input
          id="name"
          placeholder={showPlaceholders ? t("admin.eGCodeReview") : undefined}
          {...register("name")}
        />
      </FormField>

      <FormField
        htmlFor="repoUrl"
        label={t("common.repoUrl")}
        required
        error={errors.repoUrl?.message}
      >
        <Input
          id="repoUrl"
          placeholder={showPlaceholders ? "https://github.com/owner/repo" : undefined}
          {...register("repoUrl")}
        />
      </FormField>

      <FormField htmlFor="repoPath" label={t("common.repoPath")} error={errors.repoPath?.message}>
        <Input
          id="repoPath"
          placeholder={showPlaceholders ? t("admin.pathWithinRepoOptional") : undefined}
          {...register("repoPath")}
        />
      </FormField>

      <FormField htmlFor="repoRef" label={t("common.ref")} error={errors.repoRef?.message}>
        <Input
          id="repoRef"
          placeholder={showPlaceholders ? t("admin.branchOrTagOptional") : undefined}
          {...register("repoRef")}
        />
      </FormField>

      <FormField
        htmlFor="description"
        label={t("common.description")}
        error={errors.description?.message}
      >
        <Textarea
          id="description"
          rows={4}
          placeholder={showPlaceholders ? t("admin.whatThisSkillDoesOptional") : undefined}
          {...register("description")}
        />
      </FormField>

      <FormField
        htmlFor="repoAuthUsername"
        label={t("common.authUsername")}
        error={errors.repoAuthUsername?.message}
      >
        <Input
          id="repoAuthUsername"
          placeholder={showPlaceholders ? t("admin.eGOctocatOptional") : undefined}
          {...register("repoAuthUsername")}
        />
      </FormField>

      <Controller
        control={control}
        name="repoAuthPassword"
        render={({ field }) => (
          <SecretRefField
            value={field.value}
            onChange={field.onChange}
            label={t("common.authPassword")}
            idPrefix="repoAuthPassword"
            error={errors.repoAuthPassword?.message}
            hint={t("admin.oneEntryOfARegisteredSecretUsed")}
          />
        )}
      />
    </>
  );
}
