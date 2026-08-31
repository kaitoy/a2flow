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
 *
 * An `mcp` target's server and tool are picked through {@link McpToolField} —
 * the same two-step "choose the server, then a tool from its live listing"
 * control the task-template forms use — so the two forms behave alike and the
 * page no longer fetches the server registry itself.
 *
 * The form owns the tool listing rather than leaving it to {@link McpToolField},
 * because the chosen tool is needed in two places: the
 * {@link ToolOutputFormatPanel} under the picker, and the "Insert from schema"
 * shortcut in each `structured` response. Listing a server connects to it live,
 * so it is done once and shared.
 */
"use client";

import { FileJson, Plus, Server, Trash2, Wrench } from "lucide-react";
import { useState } from "react";
import type { Control, FieldErrors, UseFormRegister } from "react-hook-form";
import { Controller, useController, useFieldArray, useWatch } from "react-hook-form";
import { z } from "zod";
import { FormField } from "@/components/admin/form-field";
import { McpToolField } from "@/components/admin/mcp-tool-field";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import { ToolOutputFormatPanel } from "@/components/admin/tool-output-format-panel";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { SegmentedControl, type SegmentedOption } from "@/components/ui/segmented-control";
import { Select, type SelectOption } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { zMcpToolMockCreate, zMockResponseKind } from "@/generated/api/zod.gen";
import { type UseMcpServerToolsResult, useMcpServerTools } from "@/hooks/useMcpServerTools";
import type { McpToolInfo, McpToolMockCreate, MockResponse, MockResponseKind } from "@/lib/api";
import { sampleObjectTextFromJsonSchema } from "@/lib/json-schema-sample";
import { EMPTY_VALUE, formatChoice } from "@/lib/read-only-display";

/**
 * The one built-in agent tool A2Flow knows how to stub. Mirrors the backend's
 * `BUILTIN_MOCKABLE_TOOLS`; a mock naming anything else without a server is
 * rejected there, so the form offers no way to type one.
 */
export const REQUEST_APPROVAL_TOOL = "request_approval";

/**
 * What `request_approval` returns, as a schema the output-format panel can show
 * and the "Insert from schema" shortcut can build a skeleton from.
 *
 * A built-in tool is A2Flow's own, not a server's, so nothing advertises this
 * over MCP — it is written down here from the tool's own contract. The two
 * branches are the two shapes it can return; the first is what a mock normally
 * stands in for, so it is the one the skeleton comes from.
 */
const REQUEST_APPROVAL_TOOL_INFO: McpToolInfo = {
  name: REQUEST_APPROVAL_TOOL,
  description:
    "Records a pending approval and notifies whoever can decide it. A mocked call still " +
    "checks that the destination is a real, eligible approver, but records and notifies nothing.",
  outputSchema: {
    oneOf: [
      {
        title: "Recorded",
        type: "object",
        required: ["approval_id", "status"],
        properties: {
          approval_id: { type: "string" },
          status: { type: "string", enum: ["pending", "approved", "rejected"] },
        },
      },
      {
        title: "Refused",
        type: "object",
        required: ["error"],
        properties: { error: { type: "string" } },
      },
    ],
  },
};

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

/** The seeded value of a fresh `structured` response — an empty JSON object. */
const EMPTY_STRUCTURED_VALUE = "{}";

