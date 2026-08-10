/** @module WorkflowTaskTemplateDetailPage — Admin detail page for a single task template. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ListTree } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormField } from "@/components/admin/form-field";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { McpToolPicker } from "@/components/admin/mcp-tool-picker";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { CheckboxGroup } from "@/components/ui/checkbox-group";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zWorkflowTaskTemplateCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import {
  deleteWorkflowTaskTemplate,
  getWorkflow,
  getWorkflowTaskTemplate,
  isForbiddenError,
  listWorkflowTaskTemplates,
  SUPPRESS_FORBIDDEN_TOAST,
  type ToolBinding,
  updateWorkflowTaskTemplate,
  type WorkflowTaskTemplate,
} from "@/lib/api";
import { bindingToValue, valueToBinding } from "@/lib/mcp-tool-options";
import { Role, useHasRole } from "@/lib/roles";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

// Generated schema carries the title/description constraints. The parent
// workflow id comes from the URL, and the form edits dependencies and tool
// bindings as plain string arrays (encoded values), so omit those and re-add
// them in the form's shape.
const schema = zWorkflowTaskTemplateCreate
  .omit({
    workflowId: true,
    dependsOnIds: true,
    toolBindings: true,
  })
  .extend({
    dependsOnIds: z.array(z.string()),
    toolBindings: z.array(z.string()),
  });

type FormValues = z.infer<typeof schema>;

/**
 * Detail page of a single task template — one step of a workflow's design — with
 * its dependency and MCP tool pickers. The page is titled with the template's
 * own title, the label its row carries in the list.
 *
 * A viewer without the developer role (e.g. `requester`, who reaches this
 * page read-only from the task template list) gets a read-only rendering:
 * Title and Description show as plain text, the Depends on picker sits
 * inside a disabled `fieldset` so its native checkboxes can't be toggled,
 * MCP Tools is omitted entirely (there's nothing a read-only viewer can do
 * with it, and skipping it avoids mounting `McpToolPicker`'s MCP
 * server/tool catalog fetch), and Save/Delete are hidden rather than left
 * to fail with a 403 on click — the same convention the parent
 * `WorkflowDetailPage` follows.
 */
export default function WorkflowTaskTemplateDetailPage() {
  const { workflowId, templateId } = useParams<{ workflowId: string; templateId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const canEdit = useHasRole(Role.DEVELOPER);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [candidates, setCandidates] = useState<WorkflowTaskTemplate[]>([]);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);
  const [templateBindings, setTemplateBindings] = useState<ToolBinding[]>([]);
  // The persisted title, which names the page. Kept out of the form so the
  // heading names the saved record rather than following every keystroke.
  const [title, setTitle] = useState("");
  // The parent workflow's name, shown as a breadcrumb crumb linking back to
  // its detail page.
  const [workflowName, setWorkflowName] = useState("");

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
    defaultValues: {
      title: "",
      description: "",
      dependsOnIds: [] as string[],
      toolBindings: [] as string[],
    },
  });

  useEffect(() => {
    getWorkflowTaskTemplate(templateId, SUPPRESS_FORBIDDEN_TOAST)
      .then((template) => {
        setTitle(template.title);
        reset({
          title: template.title,
          description: template.description ?? "",
          dependsOnIds: template.dependsOnIds ?? [],
          toolBindings: (template.toolBindings ?? []).map(bindingToValue),
        });
        setTemplateBindings(template.toolBindings ?? []);
        setAudit({
          createdBy: template.createdBy,
          updatedBy: template.updatedBy,
          createdAt: template.createdAt,
          updatedAt: template.updatedAt,
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
  }, [templateId, reset]);

  useEffect(() => {
    listWorkflowTaskTemplates(workflowId, { limit: 100 })
      .then(setCandidates)
      .catch(() => {
        // Candidate list is non-essential; the picker simply renders empty.
      });
  }, [workflowId]);

  useEffect(() => {
    getWorkflow(workflowId)
      .then((wf) => setWorkflowName(wf.name))
      .catch(() => {
        // Failure toast is shown globally by api.ts; the breadcrumb crumb
        // simply stays as an ellipsis.
      });
  }, [workflowId]);

  async function onSubmit(values: FormValues) {
    try {
      await save.run(async () => {
        await updateWorkflowTaskTemplate(templateId, {
          title: values.title,
          description: values.description || null,
          dependsOnIds: values.dependsOnIds,
          toolBindings: values.toolBindings.map(valueToBinding),
        });
        dispatch(showToast({ message: "Template updated" }));
        router.push(`/admin/workflows/${workflowId}/task-templates`);
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  async function executeDelete() {
    setConfirmOpen(false);
    try {
      await deleteWorkflowTaskTemplate(templateId);
      router.push(`/admin/workflows/${workflowId}/task-templates`);
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Workflows", href: "/admin/workflows" },
    // Links back to this template's parent workflow; an ellipsis stands in
    // until its name has loaded.
    { label: workflowName || "…", href: `/admin/workflows/${workflowId}` },
    { label: "Task Templates", href: `/admin/workflows/${workflowId}/task-templates` },
    // The template itself is the current page; an ellipsis stands in until its
    // title has loaded.
    { label: title || "…" },
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
        <FormLayout header={<AdminPageHeader icon={ListTree} />}>
          <FormSkeleton fields={5} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout
        header={<AdminPageHeader title={title} icon={ListTree} />}
        aside={audit && <AuditMeta {...audit} />}
      >
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <div className="text-xs text-on-surface-variant">
            Workflow ID: <span className="font-mono">{workflowId}</span>
          </div>

          <FormField htmlFor="title" label="Title" required error={errors.title?.message}>
            {canEdit ? (
              <Input id="title" {...register("title")} />
            ) : (
              <ReadOnlyField>{title}</ReadOnlyField>
            )}
          </FormField>

          <FormField htmlFor="description" label="Description">
            {canEdit ? (
              <Textarea id="description" rows={4} {...register("description")} />
            ) : (
              <ReadOnlyField className="whitespace-pre-wrap">
                {getValues("description") || "—"}
              </ReadOnlyField>
            )}
          </FormField>

          <fieldset disabled={!canEdit} className="contents">
            <FormField htmlFor="dependsOnIds" label="Depends on">
              <Controller
                control={control}
                name="dependsOnIds"
                render={({ field }) => (
                  <CheckboxGroup
                    name="dependsOnIds"
                    options={candidates
                      .filter((t) => t.id !== templateId)
                      .map((t) => ({ value: t.id, label: t.title }))}
                    value={field.value}
                    onChange={field.onChange}
                    emptyMessage="No other templates in this workflow to depend on."
                  />
                )}
              />
            </FormField>
          </fieldset>

          {canEdit && (
            <FormField htmlFor="toolBindings" label="MCP Tools">
              <Controller
                control={control}
                name="toolBindings"
                render={({ field }) => (
                  <McpToolPicker
                    value={field.value}
                    onChange={field.onChange}
                    boundBindings={templateBindings}
                  />
                )}
              />
            </FormField>
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
              onClick={() => router.push(`/admin/workflows/${workflowId}/task-templates`)}
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
        title="Delete Task Template"
        description={`Delete "${getValues("title")}"?`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </AdminPageContainer>
  );
}
