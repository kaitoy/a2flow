/** @module EditMcpServerPage — Admin edit/view form for a registered MCP server. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Server } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { recordToPairs } from "@/components/admin/key-value-editor";
import {
  emptyMcpServerFormValues,
  McpServerFields,
  type McpServerFormValues,
  mcpServerFormSchema,
  toMcpServerBody,
} from "@/components/admin/mcp-server-fields";
import { McpServerToolsPanel } from "@/components/admin/mcp-server-tools-panel";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { deleteMcpServer, getMcpServer, updateMcpServer } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

export default function EditMcpServerPage() {
  const { serverId } = useParams<{ serverId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    reset,
    control,
    getValues,
    watch,
    formState: { errors },
  } = useForm<McpServerFormValues>({
    resolver: zodResolver(mcpServerFormSchema),
    mode: "onBlur",
    defaultValues: emptyMcpServerFormValues(),
  });
  const transport = watch("transport");

  useEffect(() => {
    getMcpServer(serverId)
      .then((server) => {
        reset({
          ...emptyMcpServerFormValues(),
          name: server.name,
          transport: server.transport ?? "streamable_http",
          url: server.url ?? "",
          headers: recordToPairs(server.headers ?? {}),
          command: server.command ?? "npx",
          args: server.args ?? [],
          env: recordToPairs(server.env ?? {}),
        });
        setAudit({
          createdBy: server.createdBy,
          updatedBy: server.updatedBy,
          createdAt: server.createdAt,
          updatedAt: server.updatedAt,
        });
      })
      .catch(() => {
        // Failure toast is shown globally by api.ts; nothing else to do here.
      })
      .finally(() => setLoading(false));
  }, [serverId, reset]);

  async function onSubmit(values: McpServerFormValues) {
    try {
      await save.run(async () => {
        await updateMcpServer(serverId, toMcpServerBody(values));
        dispatch(showToast({ message: "MCP server updated" }));
        router.push("/admin/mcp-servers");
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
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
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
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
        <FormLayout header={<AdminPageHeader title="Edit MCP Server" icon={Server} />}>
          <FormSkeleton fields={4} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout
        header={<AdminPageHeader title="Edit MCP Server" icon={Server} />}
        aside={audit && <AuditMeta {...audit} />}
      >
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <McpServerFields
            register={register}
            control={control}
            errors={errors}
            transport={transport}
          />

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
            <Button type="button" variant="danger" onClick={handleDelete} className="ml-auto">
              Delete
            </Button>
          </div>
        </form>
        <McpServerToolsPanel serverId={serverId} />
      </FormLayout>
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
