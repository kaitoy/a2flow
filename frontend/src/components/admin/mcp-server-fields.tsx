/**
 * @module McpServerFields — Shared schema and field set for the MCP server
 * create and edit forms.
 *
 * Both forms edit the same record through the same transport-discriminated
 * shape, so the schema, the empty/reset values, the request-body builder, and
 * the fields themselves live here rather than being duplicated per page.
 */
"use client";

import { Globe, Terminal } from "lucide-react";
import type { Control, FieldErrors, UseFormRegister } from "react-hook-form";
import { Controller } from "react-hook-form";
import { z } from "zod";
import { FormField } from "@/components/admin/form-field";
import {
  KeyValueEditor,
  type KeyValuePair,
  pairsToRecord,
} from "@/components/admin/key-value-editor";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import { StringListEditor } from "@/components/admin/string-list-editor";
import { Input } from "@/components/ui/input";
import { SegmentedControl, type SegmentedOption } from "@/components/ui/segmented-control";
import { Textarea } from "@/components/ui/textarea";
import { zMcpCommand, zMcpServerCreate, zMcpTransport } from "@/generated/api/zod.gen";
import type { McpServerCreate } from "@/lib/api";
import { EMPTY_VALUE, formatChoice, formatLines, formatPairs } from "@/lib/read-only-display";

/**
 * Run a generated field schema against a value that the form keeps as a plain
 * string, reporting the first failure on `path`.
 *
 * The generated `url` schema is nullish, so a hidden empty input would pass
 * it even though the active transport requires a value. The form therefore
 * holds it as a plain string and checks requiredness itself, then defers to
 * the generated schema for the format constraints.
 */
function validateRequired(
  value: string,
  schema: z.ZodType,
  ctx: z.RefinementCtx,
  path: string,
  emptyMessage: string
): void {
  if (value === "") {
    ctx.addIssue({ code: "custom", path: [path], message: emptyMessage });
    return;
  }
  const result = schema.safeParse(value);
  if (!result.success) {
    ctx.addIssue({ code: "custom", path: [path], message: result.error.issues[0].message });
  }
}

/**
 * Validation schema shared by the create and edit forms: the generated
 * constraints, with `headers`/`env` edited as ordered key/value pair lists and
 * the per-transport requiredness enforced the way the backend enforces it
 * against a merged PATCH.
 */
export const mcpServerFormSchema = z
  .object({
    name: zMcpServerCreate.shape.name,
    description: z.string(),
    transport: zMcpTransport,
    url: z.string(),
    headers: z.array(z.object({ key: z.string(), value: z.string() })),
    command: zMcpCommand,
    args: z.array(z.string()),
    env: z.array(z.object({ key: z.string(), value: z.string() })),
  })
  .superRefine((values, ctx) => {
    if (values.transport === "streamable_http") {
      validateRequired(values.url, zMcpServerCreate.shape.url, ctx, "url", "URL is required");
    }
  });

/** Form values for the MCP server create and edit forms. */
export type McpServerFormValues = z.infer<typeof mcpServerFormSchema>;

/**
 * The selectable transports. Module-level so the editable control and the
 * read-only label resolution share one list, and so the control is not handed a
 * fresh array literal on every render.
 */
const TRANSPORT_OPTIONS: ReadonlyArray<SegmentedOption<McpServerFormValues["transport"]>> = [
  { value: "streamable_http", label: "Streamable HTTP", icon: Globe },
  { value: "stdio", label: "stdio", icon: Terminal },
];

/** The launchers a stdio server may be started with. See {@link TRANSPORT_OPTIONS}. */
const COMMAND_OPTIONS: ReadonlyArray<SegmentedOption<McpServerFormValues["command"]>> = [
  { value: "npx", label: "npx" },
  { value: "uvx", label: "uvx" },
];

/** Blank form values, used as the create form's fallback and the edit form's reset base. */
export function emptyMcpServerFormValues(): McpServerFormValues {
  return {
    name: "",
    description: "",
    transport: "streamable_http",
    url: "",
    headers: [] as KeyValuePair[],
    command: "npx",
    args: [],
    env: [] as KeyValuePair[],
  };
}

