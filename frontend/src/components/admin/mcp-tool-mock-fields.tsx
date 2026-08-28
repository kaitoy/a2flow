/**
 * @module McpToolMockFields — Shared schema and field set for the tool-mock
 * create and edit forms.
 *
 * Both forms edit the same record, so the schema, the empty/reset values, the
 * request-body builder, and the fields themselves live here rather than being
 * duplicated per page.
 *
 * The `value` of a response is held as **text** throughout the form, not as a
 * parsed value: a `structured` response is JSON the operator types, and keeping
 * it as text is what lets a half-finished object stay on screen with an inline
 * error instead of being rejected keystroke by keystroke. It is parsed once, in
 * {@link toMcpToolMockBody}, after the schema has confirmed it parses at all.
 */
"use client";

import { Plus, Server, Trash2, Wrench } from "lucide-react";
import type { Control, FieldErrors, UseFormRegister } from "react-hook-form";
import { Controller, useFieldArray } from "react-hook-form";
import { z } from "zod";
import { FormField } from "@/components/admin/form-field";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import { Input } from "@/components/ui/input";
import { SegmentedControl, type SegmentedOption } from "@/components/ui/segmented-control";
import { Select, type SelectOption } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { zMcpToolMockCreate, zMockResponseKind } from "@/generated/api/zod.gen";
import type { McpToolMockCreate, MockResponse, MockResponseKind } from "@/lib/api";
import { EMPTY_VALUE, formatChoice } from "@/lib/read-only-display";

/**
 * The one built-in agent tool A2Flow knows how to stub. Mirrors the backend's
 * `BUILTIN_MOCKABLE_TOOLS`; a mock naming anything else without a server is
 * rejected there, so the form offers no way to type one.
 */
export const REQUEST_APPROVAL_TOOL = "request_approval";

/** Whether the mock targets a registered MCP server or a built-in agent tool. */
export type MockTarget = "mcp" | "builtin";

/** Validation schema shared by the create and edit forms. */
export const mcpToolMockFormSchema = z
  .object({
    name: zMcpToolMockCreate.shape.name,
    description: z.string(),
    target: z.enum(["mcp", "builtin"]),
    mcpServerId: z.string(),
    toolName: z.string(),
    responses: z
      .array(z.object({ kind: zMockResponseKind, value: z.string() }))
      .min(1, "At least one response is required"),
  })
  .superRefine((values, ctx) => {
    if (values.target === "mcp") {
      if (values.mcpServerId === "") {
        ctx.addIssue({ code: "custom", path: ["mcpServerId"], message: "Server is required" });
      }
      if (values.toolName === "") {
        ctx.addIssue({ code: "custom", path: ["toolName"], message: "Tool name is required" });
      }
    }
    values.responses.forEach((response, index) => {
      if (response.kind !== "structured") {
        if (response.value === "") {
          ctx.addIssue({
            code: "custom",
            path: ["responses", index, "value"],
            message: "A value is required",
          });
        }
        return;
      }
      let parsed: unknown;
      try {
        parsed = JSON.parse(response.value);
      } catch {
        ctx.addIssue({
          code: "custom",
          path: ["responses", index, "value"],
          message: "Must be valid JSON",
        });
        return;
      }
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        ctx.addIssue({
          code: "custom",
          path: ["responses", index, "value"],
          message: "Must be a JSON object",
        });
      }
    });
  });

/** Form values for the tool-mock create and edit forms. */
export type McpToolMockFormValues = z.infer<typeof mcpToolMockFormSchema>;

/** The selectable targets. Module-level so the control is not re-created per render. */
const TARGET_OPTIONS: ReadonlyArray<SegmentedOption<MockTarget>> = [
  { value: "mcp", label: "MCP tool", icon: Server },
  { value: "builtin", label: "Built-in tool", icon: Wrench },
];

/** The response kinds, in the order the select offers them. */
const KIND_OPTIONS: SelectOption[] = [
  { value: "structured", label: "Structured (JSON object)" },
  { value: "text", label: "Text" },
  { value: "error", label: "Error" },
];

/** The built-in tools a mock may target. */
const BUILTIN_TOOL_OPTIONS: SelectOption[] = [
  { value: REQUEST_APPROVAL_TOOL, label: REQUEST_APPROVAL_TOOL },
];

/** Blank form values, used as the create form's fallback and the edit form's reset base. */
export function emptyMcpToolMockFormValues(): McpToolMockFormValues {
  return {
    name: "",
    description: "",
    target: "mcp",
    mcpServerId: "",
    toolName: "",
    responses: [{ kind: "structured", value: "{}" }],
  };
}

