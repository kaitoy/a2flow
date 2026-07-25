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
import { StringListEditor } from "@/components/admin/string-list-editor";
import { Input } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { zMcpCommand, zMcpServerCreate, zMcpTransport } from "@/generated/api/zod.gen";
import type { McpServerCreate } from "@/lib/api";

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

/** Blank form values, used as the create form's fallback and the edit form's reset base. */
export function emptyMcpServerFormValues(): McpServerFormValues {
  return {
    name: "",
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
      transport: "streamable_http",
      url: values.url,
      headers: pairsToRecord(values.headers),
    };
  }
  return {
    name: values.name,
    transport: "stdio",
    command: values.command,
    args: values.args.filter((arg) => arg !== ""),
    env: pairsToRecord(values.env),
  };
}

/** Props for {@link McpServerFields}. */
export interface McpServerFieldsProps {
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

/** Note shown under the header and environment editors about secret references. */
function SecretReferenceHint() {
  return (
    <p className="mt-1 text-xs text-on-surface-variant">
      Values may reference registered secrets as{" "}
      {/* biome-ignore lint/suspicious/noTemplateCurlyInString: literal placeholder syntax shown to the user */}
      {"${secret:name}"}, resolved when connecting.
    </p>
  );
}

/**
 * Name, transport switch, and the transport-specific fields of a registered
 * MCP server: URL plus HTTP headers for a remote server, or command, arguments,
 * and environment variables for one launched over stdio.
 */
export function McpServerFields({
  register,
  control,
  errors,
  transport,
  showPlaceholders = false,
}: McpServerFieldsProps) {
  return (
    <>
      <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
        <Input
          id="name"
          placeholder={showPlaceholders ? "e.g. web-search" : undefined}
          {...register("name")}
        />
      </FormField>

      <FormField htmlFor="transport" label="Transport" required>
        <Controller
          control={control}
          name="transport"
          render={({ field }) => (
            <SegmentedControl
              aria-label="Transport"
              options={[
                { value: "streamable_http", label: "Streamable HTTP", icon: Globe },
                { value: "stdio", label: "stdio", icon: Terminal },
              ]}
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
                  options={[
                    { value: "npx", label: "npx" },
                    { value: "uvx", label: "uvx" },
                  ]}
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
