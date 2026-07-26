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
import { SecretRefField } from "@/components/admin/secret-ref-field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zAgentSkillCreate } from "@/generated/api/zod.gen";
import type { AgentSkillCreate, AgentSkillUpdate } from "@/lib/api";

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
    description: values.description || null,
    repoAuthPassword: values.repoAuthPassword || null,
    repoAuthUsername: values.repoAuthUsername || null,
  };
}

/** Props for {@link AgentSkillFields}. */
export interface AgentSkillFieldsProps {
  /** `register` from the page's `useForm`. */
  register: UseFormRegister<AgentSkillFormValues>;
  /** `control` from the page's `useForm`, for the secret reference picker. */
  control: Control<AgentSkillFormValues>;
  /** `formState.errors` from the page's `useForm`. */
  errors: FieldErrors<AgentSkillFormValues>;
  /** Whether to show input placeholders (the create form does, the edit form does not). */
  showPlaceholders?: boolean;
}

/**
 * Name, repository location, description, and repository credentials of an
 * agent skill. The clone token is not typed in — it is picked as one entry of a
 * registered secret, which is the only form the backend accepts.
 */
export function AgentSkillFields({
  register,
  control,
  errors,
  showPlaceholders = false,
}: AgentSkillFieldsProps) {
  return (
    <>
      <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
        <Input
          id="name"
          placeholder={showPlaceholders ? "e.g. code-review" : undefined}
          {...register("name")}
        />
      </FormField>

      <FormField htmlFor="repoUrl" label="Repo URL" required error={errors.repoUrl?.message}>
        <Input
          id="repoUrl"
          placeholder={showPlaceholders ? "https://github.com/owner/repo" : undefined}
          {...register("repoUrl")}
        />
      </FormField>

      <FormField htmlFor="repoPath" label="Repo Path" error={errors.repoPath?.message}>
        <Input
          id="repoPath"
          placeholder={showPlaceholders ? "path/within/repo (optional)" : undefined}
          {...register("repoPath")}
        />
      </FormField>

      <FormField htmlFor="description" label="Description" error={errors.description?.message}>
        <Textarea
          id="description"
          rows={4}
          placeholder={showPlaceholders ? "What this skill does (optional)" : undefined}
          {...register("description")}
        />
      </FormField>

      <FormField
        htmlFor="repoAuthUsername"
        label="Auth Username"
        error={errors.repoAuthUsername?.message}
      >
        <Input
          id="repoAuthUsername"
          placeholder={showPlaceholders ? "e.g. octocat (optional)" : undefined}
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
            label="Auth Password"
            idPrefix="repoAuthPassword"
            error={errors.repoAuthPassword?.message}
            hint="One entry of a registered Secret, used as the password for a private repository."
          />
        )}
      />
    </>
  );
}