/**
 * Turn a stored response into the text the form edits it as.
 *
 * @param response - One stored response.
 * @returns The same response with its value as editable text.
 */
export function responseToFormValue(response: MockResponse): {
  kind: MockResponseKind;
  value: string;
} {
  if (response.kind === "structured") {
    return { kind: response.kind, value: JSON.stringify(response.value ?? {}, null, 2) };
  }
  return { kind: response.kind, value: String(response.value ?? "") };
}

/**
 * Build the request body from the form values.
 *
 * A built-in mock sends `mcpServerId: null` — that null is what tells the
 * backend the target is one of A2Flow's own tools rather than a server's.
 *
 * @param values - Current form values, already validated by the schema.
 * @returns The `POST`/`PATCH` body for the mock.
 */
export function toMcpToolMockBody(values: McpToolMockFormValues): McpToolMockCreate {
  const builtin = values.target === "builtin";
  return {
    name: values.name,
    description: values.description || null,
    mcpServerId: builtin ? null : values.mcpServerId,
    toolName: builtin ? REQUEST_APPROVAL_TOOL : values.toolName,
    responses: values.responses.map((response) => ({
      kind: response.kind,
      value: response.kind === "structured" ? JSON.parse(response.value) : response.value,
    })),
  };
}

/** Props for the editable rendering of {@link McpToolMockFields}. */
export interface McpToolMockEditableFieldsProps {
  /** `register` from the page's `useForm`. */
  register: UseFormRegister<McpToolMockFormValues>;
  /** `control` from the page's `useForm`, for the target, server, and response list. */
  control: Control<McpToolMockFormValues>;
  /** `formState.errors` from the page's `useForm`. */
  errors: FieldErrors<McpToolMockFormValues>;
  /** Currently selected target, watched by the page so the fields re-render. */
  target: MockTarget;
  /** Registered MCP servers, offered as the server choices. */
  serverOptions: SelectOption[];
  /** Whether to show input placeholders (the create form does, the edit form does not). */
  showPlaceholders?: boolean;
}

/** Props for the read-only rendering of {@link McpToolMockFields}. */
export interface McpToolMockReadOnlyFieldsProps {
  /** Renders every field as a value instead of a control. */
  readOnly: true;
  /** The values to display, e.g. the edit form's `getValues()`. */
  values: McpToolMockFormValues;
  /** Registered MCP servers, used to name the selected one. */
  serverOptions: SelectOption[];
}

/**
 * Props for {@link McpToolMockFields}: either the form handles to edit with, or
 * the values to display. A read-only rendering has no control to register
 * against and no errors to report, so the two shapes are kept apart rather than
 * left as optional props that only make sense in one mode.
 */
export type McpToolMockFieldsProps =
  | ({ readOnly?: false } & McpToolMockEditableFieldsProps)
  | McpToolMockReadOnlyFieldsProps;

/** Explains what the ordered response list means, shown above the editor. */
function ResponseOrderHint() {
  return (
    <p className="mt-1 text-xs text-on-surface-variant">
      Responses are returned in order: the first for the run&apos;s first call, the second for its
      second, and so on. Once the list runs out the last response repeats, so a single response
      behaves as a constant.
    </p>
  );
}

/** The editable list of per-call responses. */
function ResponseListEditor({
  control,
  errors,
}: {
  control: Control<McpToolMockFormValues>;
  errors: FieldErrors<McpToolMockFormValues>;
}) {
  const { fields, append, remove } = useFieldArray({ control, name: "responses" });
  return (
    <div className="flex flex-col gap-3">
      {fields.map((field, index) => (
        <div key={field.id} className="flex flex-col gap-2 rounded-xl glass-panel p-4">
          <div className="flex items-center justify-between gap-2">
            <span className="text-label-caps text-on-surface-variant">Call #{index + 1}</span>
            <button
              type="button"
              aria-label={`Remove response ${index + 1}`}
              disabled={fields.length === 1}
              onClick={() => remove(index)}
              className="inline-flex size-8 items-center justify-center rounded-lg text-on-surface-variant transition-colors hover:bg-error/10 hover:text-error focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-error/50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Trash2 size={16} strokeWidth={1.8} aria-hidden="true" />
            </button>
          </div>
          <Controller
            control={control}
            name={`responses.${index}.kind`}
            render={({ field: kindField }) => (
              <Select
                options={KIND_OPTIONS}
                value={kindField.value}
                onChange={(value) => kindField.onChange(value as MockResponseKind)}
                aria-label={`Response ${index + 1} kind`}
              />
            )}
          />
          <Controller
            control={control}
            name={`responses.${index}.value`}
            render={({ field: valueField }) => (
              <Textarea
                {...valueField}
                rows={4}
                className="font-mono text-xs"
                aria-label={`Response ${index + 1} value`}
              />
            )}
          />
          {errors.responses?.[index]?.value && (
            <p className="text-xs text-error">{errors.responses[index]?.value?.message}</p>
          )}
        </div>
      ))}
      {errors.responses?.root && (
        <p className="text-xs text-error">{errors.responses.root.message}</p>
      )}
      <button
        type="button"
        onClick={() => append({ kind: "structured", value: "{}" })}
        className="inline-flex w-fit items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-accent transition-colors hover:bg-accent-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
      >
        <Plus size={16} strokeWidth={1.8} aria-hidden="true" />
        Add response
      </button>
    </div>
  );
}

