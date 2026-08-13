/** @module McpServerDetailPage — Admin detail page for a registered MCP server. */
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
import { TagPicker } from "@/components/admin/tag-picker";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import {
  deleteMcpServer,
  getMcpServer,
  isForbiddenError,
  SUPPRESS_FORBIDDEN_TOAST,
  setMcpServerTags,
  updateMcpServer,
} from "@/lib/api";
import { sameIds } from "@/lib/ids";
import { Role, useHasRole } from "@/lib/roles";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/**
 * Detail page of a registered MCP server: its connection fields and the tools
 * it advertises. The page is titled with the server's own name.
 *
 * A viewer without the developer role gets a read-only rendering — reads are
 * open to every authenticated user, but writes are developer-only — so the
 * connection fields show as plain values (see {@link McpServerFields}'s
 * `readOnly` mode) and Save/Delete are hidden rather than left to fail with a
 * 403 on click. The tools panel stays: listing a server's tools is a read.
 */
export default function McpServerDetailPage() {
  const { serverId } = useParams<{ serverId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const canEdit = useHasRole(Role.DEVELOPER);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);
  // The persisted name, which titles the page. Kept out of the form so the
  // heading names the saved record rather than following every keystroke.
  const [name, setName] = useState("");

  // Tags live outside the form state: the picker is a controlled
  // multi-select rather than a registered input. `savedTagIds` is what the
  // record carried when it loaded, so an untouched selection writes nothing.
  const [tagIds, setTagIds] = useState<string[]>([]);
  const [savedTagIds, setSavedTagIds] = useState<string[]>([]);

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
    getMcpServer(serverId, SUPPRESS_FORBIDDEN_TOAST)
      .then((server) => {
        setName(server.name);
        setTagIds(server.tagIds ?? []);
        setSavedTagIds(server.tagIds ?? []);
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
      .catch((err: unknown) => {
        if (isForbiddenError(err)) {
          setForbidden(true);
          return;
        }
        // Failure toast is shown globally by api.ts; nothing else to do here.
      })
      .finally(() => setLoading(false));
  }, [serverId, reset]);

  async function onSubmit(values: McpServerFormValues) {
    try {
      await save.run(async () => {
        await updateMcpServer(serverId, toMcpServerBody(values));
        // Tags are a separate sub-resource, so they are only written when
        // the selection actually changed.
        if (!sameIds(tagIds, savedTagIds)) {
          await setMcpServerTags(serverId, tagIds);
        }
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
    // The server itself is the current page; an ellipsis stands in until its
    // name has loaded.
    { label: name || "…" },
  ];

  if (forbidden) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AccessDeniedState fill="full" />
      </AdminPageContainer>
    );
  }

  if (loading) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={<AdminPageHeader icon={Server} />}>
          <FormSkeleton fields={4} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout
        header={<AdminPageHeader title={name} icon={Server} />}
        aside={audit && <AuditMeta {...audit} />}
      >
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          {canEdit ? (
            <McpServerFields
              register={register}
              control={control}
              errors={errors}
              transport={transport}
            />
          ) : (
            <McpServerFields readOnly values={getValues()} />
          )}

          <TagPicker value={tagIds} onChange={setTagIds} readOnly={!canEdit} />

          <div className="flex gap-2">
            {canEdit && (
              <Button
                type="submit"
                variant="primary"
                disabled={save.inFlight}
                status={save.status}
                pendingLabel="Saving…"
              >
                Save
              </Button>
            )}
            <Button type="button" variant="ghost" onClick={() => router.push("/admin/mcp-servers")}>
              {canEdit ? "Cancel" : "Back"}
            </Button>
            {canEdit && (
              <Button type="button" variant="danger" onClick={handleDelete} className="ml-auto">
                Delete
              </Button>
            )}
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
