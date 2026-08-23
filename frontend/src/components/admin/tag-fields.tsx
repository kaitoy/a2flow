/**
 * @module TagFields — Shared schema and field set for the tag create and edit forms.
 *
 * Both forms edit the same two registered fields (`name`, `description`)
 * through the same shape, so the schema, the empty/reset values, the
 * request-body builders, and the fields themselves live here rather than
 * being duplicated per page — the same split `agent-skill-fields.tsx` uses.
 *
 * `color` is deliberately NOT part of this module: it is a controlled select
 * with a live preview (`TagColorField`), never a registered `react-hook-form`
 * field, and each page already owns that piece of state and its wiring
 * (`previewLabel`, `readOnly`) independently. Centralizing it here would
 * relocate one JSX line while forcing an awkward extra prop bundle onto this
 * component's read-only contract, so both pages keep rendering
 * `TagColorField` themselves.
 */
"use client";

import type { FieldErrors, UseFormRegister } from "react-hook-form";
import type { z } from "zod";
import { FormField } from "@/components/admin/form-field";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zTagCreate } from "@/generated/api/zod.gen";
import type { TagCreate, TagUpdate } from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/** Validation schema shared by the create and edit forms; `color` is handled outside it. */
export const tagFormSchema = zTagCreate.omit({ color: true });

/** Form values for the tag create and edit forms. */
export type TagFormValues = z.input<typeof tagFormSchema>;

/** Blank form values, used as the create form's defaults and the edit form's reset base. */
export function emptyTagFormValues(): TagFormValues {
  return { name: "", description: "" };
}

/**
 * Build the `POST` body's `name`/`description` fields, omitting a blank
 * description so the backend applies its own default. `color` is merged in
 * by the caller.
 *
 * @param values - Current form values.
 * @returns The `name`/`description` portion of the body for creating the tag.
 */
export function toTagCreateBody(values: TagFormValues): Omit<TagCreate, "color"> {
  return { name: values.name, description: values.description || null };
}

/**
 * Build the `PATCH` body's `name`/`description` fields, sending a blank
 * description as `null` so a value the user cleared is actually cleared
 * server-side. `color` is merged in by the caller.
 *
 * @param values - Current form values.
 * @returns The `name`/`description` portion of the body for updating the tag.
 */
export function toTagUpdateBody(values: TagFormValues): Omit<TagUpdate, "color"> {
  return { name: values.name, description: values.description || null };
}

/** Props for the editable rendering of {@link TagFields}. */
export interface TagEditableFieldsProps {
  /** `register` from the page's `useForm`. */
  register: UseFormRegister<TagFormValues>;
  /** `formState.errors` from the page's `useForm`. */
  errors: FieldErrors<TagFormValues>;
  /** Whether to show input placeholders (the create form does, the edit form does not). */
  showPlaceholders?: boolean;
}

/** Props for the read-only rendering of {@link TagFields}. */
export interface TagReadOnlyFieldsProps {
  /** Renders every field as a value instead of a control. */
  readOnly: true;
  /** The values to display, e.g. the edit form's `getValues()`. */
  values: TagFormValues;
}

/**
 * Props for {@link TagFields}: either the form handles to edit with, or the
 * values to display. A read-only rendering has no control to register
 * against and no errors to report, so the two shapes are kept apart rather
 * than left as optional props that only make sense in one mode.
 */
export type TagFieldsProps =
  | ({ readOnly?: false } & TagEditableFieldsProps)
  | TagReadOnlyFieldsProps;

/**
 * Name and description of a tag. Pass `readOnly` with the current `values` to
 * render the same fields as plain values instead, for a viewer whose role
 * cannot write tags.
 */
export function TagFields(props: TagFieldsProps) {
  if (props.readOnly) {
    const { values } = props;
    return (
      <>
        <FormField htmlFor="name" label="Name" required>
          <ReadOnlyField>{values.name || EMPTY_VALUE}</ReadOnlyField>
        </FormField>
        <FormField htmlFor="description" label="Description">
          <ReadOnlyField className="whitespace-pre-wrap">
            {values.description || EMPTY_VALUE}
          </ReadOnlyField>
        </FormField>
      </>
    );
  }

  const { register, errors, showPlaceholders = false } = props;

  return (
    <>
      <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
        <Input
          id="name"
          placeholder={showPlaceholders ? "e.g. production" : undefined}
          {...register("name")}
        />
      </FormField>

      <FormField htmlFor="description" label="Description" error={errors.description?.message}>
        <Textarea
          id="description"
          rows={4}
          placeholder={showPlaceholders ? "What this tag means (optional)" : undefined}
          {...register("description")}
        />
      </FormField>
    </>
  );
}
