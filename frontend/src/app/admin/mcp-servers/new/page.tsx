/** @module NewMcpServerPage — Admin form for registering a new remote MCP server. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { ErrorBanner } from "@/components/admin/error-banner";
import { FormField } from "@/components/admin/form-field";
import {
  KeyValueEditor,
  type KeyValuePair,
  pairsToRecord,
} from "@/components/admin/key-value-editor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createMcpServer } from "@/lib/api";

const schema = z.object({
  name: z.string().min(1, "Name is required"),
  url: z.string().url("Must be a valid URL").min(1, "URL is required"),
  headers: z.array(z.object({ key: z.string(), value: z.string() })),
});

type FormValues = z.infer<typeof schema>;

export default function NewMcpServerPage() {
  const router = useRouter();
  const [apiError, setApiError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: { name: "", url: "", headers: [] as KeyValuePair[] },
  });

  async function onSubmit(values: FormValues) {
    setApiError(null);
    try {
      await createMcpServer({
        name: values.name,
        url: values.url,
        headers: pairsToRecord(values.headers),
      });
      router.push("/admin/mcp-servers");
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to create MCP server");
    }
  }

  return (
    <div className="mx-auto max-w-2xl p-8">
      <h1 className="mb-6 text-3xl font-semibold tracking-tight text-gradient-accent">
        New MCP Server
      </h1>

      <form
        onSubmit={handleSubmit(onSubmit)}
        className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
      >
        <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
          <Input id="name" placeholder="e.g. web-search" {...register("name")} />
        </FormField>

        <FormField htmlFor="url" label="URL" required error={errors.url?.message}>
          <Input id="url" placeholder="https://mcp.example.com/mcp" {...register("url")} />
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
        </FormField>

        <ErrorBanner error={apiError} />

        <div className="flex gap-2">
          <Button type="submit" variant="primary" disabled={isSubmitting}>
            {isSubmitting ? "Saving…" : "Save"}
          </Button>
          <Button type="button" variant="ghost" onClick={() => router.push("/admin/mcp-servers")}>
            Cancel
          </Button>
        </div>
      </form>
    </div>
  );
}