/**
 * Build the request body for the active transport, dropping the other
 * transport's fields entirely so a PATCH that switches transport lets the
 * backend clear the stale ones.
 *
 * @param values - Current form values.
 * @returns The `POST`/`PATCH` body for the registered server.
 */
export function toMcpServerBody(values: McpServerFormValues): McpServerCreate {
  if (values.transport === "streamable_http") {
    return {
      name: values.name,
      description: values.description || null,
      transport: "streamable_http",
      url: values.url,
      headers: pairsToRecord(values.headers),
    };
  }
  return {
    name: values.name,
    description: values.description || null,
    transport: "stdio",
    command: values.command,
    args: values.args.filter((arg) => arg !== ""),
    env: pairsToRecord(values.env),
  };
}

/** Props for the editable rendering of {@link McpServerFields}. */
export interface McpServerEditableFieldsProps {
  /** `register` from the page's `useForm`. */
  register: UseFormRegister<McpServerFormValues>;
  /** `control` from the page's `useForm`, for the pair/list editors. */
  control: Control<McpServerFormValues>;
  /** `formState.errors` from the page's `useForm`. */
  errors: FieldErrors<McpServerFormValues>;
  /** Currently selected transport, watched by the page so the fields re-render. */
  transport: McpServerFormValues["transport"];
  /** Whether to show input placeholders (the create form does, the edit form does not). */
  showPlaceholders?: boolean;
}

/** Props for the read-only rendering of {@link McpServerFields}. */
export interface McpServerReadOnlyFieldsProps {
  /** Renders every field as a value instead of a control. */
  readOnly: true;
  /** The values to display, e.g. the edit form's `getValues()`. */
  values: McpServerFormValues;
}

/**
 * Props for {@link McpServerFields}: either the form handles to edit with, or
 * the values to display. A read-only rendering has no control to register
 * against and no errors to report, so the two shapes are kept apart rather than
 * left as optional props that only make sense in one mode.
 */
export type McpServerFieldsProps =
  | ({ readOnly?: false } & McpServerEditableFieldsProps)
  | McpServerReadOnlyFieldsProps;

/** Note shown under the header and environment editors about secret references. */
function SecretReferenceHint() {
  return (
    <p className="mt-1 text-xs text-on-surface-variant">
      Values may reference one entry of a registered secret as{" "}
      {/* biome-ignore lint/suspicious/noTemplateCurlyInString: literal placeholder syntax shown to the user */}
      {"${secret:name/key}"}, resolved when connecting.
    </p>
  );
}

/** Note shown under the arguments editor about referencing this server's own env vars. */
function EnvArgReferenceHint() {
  return (
    <p className="mt-1 text-xs text-on-surface-variant">
      An argument may reuse this server's own Environment Variables by name as{" "}
      {/* biome-ignore lint/suspicious/noTemplateCurlyInString: literal placeholder syntax shown to the user */}
      {"${env:NAME}"}, expanded when connecting.
    </p>
  );
}

/**
 * The same fields as values on a recessed surface, for a viewer who may see the
 * server but not edit it.
 *
 * The hints the editable fields carry are all about *how to type a value in*
 * (secret and env-var reference syntax, how `args` is passed to the process), so
 * they are dropped here — the stored values already show whatever references
 * they use.
 */
function McpServerFieldValues({ values }: { values: McpServerFormValues }) {
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

      <FormField htmlFor="transport" label="Transport" required>
        <ReadOnlyField>{formatChoice(TRANSPORT_OPTIONS, values.transport)}</ReadOnlyField>
      </FormField>

      {values.transport === "streamable_http" ? (
        <>
          <FormField htmlFor="url" label="URL" required>
            <ReadOnlyField>{values.url || EMPTY_VALUE}</ReadOnlyField>
          </FormField>

          <FormField htmlFor="headers" label="HTTP Headers">
            <ReadOnlyField className="whitespace-pre-wrap">
              {formatLines(formatPairs(values.headers))}
            </ReadOnlyField>
          </FormField>
        </>
      ) : (
        <>
          <FormField htmlFor="command" label="Command" required>
            <ReadOnlyField>{formatChoice(COMMAND_OPTIONS, values.command)}</ReadOnlyField>
          </FormField>

          <FormField htmlFor="args" label="Arguments">
            <ReadOnlyField className="whitespace-pre-wrap">
              {formatLines(values.args.filter((arg) => arg !== ""))}
            </ReadOnlyField>
          </FormField>

          <FormField htmlFor="env" label="Environment Variables">
            <ReadOnlyField className="whitespace-pre-wrap">
              {formatLines(formatPairs(values.env))}
            </ReadOnlyField>
          </FormField>
        </>
      )}
    </>
  );
}