/** The same fields as values, for a viewer who may see the mock but not edit it. */
function McpToolMockFieldValues({
  values,
  serverOptions,
}: {
  values: McpToolMockFormValues;
  serverOptions: SelectOption[];
}) {
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

      <FormField htmlFor="target" label="Target" required>
        <ReadOnlyField>{formatChoice(TARGET_OPTIONS, values.target)}</ReadOnlyField>
      </FormField>

      {values.target === "mcp" && (
        <FormField htmlFor="mcpServerId" label="MCP Server" required>
          <ReadOnlyField>
            {serverOptions.find((o) => o.value === values.mcpServerId)?.label || EMPTY_VALUE}
          </ReadOnlyField>
        </FormField>
      )}

      <FormField htmlFor="toolName" label="Tool Name" required>
        <ReadOnlyField>{values.toolName || EMPTY_VALUE}</ReadOnlyField>
      </FormField>

      <FormField htmlFor="responses" label="Responses" required>
        <div className="flex flex-col gap-2">
          {values.responses.map((response, index) => (
            <ReadOnlyField
              // The list is fixed for a read-only view, so the index is a
              // stable key here.
              // biome-ignore lint/suspicious/noArrayIndexKey: read-only, never reordered
              key={index}
              className="whitespace-pre-wrap font-mono text-xs"
            >
              {`#${index + 1} (${response.kind})\n${response.value}`}
            </ReadOnlyField>
          ))}
        </div>
      </FormField>
    </>
  );
}

/**
 * The tool-mock form fields, shared by the create and edit pages.
 *
 * Pass `readOnly` with the current values to render them as text instead of
 * controls, for a viewer without the `developer` role.
 */
export function McpToolMockFields(props: McpToolMockFieldsProps) {
  if (props.readOnly) {
    return <McpToolMockFieldValues values={props.values} serverOptions={props.serverOptions} />;
  }
  const { register, control, errors, target, serverOptions, showPlaceholders } = props;
  return (
    <>
      <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
        <Input
          id="name"
          {...register("name")}
          placeholder={showPlaceholders ? "Jira search returns no hits" : undefined}
        />
      </FormField>

      <FormField htmlFor="description" label="Description" error={errors.description?.message}>
        <Textarea
          id="description"
          rows={2}
          {...register("description")}
          placeholder={showPlaceholders ? "What this stub stands in for" : undefined}
        />
      </FormField>

      <FormField htmlFor="target" label="Target" required>
        <Controller
          control={control}
          name="target"
          render={({ field }) => (
            <SegmentedControl
              options={TARGET_OPTIONS}
              value={field.value}
              onChange={field.onChange}
              aria-label="Target"
            />
          )}
        />
      </FormField>

      {target === "mcp" ? (
        <>
          <FormField
            htmlFor="mcpServerId"
            label="MCP Server"
            required
            error={errors.mcpServerId?.message}
          >
            <Controller
              control={control}
              name="mcpServerId"
              render={({ field }) => (
                <Select
                  id="mcpServerId"
                  options={serverOptions}
                  value={field.value}
                  onChange={field.onChange}
                  placeholder="Select a server"
                />
              )}
            />
          </FormField>

          <FormField htmlFor="toolName" label="Tool Name" required error={errors.toolName?.message}>
            <Input
              id="toolName"
              {...register("toolName")}
              placeholder={showPlaceholders ? "search_issues" : undefined}
            />
          </FormField>
        </>
      ) : (
        <FormField htmlFor="toolName" label="Tool Name" required error={errors.toolName?.message}>
          <Controller
            control={control}
            name="toolName"
            render={({ field }) => (
              <Select
                id="toolName"
                options={BUILTIN_TOOL_OPTIONS}
                value={field.value || REQUEST_APPROVAL_TOOL}
                onChange={field.onChange}
              />
            )}
          />
        </FormField>
      )}

      <FormField htmlFor="responses" label="Responses" required>
        <ResponseOrderHint />
        <ResponseListEditor control={control} errors={errors} />
      </FormField>
    </>
  );
}
