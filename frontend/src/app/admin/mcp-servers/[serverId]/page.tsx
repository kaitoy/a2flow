/** @module EditMcpServerPage — Admin edit/view form for a registered MCP server. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { ErrorBanner } from "@/components/admin/error-banner";
import { FormField } from "@/components/admin/form-field";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import {
  KeyValueEditor,
  type KeyValuePair,
  pairsToRecord,
  recordToPairs,
} from "@/components/admin/key-value-editor";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { deleteMcpServer, getMcpServer, updateMcpServer } from "@/lib/api";

const schema = z.object({
  name: z.string().min(1, "Name is required"),
  url: z.string().url("Must be a valid URL").min(1, "URL is required"),
  headers: z.array(z.object({ key: z.string(), value: z.string() })),
});

type FormValues = z.infer<typeof schema>;

export default function EditMcpServerPage() {
  const { serverId } = useParams<{ serverId: string }>();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    control,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: { name: "", url: "", headers: [] as KeyValuePair[] },
  });

  useEffect(() => {
    getMcpServer(serverId)
      .then((server) => {
        reset({
          name: server.name,
          url: server.url,
          headers: recordToPairs(server.headers ?? {}),
        });
        setAudit({
          createdBy: server.createdBy,
          updatedBy: server.updatedBy,
          createdAt: server.createdAt,
          updatedAt: server.updatedAt,
        });
      })
      .catch((e: unknown) => {
        setApiError(e instanceof Error ? e.message : "Failed to load MCP server");
      })
      .finally(() => setLoading(false));
  }, [serverId, reset]);

  async function onSubmit(values: FormValues) {
    setApiError(null);
    try {
      await updateMcpServer(serverId, {
        name: values.name,
        url: values.url,
        headers: pairsToRecord(values.headers),
      });
      router.push("/admin/mcp-servers");
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to update MCP server");
    }
  }

  function handleDelete() {
    setConfirmOpen(true);
  }

  async function executeDelete() {
    setConfirmOpen(false);
    try {
      await deleteMcpServer(serverId);
      router.push("/admin/mcp-servers");
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to delete MCP server");
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl p-8">
        <h1 className="mb-6 text-3xl font-semibold tracking-tight text-gradient-accent">
          Edit MCP Server
        </h1>
        <FormSkeleton fields={3} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl p-8">
      <h1 className="mb-6 text-3xl font-semibold tracking-tight text-gradient-accent">
        Edit MCP Server
      </h1>

      <form
        onSubmit={handleSubmit(onSubmit)}
        className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
      >
        <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
          <Input id="name" {...register("name")} />
        </FormField>

        <FormField htmlFor="url" label="URL" required error={errors.url?.message}>
          <Input id="url" {...register("url")} />
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
          <Button
            type="button"
            variant="secondary"
            onClick={handleDelete}
            className="ml-auto text-error"
          >
            Delete
          </Button>
        </div>
      </form>
      {audit && (
        <div className="mt-4">
          <AuditMeta {...audit} />
        </div>
      )}
      <ConfirmDialog
        open={confirmOpen}
        title="Delete MCP Server"
        description={`Delete "${getValues("name")}"?`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