/**
 * Name, transport switch, and the transport-specific fields of a registered
 * MCP server: URL plus HTTP headers for a remote server, or command, arguments,
 * and environment variables for one launched over stdio.
 *
 * Pass `readOnly` with the current `values` to render the same fields as plain
 * values instead, for a viewer whose role cannot write MCP servers.
 */
export function McpServerFields(props: McpServerFieldsProps) {
  if (props.readOnly) {
    return <McpServerFieldValues values={props.values} />;
  }
  const { register, control, errors, transport, showPlaceholders = false } = props;

  return (
    <>
      <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
        <Input
          id="name"
          placeholder={showPlaceholders ? "e.g. web-search" : undefined}
          {...register("name")}
        />
      </FormField>

      <FormField htmlFor="description" label="Description" error={errors.description?.message}>
        <Textarea
          id="description"
          rows={4}
          placeholder={showPlaceholders ? "What this server is for (optional)" : undefined}
          {...register("description")}
        />
      </FormField>

      <FormField htmlFor="transport" label="Transport" required>
        <Controller
          control={control}
          name="transport"
          render={({ field }) => (
            <SegmentedControl
              aria-label="Transport"
              options={TRANSPORT_OPTIONS}
              value={field.value}
              onChange={field.onChange}
            />
          )}
        />
      </FormField>

      {transport === "streamable_http" ? (
        <>
          <FormField htmlFor="url" label="URL" required error={errors.url?.message}>
            <Input
              id="url"
              placeholder={showPlaceholders ? "https://mcp.example.com/mcp" : undefined}
              {...register("url")}
            />
          </FormField>

          <FormField htmlFor="headers" label="HTTP Headers">
            <Controller
              control={control}
              name="headers"
              render={({ field }) => (
                <KeyValueEditor
                  name="headers"
                  pairs={field.value}
                  onChange={field.onChange}
                  keyPlaceholder="Authorization"
                  valuePlaceholder="Bearer …"
                />
              )}
            />
            <SecretReferenceHint />
          </FormField>
        </>
      ) : (
        <>
          <FormField htmlFor="command" label="Command" required>
            <Controller
              control={control}
              name="command"
              render={({ field }) => (
                <SegmentedControl
                  aria-label="Command"
                  options={COMMAND_OPTIONS}
                  value={field.value}
                  onChange={field.onChange}
                />
              )}
            />
            <p className="mt-1 text-xs text-on-surface-variant">
              Launched as a child process of the backend.
            </p>
          </FormField>

          <FormField htmlFor="args" label="Arguments">
            <Controller
              control={control}
              name="args"
              render={({ field }) => (
                <StringListEditor
                  name="args"
                  values={field.value}
                  onChange={field.onChange}
                  placeholder="-y"
                  addLabel="+ Add argument"
                />
              )}
            />
            <p className="mt-1 text-xs text-on-surface-variant">
              One entry per argument, in order. Passed straight to the process — never through a
              shell, so quoting and globs are not interpreted.
            </p>
            <EnvArgReferenceHint />
          </FormField>

          <FormField htmlFor="env" label="Environment Variables">
            <Controller
              control={control}
              name="env"
              render={({ field }) => (
                <KeyValueEditor
                  name="env"
                  pairs={field.value}
                  onChange={field.onChange}
                  keyPlaceholder="API_KEY"
                  valuePlaceholder="…"
                />
              )}
            />
            <SecretReferenceHint />
          </FormField>
        </>
      )}
    </>
  );
}
