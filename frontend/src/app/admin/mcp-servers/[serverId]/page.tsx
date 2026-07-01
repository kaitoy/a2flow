/** @module EditMcpServerPage — Admin edit/view form for a registered MCP server. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Server } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ErrorBanner } from "@/components/admin/error-banner";
import { FormColumn } from "@/components/admin/form-column";
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
import { zMcpServerCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { deleteMcpServer, getMcpServer, updateMcpServer } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

// Generated schema carries the name/url constraints; the form edits headers as
// an ordered key/value pair list (converted to a record on submit), so override
// that one field's shape while keeping the rest from the generated schema.
const schema = zMcpServerCreate.omit({ headers: true }).extend({
  headers: z.array(z.object({ key: z.string(), value: z.string() })),
});

type FormValues = z.infer<typeof schema>;

export default function EditMcpServerPage() {
  const { serverId } = useParams<{ serverId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    reset,
    control,
    getValues,
    formState: { errors },
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
      await save.run(async () => {
        await updateMcpServer(serverId, {
          name: values.name,
          url: values.url,
          headers: pairsToRecord(values.headers),
        });
        dispatch(showToast({ message: "MCP server updated" }));
        router.push("/admin/mcp-servers");
      });
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

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "MCP Servers", href: "/admin/mcp-servers" },
    { label: "Edit" },
  ];

  if (loading) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AdminPageHeader title="Edit MCP Server" icon={Server} />
        <FormColumn>
          <FormSkeleton fields={3} />
        </FormColumn>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <AdminPageHeader title="Edit MCP Server" icon={Server} />

      <FormColumn>
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
            <Button
              type="submit"
              variant="primary"
              disabled={save.inFlight}
              status={save.status}
              pendingLabel="Saving…"
            >
              Save
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
      </FormColumn>
      <ConfirmDialog
        open={confirmOpen}
        title="Delete MCP Server"
        description={`Delete "${getValues("name")}"?`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </AdminPageContainer>
  );
}
