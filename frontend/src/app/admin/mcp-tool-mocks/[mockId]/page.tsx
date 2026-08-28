/** @module McpToolMockDetailPage — Admin detail page for one tool mock. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { FlaskConical } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import {
  emptyMcpToolMockFormValues,
  McpToolMockFields,
  type McpToolMockFormValues,
  mcpToolMockFormSchema,
  responseToFormValue,
  toMcpToolMockBody,
} from "@/components/admin/mcp-tool-mock-fields";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { SelectOption } from "@/components/ui/select";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useIsAllTenantsView } from "@/hooks/useIsAllTenantsView";
import {
  deleteMcpToolMock,
  getMcpToolMock,
  isForbiddenError,
  listMcpServers,
  SUPPRESS_FORBIDDEN_TOAST,
  updateMcpToolMock,
} from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/** Upper bound used to fetch the MCP server registry for the server select. */
const SERVER_LIMIT = 1000;

/**
 * Detail page of one tool mock. The page is titled with the mock's own name.
 *
 * A viewer without the developer role gets a read-only rendering — reads are
 * open to every authenticated user, but writes are developer-only — so the
 * fields show as plain values (see {@link McpToolMockFields}'s `readOnly` mode)
 * and Save/Delete are hidden rather than left to fail with a 403 on click.
 */
export default function McpToolMockDetailPage() {
  const { mockId } = useParams<{ mockId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const canEdit = useHasRole(Role.DEVELOPER);
  const isAllTenantsView = useIsAllTenantsView();
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);
  const [serverOptions, setServerOptions] = useState<SelectOption[]>([]);
  // The persisted name, which titles the page. Kept out of the form so the
  // heading names the saved record rather than following every keystroke.
  const [name, setName] = useState("");

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    reset,
    control,
    getValues,
    watch,
    formState: { errors },
  } = useForm<McpToolMockFormValues>({
    resolver: zodResolver(mcpToolMockFormSchema),
    mode: "onBlur",
    defaultValues: emptyMcpToolMockFormValues(),
  });
  const target = watch("target");

  useEffect(() => {
    listMcpServers({ limit: SERVER_LIMIT })
      .then((servers) => setServerOptions(servers.map((s) => ({ value: s.id, label: s.name }))))
      .catch(() => {
        // Failure toast is shown globally by api.ts; the select simply stays
        // empty and the stored server id shows as unresolved.
      });
  }, []);

  useEffect(() => {
    getMcpToolMock(mockId, SUPPRESS_FORBIDDEN_TOAST)
      .then((mock) => {
        setName(mock.name);
        reset({
          ...emptyMcpToolMockFormValues(),
          name: mock.name,
          description: mock.description ?? "",
          target: mock.mcpServerId ? "mcp" : "builtin",
          mcpServerId: mock.mcpServerId ?? "",
          toolName: mock.toolName,
          responses: mock.responses.map(responseToFormValue),
        });
        setAudit({
          createdBy: mock.createdBy,
          updatedBy: mock.updatedBy,
          createdAt: mock.createdAt,
          updatedAt: mock.updatedAt,
          tenantId: isAllTenantsView ? mock.tenantId : undefined,
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
  }, [mockId, reset, isAllTenantsView]);

  async function onSubmit(values: McpToolMockFormValues) {
    try {
      await save.run(async () => {
        await updateMcpToolMock(mockId, toMcpToolMockBody(values));
        dispatch(showToast({ message: "Tool mock updated" }));
        router.push("/admin/mcp-tool-mocks");
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  async function executeDelete() {
    setConfirmOpen(false);
    try {
      await deleteMcpToolMock(mockId);
      router.push("/admin/mcp-tool-mocks");
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Tool Mocks", href: "/admin/mcp-tool-mocks" },
    // The mock itself is the current page; an ellipsis stands in until its name
    // has loaded.
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
        <FormLayout header={<AdminPageHeader icon={FlaskConical} />}>
          <FormSkeleton fields={4} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout
        header={<AdminPageHeader title={name} icon={FlaskConical} />}
        aside={audit && <AuditMeta {...audit} />}
      >
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          {canEdit ? (
            <McpToolMockFields
              register={register}
              control={control}
              errors={errors}
              target={target}
              serverOptions={serverOptions}
            />
          ) : (
            <McpToolMockFields readOnly values={getValues()} serverOptions={serverOptions} />
          )}

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
            <Button
              type="button"
              variant="ghost"
              onClick={() => router.push("/admin/mcp-tool-mocks")}
            >
              {canEdit ? "Cancel" : "Back"}
            </Button>
            {canEdit && (
              <Button
                type="button"
                variant="danger"
                onClick={() => setConfirmOpen(true)}
                className="ml-auto"
              >
                Delete
              </Button>
            )}
          </div>
        </form>
      </FormLayout>
      <ConfirmDialog
        open={confirmOpen}
        title="Delete Tool Mock"
        description={`Delete "${getValues("name")}"? Runs already started keep their own copy of it and are unaffected.`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </AdminPageContainer>
  );
}