/** Blank form values, used as the create form's fallback and the edit form's reset base. */
export function emptyMcpToolMockFormValues(): McpToolMockFormValues {
  return {
    name: "",
    description: "",
    target: "mcp",
    mcpServerId: "",
    toolName: "",
    responses: [{ kind: "structured", value: EMPTY_STRUCTURED_VALUE }],
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
  /** Whether to show input placeholders (the create form does, the edit form does not). */
  showPlaceholders?: boolean;
}

/** Props for the read-only rendering of {@link McpToolMockFields}. */
export interface McpToolMockReadOnlyFieldsProps {
  /** Renders every field as a value instead of a control. */
  readOnly: true;
  /** The values to display, e.g. the edit form's `getValues()`. */
  values: McpToolMockFormValues;
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

/** Props for {@link TextActionButton}. */
interface TextActionButtonProps {
  /** Lucide icon rendered before the label. */
  icon: typeof Plus;
  /** The button's visible label. */
  label: string;
  /** Called on click. */
  onClick: () => void;
  /** Extra classes, e.g. to align the button within its card. */
  className?: string;
}

/**
 * The flat, accent-coloured action used inside the response editor's cards and
 * below the list. Shared so the two actions cannot drift apart.
 *
 * @param props - The icon, label, click handler, and any extra classes.
 * @returns The rendered button.
 */
function TextActionButton({ icon: Icon, label, onClick, className }: TextActionButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex w-fit items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-accent transition-colors hover:bg-accent-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50${
        className ? ` ${className}` : ""
      }`}
    >
      <Icon size={16} strokeWidth={1.8} aria-hidden="true" />
      {label}
    </button>
  );
}

/** Props for {@link ResponseCard}. */
interface ResponseCardProps {
  /** `control` from the page's `useForm`. */
  control: Control<McpToolMockFormValues>;
  /** `formState.errors` from the page's `useForm`. */
  errors: FieldErrors<McpToolMockFormValues>;
  /** This response's position in the list, zero-based. */
  index: number;
  /** False for the last remaining response, which may not be removed. */
  canRemove: boolean;
  /** Removes this response. */
  onRemove: () => void;
  /** The chosen tool's declared output schema, when it declares one. */
  outputSchema?: Record<string, unknown> | null;
}

/**
 * One call ordinal's response: its kind, its value, and — when the tool says
 * what it returns — a shortcut that fills the value with a skeleton of that
 * shape, so the operator edits keys rather than inventing them.
 *
 * @param props - The form handles, this card's position, and the tool's schema.
 * @returns The rendered card.
 */
function ResponseCard({
  control,
  errors,
  index,
  canRemove,
  onRemove,
  outputSchema,
}: ResponseCardProps) {
  const kind = useController({ control, name: `responses.${index}.kind` });
  const value = useController({ control, name: `responses.${index}.value` });
  const [confirmingInsert, setConfirmingInsert] = useState(false);

  const hasSchema = outputSchema !== null && outputSchema !== undefined;
  const canInsert = kind.field.value === "structured" && hasSchema;
  // A blank field, or the empty object a fresh response is seeded with, is not
  // work worth asking about before replacing.
  const trimmed = value.field.value.trim();
  const isDisposable = trimmed === "" || trimmed === EMPTY_STRUCTURED_VALUE;

  /** Replace the value with a skeleton built from the tool's output schema. */
  function insertSkeleton() {
    value.field.onChange(sampleObjectTextFromJsonSchema(outputSchema));
    setConfirmingInsert(false);
  }

  return (
    <div className="flex flex-col gap-2 rounded-xl glass-panel p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="text-label-caps text-on-surface-variant">Call #{index + 1}</span>
        <button
          type="button"
          aria-label={`Remove response ${index + 1}`}
          disabled={!canRemove}
          onClick={onRemove}
          className="inline-flex size-8 items-center justify-center rounded-lg text-on-surface-variant transition-colors hover:bg-error/10 hover:text-error focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-error/50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Trash2 size={16} strokeWidth={1.8} aria-hidden="true" />
        </button>
      </div>
      <Select
        options={KIND_OPTIONS}
        value={kind.field.value}
        onChange={(next) => kind.field.onChange(next as MockResponseKind)}
        aria-label={`Response ${index + 1} kind`}
      />
      <Textarea
        {...value.field}
        rows={4}
        className="font-mono text-xs"
        aria-label={`Response ${index + 1} value`}
      />
      {errors.responses?.[index]?.value && (
        <p className="text-xs text-error">{errors.responses[index]?.value?.message}</p>
      )}
      {canInsert && (
        <TextActionButton
          icon={FileJson}
          label="Insert from schema"
          className="self-end"
          onClick={() => (isDisposable ? insertSkeleton() : setConfirmingInsert(true))}
        />
      )}
      <ConfirmDialog
        open={confirmingInsert}
        title="Replace this response?"
        description={`Response ${index + 1} already has a value. Inserting the skeleton from the tool's output format discards what is there.`}
        confirmLabel="Replace"
        confirmVariant="primary"
        onConfirm={insertSkeleton}
        onCancel={() => setConfirmingInsert(false)}
      />
    </div>
  );
}

/** The editable list of per-call responses. */
function ResponseListEditor({
  control,
  errors,
  outputSchema,
}: {
  control: Control<McpToolMockFormValues>;
  errors: FieldErrors<McpToolMockFormValues>;
  outputSchema?: Record<string, unknown> | null;
}) {
  const { fields, append, remove } = useFieldArray({ control, name: "responses" });
  return (
    <div className="flex flex-col gap-3">
      {fields.map((field, index) => (
        <ResponseCard
          key={field.id}
          control={control}
          errors={errors}
          index={index}
          canRemove={fields.length > 1}
          onRemove={() => remove(index)}
          outputSchema={outputSchema}
        />
      ))}
      {errors.responses?.root && (
        <p className="text-xs text-error">{errors.responses.root.message}</p>
      )}
      <TextActionButton
        icon={Plus}
        label="Add response"
        onClick={() => append({ kind: "structured", value: EMPTY_STRUCTURED_VALUE })}
      />
    </div>
  );
}

/** The same fields as values, for a viewer who may see the mock but not edit it. */
function McpToolMockFieldValues({ values }: { values: McpToolMockFormValues }) {
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

      {values.target === "mcp" ? (
        <McpToolField
          readOnly
          idPrefix="mcpToolMock"
          mcpServerId={values.mcpServerId}
          toolName={values.toolName}
          onChange={() => {}}
        />
      ) : (
        <FormField htmlFor="toolName" label="Tool Name" required>
          <ReadOnlyField>{values.toolName || EMPTY_VALUE}</ReadOnlyField>
        </FormField>
      )}

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
 * Wires {@link McpToolField} to the form's `mcpServerId` / `toolName` fields.
 *
 * A sub-component so the two `useController` calls run only while the `mcp`
 * target is selected, mirroring how {@link ResponseListEditor} takes `control`.
 */
function McpToolMockServerToolField({
  control,
  errors,
  tools,
}: {
  control: Control<McpToolMockFormValues>;
  errors: FieldErrors<McpToolMockFormValues>;
  tools: UseMcpServerToolsResult;
}) {
  const server = useController({ control, name: "mcpServerId" });
  const tool = useController({ control, name: "toolName" });
  return (
    <McpToolField
      idPrefix="mcpToolMock"
      mcpServerId={server.field.value}
      toolName={tool.field.value}
      onChange={({ mcpServerId, toolName }) => {
        server.field.onChange(mcpServerId);
        tool.field.onChange(toolName);
      }}
      serverError={errors.mcpServerId?.message}
      toolError={errors.toolName?.message}
      tools={tools}
    />
  );
}

/** The editable rendering: the controls, plus everything they need to fetch. */
function McpToolMockEditableFields({
  register,
  control,
  errors,
  target,
  showPlaceholders,
}: McpToolMockEditableFieldsProps) {
  const mcpServerId = useWatch({ control, name: "mcpServerId" });
  const toolName = useWatch({ control, name: "toolName" });

  // Owned here, not inside McpToolField, because the output-format panel and
  // the response editor need the chosen tool too, and listing a server means
  // connecting to it live — a `stdio` server can take a minute to answer.
  const tools = useMcpServerTools(target === "mcp" && mcpServerId !== "" ? mcpServerId : null);

  const selectedTool =
    target === "builtin"
      ? REQUEST_APPROVAL_TOOL_INFO
      : tools.state.phase === "ready"
        ? tools.state.tools.find((tool) => tool.name === toolName)
        : undefined;

  // The tool is chosen but its listing has not landed yet — what opening the
  // edit page looks like, and what a `stdio` server can keep it looking like
  // for a minute. A failed listing is deliberately not covered: McpToolField
  // already reports it above with a Retry, so the panel just stays away.
  const outputFormatLoading =
    target === "mcp" &&
    toolName !== "" &&
    (tools.state.phase === "idle" || tools.state.phase === "loading");

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
        <McpToolMockServerToolField control={control} errors={errors} tools={tools} />
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

      {outputFormatLoading ? (
        <ToolOutputFormatPanel toolName={toolName} loading />
      ) : selectedTool ? (
        <ToolOutputFormatPanel
          toolName={selectedTool.name}
          description={selectedTool.description}
          outputSchema={selectedTool.outputSchema}
        />
      ) : null}

      <FormField htmlFor="responses" label="Responses" required>
        <ResponseOrderHint />
        <ResponseListEditor
          control={control}
          errors={errors}
          outputSchema={selectedTool?.outputSchema}
        />
      </FormField>
    </>
  );
}

/**
 * The tool-mock form fields, shared by the create and edit pages.
 *
 * Pass `readOnly` with the current values to render them as text instead of
 * controls, for a viewer without the `developer` role. A read-only rendering
 * never lists a server's tools, so it makes no MCP connection and shows no
 * output-format panel.
 */
export function McpToolMockFields(props: McpToolMockFieldsProps) {
  if (props.readOnly) {
    return <McpToolMockFieldValues values={props.values} />;
  }
  return <McpToolMockEditableFields {...props} />;
}
