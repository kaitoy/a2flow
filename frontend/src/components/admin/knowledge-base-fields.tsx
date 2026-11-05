/**
 * @module KnowledgeBaseFields — Shared schema and field set for the knowledge
 * base create and edit forms.
 */
"use client";

import type { FieldErrors, UseFormRegister } from "react-hook-form";
import type { z } from "zod";
import { FormField } from "@/components/admin/form-field";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zKnowledgeBaseCreate } from "@/generated/api/zod.gen";
import { useT } from "@/i18n/provider";
import type { KnowledgeBaseCreate } from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/** Validation schema shared by the create and edit forms. */
export const knowledgeBaseFormSchema = zKnowledgeBaseCreate;

/** Form values for the knowledge base create and edit forms. */
export type KnowledgeBaseFormValues = z.input<typeof knowledgeBaseFormSchema>;

/** Blank form values, used as the create form's defaults and the edit form's reset base. */
export function emptyKnowledgeBaseFormValues(): KnowledgeBaseFormValues {
  return { name: "", description: "" };
}

/**
 * Build the request body. A blank description is sent as `null`, which on
 * create leaves it unset and on update clears it.
 *
 * @param values - Current form values.
 * @returns The body for creating or updating the knowledge base.
 */
export function toKnowledgeBaseBody(values: KnowledgeBaseFormValues): KnowledgeBaseCreate {
  return { name: values.name, description: values.description || null };
}

/** Props for {@link KnowledgeBaseFields}: form handles to edit with, or values to display. */
export type KnowledgeBaseFieldsProps =
  | {
      readOnly?: false;
      /** `register` from the page's `useForm`. */
      register: UseFormRegister<KnowledgeBaseFormValues>;
      /** `formState.errors` from the page's `useForm`. */
      errors: FieldErrors<KnowledgeBaseFormValues>;
      /** Whether to show input placeholders (the create form does). */
      showPlaceholders?: boolean;
    }
  | {
      /** Renders every field as a value instead of a control. */
      readOnly: true;
      /** The values to display, e.g. the edit form's `getValues()`. */
      values: KnowledgeBaseFormValues;
    };

/**
 * Name and description of a knowledge base. The description is also what the
 * workflow agents see when they list the knowledge bases they can read, so it
 * is worth saying what the knowledge base covers.
 */
export function KnowledgeBaseFields(props: KnowledgeBaseFieldsProps) {
  const t = useT();
  if (props.readOnly) {
    return (
      <>
        <FormField htmlFor="name" label={t("common.name")} required>
          <ReadOnlyField>{props.values.name || EMPTY_VALUE}</ReadOnlyField>
        </FormField>
        <FormField htmlFor="description" label={t("common.description")}>
          <ReadOnlyField className="whitespace-pre-wrap">
            {props.values.description || EMPTY_VALUE}
          </ReadOnlyField>
        </FormField>
      </>
    );
  }
  const { register, errors, showPlaceholders = false } = props;
  return (
    <>
      <FormField htmlFor="name" label={t("common.name")} required error={errors.name?.message}>
        <Input
          id="name"
          placeholder={showPlaceholders ? t("admin.eGItOperations") : undefined}
          {...register("name")}
        />
      </FormField>
      <FormField
        htmlFor="description"
        label={t("common.description")}
        error={errors.description?.message}
      >
        <Textarea
          id="description"
          rows={3}
          placeholder={showPlaceholders ? t("admin.whatItCoversWorkflowAgentsReadThis") : undefined}
          {...register("description")}
        />
      </FormField>
    </>
  );
}
